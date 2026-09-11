"""Paired desktop queue. Worker tokens can only claim and report their own jobs."""
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Literal
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, Field
from mini.store import now
from mini.workspaces import project_for


def hashed(value): return hashlib.sha256(value.encode()).hexdigest()


class PairWorker(BaseModel):
    code: str = Field(min_length=16, max_length=100)
    label: str = Field(min_length=1, max_length=80)
    repositories: dict[str, list[str]] = Field(max_length=20)


class Job(BaseModel):
    request_id: str = Field(min_length=16, max_length=100)
    worker_id: str = Field(max_length=100)
    project_id: str = Field(max_length=100)
    repository: str = Field(min_length=1, max_length=80)
    check: str = Field(min_length=1, max_length=80)
    patch: str = Field(default='', max_length=60000)
    base_sha: str = Field(default='', max_length=40)


class Report(BaseModel):
    job_id: str = Field(max_length=100)
    claim: str = Field(max_length=100)
    status: Literal['passed', 'failed', 'declined', 'needs_review']
    summary: str = Field(max_length=30000)
    diff: str = Field(default='', max_length=60000)
    branch: str = Field(default='', max_length=120)


class Id(BaseModel):
    id: str = Field(max_length=100)


def public(w):
    return {k: v for k, v in w.items() if k not in ('token_hash', 'expires') } | {'online': w.get('last_seen', 0) > time.time()-90 and not w.get('revoked')}


def install(app, db, identity, owner, limited):
    def worker(authorization: str = Header(default='')):
        token = authorization.removeprefix('Bearer ').strip()
        if not token: raise HTTPException(401, 'Worker token required.')
        w = next((w for w in db().read().get('workers', []) if not w.get('revoked') and w['expires'] > time.time() and hmac.compare_digest(w['token_hash'], hashed(token))), None)
        if not w: raise HTTPException(401, 'Worker pairing expired or revoked.')
        return w

    @app.get('/api/v2/desktop')
    def dashboard(auth=Depends(identity)):
        s = db().read()
        return {'workers': [public(w) for w in s.get('workers', [])],
                'jobs': [{k: v for k, v in j.items() if k not in ('claim', 'patch', 'diff', 'summary')} | {'summary': j.get('summary','')[:400], 'has_result': j['status'] not in ('queued','running')} for j in s.get('desktop_jobs', [])][-40:]}

    @app.get('/api/v2/desktop/jobs/{job_id}')
    def result(job_id: str, auth=Depends(identity)):
        j=next((j for j in db().read().get('desktop_jobs',[]) if j['id']==job_id),None)
        if not j: raise HTTPException(404,'Job not found.')
        return {k:v for k,v in j.items() if k not in ('claim','patch')}

    @app.post('/api/v2/desktop/pairing-code')
    def code(auth=Depends(owner)):
        def save(s):
            value = secrets.token_urlsafe(24)
            s['worker_pairing'] = {'hash': hashed(value), 'expires': time.time()+600}
            return {'code': value, 'expires_in': 600}
        return db().mutate(save)

    @app.post('/api/v2/desktop/pair')
    def pair(p: PairWorker):
        limited('worker-pair', 5)
        if any(len(k)>80 or len(v)>20 or any(len(c)>80 for c in v) for k,v in p.repositories.items()):
            raise HTTPException(422, 'Too many repositories or checks.')
        def save(s):
            code = s.get('worker_pairing', {})
            if code.get('expires', 0) < time.time() or not hmac.compare_digest(code.get('hash',''), hashed(p.code)):
                raise HTTPException(401, 'Pairing code is invalid or expired.')
            ws = s.setdefault('workers', [])
            if len([w for w in ws if not w.get('revoked')]) >= 5: raise HTTPException(400, 'Revoke an old worker first.')
            token = secrets.token_urlsafe(40)
            row = {'id': uuid.uuid4().hex, 'label': p.label, 'repositories': p.repositories, 'token_hash': hashed(token), 'expires': time.time()+90*86400, 'last_seen': time.time(), 'revoked': False}
            ws.append(row)
            s.pop('worker_pairing', None)
            return {'id': row['id'], 'token': token}
        return db().mutate(save)

    @app.post('/api/v2/desktop/revoke')
    def revoke(p: Id, auth=Depends(owner)):
        def save(s):
            for w in s.get('workers', []):
                if w['id'] == p.id: w['revoked'] = True
            for j in s.get('desktop_jobs', []):
                if j['worker_id'] == p.id and j['status'] in ('queued', 'running'): j.update(status='needs_review', summary='Worker revoked. Check the computer before retrying.')
            return {'ok': True}
        return db().mutate(save)

    @app.post('/api/v2/desktop/jobs')
    def enqueue(p: Job, auth=Depends(identity)):
        def save(s):
            project_for(s, p.project_id)
            w = next((w for w in s.get('workers', []) if w['id'] == p.worker_id and not w.get('revoked') and w['expires'] > time.time()), None)
            if not w or p.check not in w['repositories'].get(p.repository, []): raise HTTPException(422, 'Select a paired repository and check.')
            if p.patch and (len(p.base_sha)!=40 or any(c not in '0123456789abcdef' for c in p.base_sha)):
                raise HTTPException(422, 'A patch requires its full 40-character Git base SHA.')
            jobs = s.setdefault('desktop_jobs', [])
            if len([j for j in jobs if j['status'] in ('queued','running')]) >= 10: raise HTTPException(429, 'Ten jobs are already waiting or running.')
            row = p.model_dump(exclude={'request_id'}) | {'id': uuid.uuid4().hex, 'status': 'queued', 'created_at': now(), 'summary': 'Waiting for the computer and local approval.'}
            jobs.append(row)
            # Never prune uncompleted jobs.
            completed = [j for j in jobs if j['status'] not in ('queued','running')][-40:]
            s['desktop_jobs'] = completed + [j for j in jobs if j['status'] in ('queued','running')]
            return {'id': row['id'], 'status': row['status']}
        return db().mutate(save, 'desktop:'+auth['id']+':'+p.request_id)

    @app.post('/api/v2/desktop/cancel')
    def cancel(p: Id, auth=Depends(identity)):
        def save(s):
            j = next((j for j in s.get('desktop_jobs',[]) if j['id']==p.id),None)
            if not j: raise HTTPException(404,'Job not found.')
            if j['status']!='queued': raise HTTPException(409,'Only a queued job can be cancelled. Stop a running job on the computer.')
            j.update(status='declined',summary='Cancelled before execution.')
            return {'ok':True}
        return db().mutate(save)

    @app.post('/api/v2/desktop/poll')
    def poll(w=Depends(worker)):
        def claim(s):
            current=next(x for x in s['workers'] if x['id']==w['id'])
            if current.get('revoked'): raise HTTPException(401,'Worker revoked.')
            current['last_seen']=time.time()
            jobs=s.get('desktop_jobs',[])
            for j in jobs:
                if j['worker_id']==w['id'] and j['status']=='running':
                    if j['claimed_at']<time.time()-3600: j.update(status='needs_review',summary='Worker did not report within one hour. Inspect local evidence; this job will not rerun automatically.')
                    else: return {'job':None}
            j=next((j for j in jobs if j['worker_id']==w['id'] and j['status']=='queued'),None)
            if j:
                j.update(status='running',claim=secrets.token_urlsafe(24),claimed_at=time.time(),summary='Awaiting local approval or running on the computer.')
                return {'job':dict(j)}
            return {'job':None}
        return db().mutate(claim)

    @app.post('/api/v2/desktop/heartbeat')
    def heartbeat(w=Depends(worker)):
        def save(s):
            next(x for x in s['workers'] if x['id']==w['id'])['last_seen']=time.time()
            return {'ok':True}
        return db().mutate(save)

    @app.post('/api/v2/desktop/report')
    def report(p: Report,w=Depends(worker)):
        def save(s):
            j=next((j for j in s.get('desktop_jobs',[]) if j['id']==p.job_id and j['worker_id']==w['id']),None)
            current=next(x for x in s['workers'] if x['id']==w['id'])
            if current.get('revoked') or not j or not hmac.compare_digest(j.get('claim',''),p.claim): raise HTTPException(403,'Invalid claim.')
            if j['status'] not in ('running','needs_review'): return {'ok':True,'duplicate':True}
            j.update(status=p.status,summary=p.summary,diff=p.diff,branch=p.branch,finished_at=now())
            j.pop('patch',None)
            return {'ok':True}
        return db().mutate(save)
