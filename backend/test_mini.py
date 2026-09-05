"""Regression gates for auth, synchronization, proposals and durable mutations."""
import os, tempfile, unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
os.environ['APP_ENV']='test'
os.environ['ORA_API_TOKEN']='test-key-not-a-secret'
from fastapi.testclient import TestClient
import next_api as api
from mini.store import Store

class MiniTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();api.store=Store(url='',path=self.temp.name+'/db');api.rates.clear();self.client=TestClient(api.app)
  self.owner={'Authorization':'Bearer '+self.client.post('/api/v2/session',json={'token':os.environ['ORA_API_TOKEN']}).json()['token']}
 def tearDown(self):self.temp.cleanup()
 def op(self,kind,payload,auth=None,rid=None):return self.client.post('/api/v2/operations',headers=auth or self.owner,json={'kind':kind,'payload':payload,'request_id':rid or uuid4().hex})
 def state(self,auth=None):return self.client.get('/api/v2/sync',headers=auth or self.owner).json()
 def phone(self):
  code=self.client.post('/api/v2/pairing-code',headers=self.owner).json()['code'];r=self.client.post('/api/v2/pair',json={'code':code}).json()
  return {'Authorization':'Bearer '+r['token']},r['device_id'],code
 def test_auth_and_no_credentials_in_sync(self):
  self.assertEqual(self.client.get('/api/v2/sync').status_code,401)
  self.assertEqual(self.client.get('/api/v2/sync',headers={'Authorization':'Bearer '+os.environ['ORA_API_TOKEN']}).status_code,401)
  self.assertNotIn('sessions',self.state());self.assertNotIn('pairing',self.state())
 def test_one_time_pairing_and_owner_boundary(self):
  phone,_,code=self.phone()
  self.assertEqual(self.client.post('/api/v2/pair',json={'code':code}).status_code,400)
  self.assertEqual(self.client.post('/api/v2/pairing-code',headers=phone).status_code,403)
 def test_device_cannot_revoke_another_device(self):
  phone,device_id,_=self.phone();other,other_id,_=self.phone()
  self.assertEqual(self.op('device.revoke',{'id':other_id},phone).status_code,403)
  self.op('device.revoke',{'id':device_id})
  self.assertEqual(self.client.get('/api/v2/sync',headers=phone).status_code,401)
  self.assertEqual(self.client.get('/api/v2/sync',headers=other).status_code,200)
 def test_duplicate_mutation_sync_and_conflict(self):
  phone,_,_=self.phone();rid=uuid4().hex
  for _ in range(2):self.assertEqual(self.op('task.create',{'title':'Ship ORA','priority':3},rid=rid).status_code,200)
  tasks=self.state(phone)['tasks'];self.assertEqual(len(tasks),1)
  self.assertEqual(self.op('task.complete',{'id':tasks[0]['id'],'version':1},phone).status_code,200)
  self.assertEqual(self.op('task.complete',{'id':tasks[0]['id'],'version':1}).status_code,409)
 def test_consent_pause_redaction_and_deletion(self):
  phone,_,_=self.phone()
  def event():return self.client.post('/api/v2/events',headers=phone,json={'request_id':uuid4().hex,'kind':'notifications','text':'OTP 123456','observed_at':datetime.now(timezone.utc).isoformat()})
  self.assertEqual(event().status_code,403)
  self.op('device.permissions',{'permission':'notifications','enabled':True},phone);self.assertEqual(event().status_code,200)
  self.assertNotIn('123456',self.state()['events'][0]['text'])
  self.op('device.pause',{'paused':True},phone);self.assertEqual(event().status_code,403)
  self.op('events.delete',{},phone);self.assertEqual(self.state()['events'],[])
 def test_chat_proposes_and_approval_is_idempotent(self):
  rid=uuid4().hex
  with patch.object(api,'respond',return_value=('Review this reminder.',[{'kind':'task','payload':{'title':'Call home','due_at':'2030-09-05T18:00:00+03:00','priority':2}}])) as model:
   for _ in range(2):self.assertEqual(self.client.post('/api/v2/chat',headers=self.owner,json={'request_id':rid,'text':'Remind me to call home.'}).status_code,200)
   model.assert_called_once()
  state=self.state();self.assertEqual(len(state['messages']),2);self.assertEqual(state['tasks'],[])
  for _ in range(2):self.op('action.approve',{'id':state['actions'][0]['id']})
  self.assertEqual(len(self.state()['tasks']),1);self.assertEqual(self.state()['tasks'][0]['due_at'],'2030-09-05T15:00:00+00:00')
 def test_expired_action_cannot_execute(self):
  api.store.mutate(lambda s:s['actions'].append({'id':'old','kind':'memory','payload':{'text':'old'},'status':'pending','expires_at':'2000-01-01T00:00:00+00:00'}))
  self.assertEqual(self.op('action.approve',{'id':'old'}).json()['status'],'expired');self.assertEqual(self.state()['memories'],[])
 def test_ai_failure_does_not_claim_success(self):
  with patch.object(api,'respond',side_effect=RuntimeError('Provider unavailable')):
   r=self.client.post('/api/v2/chat',headers=self.owner,json={'request_id':uuid4().hex,'text':'Hello'})
  self.assertEqual(r.status_code,503);self.assertEqual(self.state()['messages'],[])
 def test_persistence_and_concurrent_duplicate(self):
  def apply(s):s['memories'].append({'text':'once'});return {'ok':True}
  with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda _:api.store.mutate(apply,'same-request'),range(5)))
  self.assertEqual(len(Store(url='',path=api.store.path).read()['memories']),1)
 def test_validation(self):
  self.assertEqual(self.op('task.create',{'title':'Test','due_at':'2030-01-01T10:00:00'}).status_code,422)
  phone,_,_=self.phone();self.assertEqual(self.op('device.permissions',{'permission':'anything','enabled':True},phone).status_code,422)
 def test_legacy_import_is_read_only_and_only_trusts_confirmed_facts(self):
  import sqlite3
  from migrate_legacy import read_legacy
  path=self.temp.name+'/old.db'
  with sqlite3.connect(path) as conn:
   conn.execute('CREATE TABLE learned_facts(id INTEGER, subject TEXT, predicate TEXT, object TEXT, status TEXT)')
   conn.execute("INSERT INTO learned_facts VALUES (1,'Elisha','prefers','concise responses','confirmed')")
   conn.execute("INSERT INTO learned_facts VALUES (2,'Elisha','likes','unconfirmed guess','candidate')")
  data=read_legacy(path)
  self.assertEqual([m['text'] for m in data['memories']],['Elisha prefers concise responses'])
  with sqlite3.connect(path) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM learned_facts').fetchone()[0],2)
 def test_production_refuses_sqlite(self):
  with patch.dict(os.environ,{'APP_ENV':'production'}):
   with self.assertRaises(RuntimeError):Store(url='',path=self.temp.name+'/unsafe')
 def test_document_export(self):
  r=self.client.post('/api/v2/documents',headers=self.owner,files={'file':('plan.md',b'# ORA\nBuild deliberately.','text/markdown')})
  self.assertEqual(r.status_code,200);self.assertNotIn('text',self.state()['documents'][0])
  self.assertIn('Build deliberately',self.client.get('/api/v2/export',headers=self.owner).json()['documents'][0]['text'])
if __name__=='__main__':unittest.main()
