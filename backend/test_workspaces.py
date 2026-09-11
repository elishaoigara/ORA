import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_mini as fixtures
import next_api as api
from mini.workspaces import active_facts


class WorkTests(fixtures.MiniTests):
    # Inherited regression tests also exercise the upgraded API.
    def post(self,path,payload,auth=None):
        return self.client.post('/api/v2/'+path,headers=auth or self.owner,json=payload)
    def project(self,**kw):
        r=self.post('work/projects',dict(request_id=uuid4().hex,name='ORA',**kw));self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_project_conflict_idempotency_and_phone_sync(self):
        p=self.project(goal='Build a helpful companion')
        update=dict(p,request_id=uuid4().hex,next_step='Check notifications')
        self.assertEqual(self.post('work/projects',update).status_code,200)
        self.assertEqual(self.post('work/projects',update).status_code,200)
        update['request_id']=uuid4().hex
        self.assertEqual(self.post('work/projects',update).status_code,409)
        phone,_,_=self.phone()
        result=self.client.get('/api/v2/work',headers=phone).json()
        self.assertEqual(result['projects'][0]['next_step'],'Check notifications')
    def test_expiry_correction_forget(self):
        p=self.project();f=dict(request_id=uuid4().hex,project_id=p['id'],text='Old decision',source='Owner',expires_at='2020-01-01T00:00:00Z')
        r=self.post('work/facts',f);self.assertEqual(r.status_code,200,r.text);f=r.json()
        self.assertEqual(active_facts(api.db().read(),p['id']),[])
        f.update(expires_at=None,text='Corrected',request_id=uuid4().hex)
        r=self.post('work/facts',f);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(active_facts(api.db().read(),p['id'])[0]['text'],'Corrected')
        self.assertEqual(self.post('work/facts',dict(r.json(),deleted=True,request_id=uuid4().hex)).status_code,200)
        self.assertEqual(api.db().read()['project_facts'],[])
    def test_project_chat_context_and_document_selection(self):
        a=self.project();b=self.project()
        upload=self.client.post('/api/v2/work/attachments',headers=self.owner,data={'project_id':a['id']},files={'file':('trace.log',b'actual build error','text/plain')})
        self.assertEqual(upload.status_code,200,upload.text);doc=upload.json()
        with patch('next_api.respond',return_value=('Answer',[])) as respond:
            r=self.post('chat',dict(request_id=uuid4().hex,text='Explain',project_id=a['id'],document_ids=[doc['id']]))
            self.assertEqual(r.status_code,200,r.text)
            context=respond.call_args.args[0];self.assertEqual(context['active_project']['project']['id'],a['id'])
            self.assertEqual(context['documents'][0]['text'],'actual build error')
        self.assertEqual(self.post('chat',dict(request_id=uuid4().hex,text='Explain',project_id=b['id'],document_ids=[doc['id']])).status_code,422)
        phone,_,_=self.phone();history=self.client.get('/api/v2/work/projects/'+a['id']+'/resume',headers=phone).json()
        self.assertEqual(len(history['messages']),2)
    def test_image_analysis_saves_description_without_raw_image(self):
        with patch.dict(os.environ,{'GROQ_API_KEY':'fake-key','GROQ_VISION_MODEL':'test-vision'}), patch('mini.workspaces.requests.post') as call:
            call.return_value.json.return_value={'choices':[{'message':{'content':'The screenshot shows a compile error.'}}]}
            response=self.client.post('/api/v2/work/attachments',headers=self.owner,files={'file':('error.png',b'\x89PNG\r\n\x1a\nexample','image/png')})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['analysis_kind'],'ai_image_description')
            self.assertNotIn('base64',json.dumps(api.db().read()['documents']))
            self.assertEqual(api.db().read()['vision_usage']['count'],1)

    def test_image_disabled_and_oversize_rejected(self):
        with patch.dict(os.environ,{'GROQ_VISION_MODEL':''}):
            r=self.client.post('/api/v2/work/attachments',headers=self.owner,files={'file':('x.png',b'\x89PNG\r\n\x1a\nxxx','image/png')})
            self.assertEqual(r.status_code,503)
        r=self.client.post('/api/v2/work/attachments',headers=self.owner,files={'file':('x.txt',b'x'*(2*1024*1024+1),'text/plain')})
        self.assertEqual(r.status_code,413)
    def test_signed_webhook_dedup_and_allowlist(self):
        secret='x'*40
        with patch.dict(os.environ,{'ORA_GITHUB_WEBHOOK_SECRET':secret,'ORA_GITHUB_REPOS':'elishaoigara/ORA'}):
            self.project(repository='elishaoigara/ORA',github_alerts=True);self.phone()
            payload={'action':'completed','repository':{'full_name':'elishaoigara/ORA'},'workflow_run':{'name':'Android','conclusion':'failure','html_url':'https://github.com/elishaoigara/ORA/actions/runs/1'}}
            body=json.dumps(payload).encode();headers={'x-github-event':'workflow_run','x-github-delivery':uuid4().hex,'x-hub-signature-256':'sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()}
            for _ in range(2):self.assertEqual(self.client.post('/api/v2/work/github/webhook',headers=headers,content=body).status_code,200)
            state=api.db().read();self.assertEqual(len(state['github_events']),1);self.assertEqual(len(state['alerts']),1)
            self.assertEqual(self.client.post('/api/v2/work/github/webhook',headers=headers,content=body+b' ').status_code,401)
            payload['repository']['full_name']='other/private';body=json.dumps(payload).encode();headers.update({'x-github-delivery':uuid4().hex,'x-hub-signature-256':'sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()})
            self.assertEqual(self.client.post('/api/v2/work/github/webhook',headers=headers,content=body).status_code,403)
    def worker(self):
        code=self.post('desktop/pairing-code',{}).json()['code']
        r=self.post('desktop/pair',{'code':code,'label':'Test PC','repositories':{'ora':['check']}}).json()
        return r,{'Authorization':'Bearer '+r['token']}
    def test_worker_scope_claim_report_and_duplicate(self):
        p=self.project();w,auth=self.worker()
        self.assertEqual(self.client.get('/api/v2/sync',headers=auth).status_code,401)
        phone,_,_=self.phone()
        self.assertEqual(self.post('desktop/pairing-code',{},phone).status_code,403)
        job={'request_id':uuid4().hex,'worker_id':w['id'],'project_id':p['id'],'repository':'ora','check':'check'}
        self.assertEqual(self.post('desktop/jobs',job).status_code,200)
        self.assertEqual(self.post('desktop/jobs',job).status_code,200)
        j=self.post('desktop/poll',{},auth).json()['job'];self.assertTrue(j)
        self.assertIsNone(self.post('desktop/poll',{},auth).json()['job'])
        _,other=self.worker()
        report={'job_id':j['id'],'claim':j['claim'],'status':'passed','summary':'Tests passed'}
        self.assertEqual(self.post('desktop/report',report,other).status_code,403)
        for _ in range(2):self.assertEqual(self.post('desktop/report',report,auth).status_code,200)
        self.assertEqual(len(api.db().read()['desktop_jobs']),1)
        public=self.client.get('/api/v2/desktop',headers=self.owner).text
        self.assertNotIn(j['claim'],public);self.assertNotIn('token_hash',public)
        self.post('desktop/revoke',{'id':w['id']})
        self.assertEqual(self.post('desktop/poll',{},auth).status_code,401)
    def test_abandoned_worker_job_never_requeued(self):
        p=self.project();w,auth=self.worker();self.post('desktop/jobs',{'request_id':uuid4().hex,'worker_id':w['id'],'project_id':p['id'],'repository':'ora','check':'check'})
        self.post('desktop/poll',{},auth)
        api.db().mutate(lambda s:s['desktop_jobs'][0].update(claimed_at=0))
        self.assertIsNone(self.post('desktop/poll',{},auth).json()['job'])
        self.assertEqual(api.db().read()['desktop_jobs'][0]['status'],'needs_review')

if __name__=='__main__':unittest.main()
