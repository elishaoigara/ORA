import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('worker',Path(__file__).with_name('worker.py'));worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)

class WorkerTests(unittest.TestCase):
    def test_path_guard_and_secret_redaction(self):
        for p in ['../escape','a/../../escape','.env','dir/.github/workflows/a.yml','secret.txt']:
            with self.assertRaises(ValueError):worker.safe_patch(f'--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-a\n+b\n')
        worker.safe_patch('--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-a\n+b\n')
        self.assertNotIn('ghp_abcdef',worker.scrub('token=hello ghp_abcdef'))
        self.assertNotIn('hello',worker.scrub('token=hello'))
    def test_real_git_worktree_patch_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo';root.mkdir();folder=Path(tmp)/'job';folder.mkdir()
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.STDOUT).decode().strip()
            git('init');git('config','user.email','test@example.com');git('config','user.name','ORA Test')
            (root/'answer.txt').write_text('old\n');git('add','answer.txt');git('commit','-m','initial')
            head=git('rev-parse','HEAD')
            job={'id':'a'*32,'repository':'test','check':'verify','base_sha':head,'patch':'diff --git a/answer.txt b/answer.txt\n--- a/answer.txt\n+++ b/answer.txt\n@@ -1 +1 @@\n-old\n+new\n'}
            config={'repositories':{'test':{'path':str(root),'checks':{'verify':[sys.executable,'-c',"from pathlib import Path; assert Path('answer.txt').read_text()=='new\\n'; print('verified')"]}}}}
            with patch('builtins.input',side_effect=['RUN','SHARE']):result=worker.execute(config,job,folder)
            self.assertEqual(result['status'],'passed');self.assertIn('verified',result['summary']);self.assertIn('+new',result['diff'])
            self.assertEqual((root/'answer.txt').read_text(),'old\n')
            self.assertEqual(git('rev-parse','HEAD'),head)
            self.assertTrue((folder/'worktree'/'answer.txt').exists())
    def test_declined_job_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config={'repositories':{'x':{'path':tmp,'checks':{'check':[sys.executable,'-c','raise Exception()']}}}}
            with patch.object(worker,'command',return_value=(0,'a'*40)),patch('builtins.input',return_value='NO'):
                result=worker.execute(config,{'repository':'x','check':'check','id':'b'*32},Path(tmp))
            self.assertEqual(result['status'],'declined')
    def test_changed_base_stops_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            config={'repositories':{'x':{'path':tmp,'checks':{'check':['python']}}}}
            with patch.object(worker,'command',return_value=(0,'a'*40)),self.assertRaises(ValueError):
                worker.execute(config,{'repository':'x','check':'check','base_sha':'b'*40},Path(tmp))

if __name__=='__main__':unittest.main()
