"""ORA Windows/local worker: explicit local approval, isolated worktrees, durable receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

SERVICE = 'ora-desktop-worker'


def api(config, path, body, token=''):
    url = config['url'].rstrip('/')
    if not re.fullmatch(r'https://[a-zA-Z0-9.-]+(?::\d+)?', url):
        raise ValueError('Use an HTTPS backend origin.')
    data = json.dumps(body).encode()
    req = urllib.request.Request(url+'/api/v2/desktop/'+path, data=data,
        headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    with urllib.request.urlopen(req, timeout=115) as response:
        return json.load(response)


def command(argv, cwd, timeout=600):
    # Never inherit cloud/owner tokens into repository processes.
    env = {k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)')}
    env.update(CI='true', GIT_TERMINAL_PROMPT='0')
    with tempfile.TemporaryFile() as output:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=os.name!='nt', shell=False)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
            else:
                import signal
                os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            return 124, 'Timed out; process tree stopped.'
        output.seek(0,2)
        size=output.tell();output.seek(max(0,size-26000))
        return p.returncode, ('[Earlier output truncated]\n' if size>26000 else '')+output.read().decode(errors='replace')


def scrub(text):
    text=re.sub(r'(?i)(bearer\s+|(?:token|password|secret|api[_-]?key)\s*[:=]\s*)[^\s,;]+',r'\1[redacted]',text)
    text=re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|gsk_[A-Za-z0-9_]+)', '[redacted]', text)
    return text


def safe_patch(patch):
    if not patch: return
    paths=[]
    for line in patch.splitlines():
        if line.startswith(('--- ', '+++ ')):
            path=line[4:].split('\t')[0]
            if path=='/dev/null': raise ValueError('File creation/deletion is not supported by the worker patch flow.')
            if not path.startswith(('a/','b/')): raise ValueError('Use a standard Git unified diff.')
            path=path[2:]
            if any(x in ('..','') for x in path.split('/')) or '\\' in path or ':' in path or path.startswith('/'):
                raise ValueError('Unsafe patch path.')
            if any(x.startswith('.') for x in path.split('/')) or re.search(r'(?i)(secret|credential|token|password|\.pem$|\.key$|lock\.)',path):
                raise ValueError('Credential, hidden and lock files cannot be patched.')
            paths.append(path)
        if re.search(r'(?:new|old) mode 120000|GIT binary patch|^rename |^copy ',line): raise ValueError('Only existing regular text files can be patched.')
    if not paths or len(set(paths))>5: raise ValueError('Patch must change 1–5 regular files.')


def resolve_command(check):
    executable=shutil.which(check[0])
    if not executable: raise ValueError('Install the local check executable: '+check[0])
    argv=[executable]+check[1:]
    if os.name=='nt' and executable.lower().endswith(('.cmd','.bat')):
        if any(re.search(r'[&|<>^%\r\n!]',a) for a in argv): raise ValueError('Unsupported shell characters in check configuration.')
        argv=[os.environ.get('COMSPEC','cmd.exe'),'/d','/s','/c',subprocess.list2cmdline(argv)]
    return argv


def execute(config, job, folder):
    spec=config['repositories'].get(job['repository'])
    if not spec or job['check'] not in spec['checks']: raise ValueError('Repository or check is not allowed locally.')
    root=Path(spec['path']).expanduser().resolve(strict=True)
    check=spec['checks'][job['check']]
    if not isinstance(check,list) or not check or not all(isinstance(x,str) for x in check): raise ValueError('Checks must be argument arrays.')
    code,head=command(['git','rev-parse','HEAD'],root,30)
    if code: raise ValueError('Cannot read repository HEAD.')
    head=head.strip()
    if job.get('base_sha') and head!=job['base_sha']: raise ValueError('Repository HEAD changed. Prepare a new job against the current commit.')
    safe_patch(job.get('patch',''))
    print('\nPROJECT:',job['repository'],'\nCOMMIT:',head,'\nCHECK:',json.dumps(check))
    print('PATCH:\n'+job.get('patch','(none)'))
    print('SETUP:',json.dumps(spec.get('setup', [])))
    print('This executes repository code with your local user permissions. A Git worktree is not a security sandbox.')
    if input('Run this job? Type RUN: ').strip()!='RUN':
        return {'status':'declined','summary':'Declined locally. No tests were run.','diff':'','branch':''}
    work=folder/'worktree';branch='ora/desktop-'+job['id']
    code,out=command(['git','worktree','add','-b',branch,str(work),head],root,60)
    if code: raise RuntimeError(out)
    if job.get('patch'):
        patch=folder/'change.patch';patch.write_text(job['patch'],encoding='utf-8')
        code,out=command(['git','apply','--check',str(patch)],work,30)
        if code: raise RuntimeError('Patch check failed: '+out)
        # Reject symlink traversal, even where diff syntax looks like a text patch.
        for line in job['patch'].splitlines():
            if line.startswith('+++ b/'):
                rel=line[6:].split('\t')[0];target=work/rel
                if target.is_symlink() or not target.resolve().is_relative_to(work.resolve()): raise ValueError('Patch target escapes worktree.')
        code,out=command(['git','apply',str(patch)],work,30)
        if code: raise RuntimeError(out)
    for setup in spec.get('setup', []):
        if not isinstance(setup,list) or not setup or not all(isinstance(x,str) for x in setup): raise ValueError('Setup must be a list of command argument arrays.')
        setup_code,setup_out=command(resolve_command(setup),work,600)
        if setup_code: raise RuntimeError('Setup failed; requested check was not run. '+setup_out)
    argv=resolve_command(check)
    code,out=command(argv,work,int(min(900,max(10,spec.get('timeout',600)))))
    diffcode,diff=command(['git','diff','--no-ext-diff','--no-color'],work,30)
    if diffcode: diff='Diff unavailable: '+diff
    summary=f'Check {job["check"]}: exit {code}.\nWorktree: {work}\n'+out
    print(scrub(summary));print(scrub(diff))
    share=input('Upload the displayed redacted output and diff to your ORA workspace? Type SHARE: ').strip()=='SHARE'
    return {'status':'passed' if code==0 else 'failed', 'summary':scrub(summary)[:30000] if share else f'Check {job["check"]}: exit {code}. Detailed evidence withheld locally.',
            'diff':scrub(diff)[:60000] if share else '', 'branch':branch, 'verified_diff_sha':hashlib.sha256(diff.encode()).hexdigest(), 'base_sha':head, 'diff_truncated':diff.startswith('[Earlier output truncated]')}


def save(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(path)


def publish(state, job_id):
    if not re.fullmatch('[a-f0-9]{32}',job_id): raise ValueError('Invalid job ID.')
    folder=state/job_id;receipt=folder/'receipt.json';record=json.loads(receipt.read_text())
    result=record.get('result',{})
    if record.get('publish_started'): raise ValueError('A publish was already attempted. Inspect GitHub and local Git before any manual retry.')
    if result.get('status')!='passed' or result.get('diff_truncated'): raise ValueError('Only a passed check with complete diff evidence can be published.')
    work=folder/'worktree'
    code,head=command(['git','rev-parse','HEAD'],work,30)
    if code or head.strip()!=result.get('base_sha'): raise ValueError('Worktree HEAD changed since testing. Run a new check.')
    code,diff=command(['git','diff','--no-ext-diff','--no-color'],work,30)
    if code or not diff.strip() or hashlib.sha256(diff.encode()).hexdigest()!=result.get('verified_diff_sha'): raise ValueError('Diff is empty or changed after testing. Run a new check.')
    code,index=command(['git','diff','--cached','--name-only'],work,30)
    if code or index.strip(): raise ValueError('Index changed since testing. Inspect the worktree.')
    code,untracked=command(['git','ls-files','--others','--exclude-standard'],work,30)
    if code or untracked.strip(): raise ValueError('Untracked files found. Inspect them and run a new job before publishing.')
    code,remote=command(['git','remote','get-url','origin'],work,30)
    match=re.fullmatch(r'(?:https://github.com/|git@github.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?',remote.strip())
    if code or not match: raise ValueError('Origin must be a GitHub HTTPS or SSH repository without embedded credentials.')
    repo=match.group(1);gh=shutil.which('gh')
    if not gh: raise ValueError('Install GitHub CLI and run gh auth login first.')
    code,default=command([gh,'repo','view',repo,'--json','defaultBranchRef','--jq','.defaultBranchRef.name'],work,30)
    if code: raise ValueError('Cannot read the default branch. Check gh authentication.')
    print('Repository:',repo,'\nBranch:',result['branch'],'\nBase:',default.strip(),'\nDiff:\n',scrub(diff))
    print('This will commit the displayed tracked changes, push a new branch and create a draft PR.')
    if input('Type PUBLISH to continue: ').strip()!='PUBLISH': return
    record['publish_started']=True;save(receipt,record)
    commands=[['git','add','-u'],['git','commit','-m','ORA: reviewed desktop changes'],['git','push','--set-upstream','origin',result['branch']]]
    for argv in commands:
        code,out=command(argv,work,120)
        if code: raise RuntimeError('Publish stopped. Inspect local Git and GitHub before retrying. '+scrub(out))
    body=folder/'pr-body.md';body.write_text('Prepared in an ORA desktop worktree and approved locally.\n\nThe configured check passed before publication. Review the diff and repository CI before merging.\n',encoding='utf-8')
    code,out=command([gh,'pr','create','--repo',repo,'--draft','--head',result['branch'],'--base',default.strip(),'--title','ORA: reviewed desktop changes','--body-file',str(body)],work,60)
    if code: raise RuntimeError('Branch pushed; PR creation did not confirm success. Inspect GitHub before retrying. '+scrub(out))
    record['published']=out.strip();save(receipt,record);print(out)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='worker.local.json');parser.add_argument('--pair',action='store_true');parser.add_argument('--once',action='store_true');parser.add_argument('--publish',metavar='JOB_ID')
    args=parser.parse_args();config_path=Path(args.config).resolve();config=json.loads(config_path.read_text(encoding='utf-8'))
    if args.publish:
        publish(config_path.parent/'ora-worker-state',args.publish);return
    # keyring uses the operating system credential vault. No tokens in config or logs.
    import keyring
    account=hashlib.sha256(config['url'].encode()).hexdigest()
    if args.pair:
        import getpass
        result=api(config,'pair',{'code':getpass.getpass('One-time web pairing code: '),'label':config.get('label','My computer'),
            'repositories':{k:list(v['checks']) for k,v in config['repositories'].items()}})
        keyring.set_password(SERVICE,account,result['token']);print('Worker paired. Run again without --pair.');return
    token=keyring.get_password(SERVICE,account)
    if not token: raise ValueError('Pair this computer first with --pair.')
    state=config_path.parent/'ora-worker-state';state.mkdir(exist_ok=True)
    stopped=threading.Event()
    def heartbeat():
        while not stopped.wait(30):
            try: api(config,'heartbeat',{},token)
            except Exception: pass
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        while True:
            try:
                # Retry reports, never execution. Interrupted jobs need human review.
                for receipt in state.glob('*/receipt.json'):
                    record=json.loads(receipt.read_text())
                    if record.get('reported'):continue
                    result=record.get('result') or {'status':'needs_review','summary':'Worker stopped before recording a result. Inspect the local worktree. Job was not rerun.','diff':'','branch':''}
                    api(config,'report',{'job_id':record['id'],'claim':record['claim'],**result},token)
                    record['reported']=True;save(receipt,record)
                job=api(config,'poll',{},token).get('job')
                if job:
                    if not re.fullmatch('[a-f0-9]{32}',job['id']): raise ValueError('Invalid job ID.')
                    folder=state/job['id'];folder.mkdir(exist_ok=True);receipt=folder/'receipt.json'
                    if receipt.exists(): raise ValueError('Already recorded job; will not execute twice.')
                    record={'id':job['id'],'claim':job['claim']};save(receipt,record)
                    try: record['result']=execute(config,job,folder)
                    except Exception as exc: record['result']={'status':'needs_review','summary':'Local execution stopped. Inspect the computer before retrying. '+scrub(str(exc))[:1500],'diff':'','branch':''}
                    save(receipt,record)
                    api(config,'report',{'job_id':record['id'],'claim':record['claim'],**record['result']},token)
                    record['reported']=True;save(receipt,record)
                if args.once:break
            except urllib.error.HTTPError as exc:
                print('Backend returned HTTP',exc.code)
                if exc.code in (401,403): break
                if args.once: raise
            except (urllib.error.URLError,TimeoutError):
                print('Backend unavailable. Saved results will retry; completed jobs will not rerun.')
                if args.once:raise
            time.sleep(20)
    finally:stopped.set()


if __name__=='__main__': main()
