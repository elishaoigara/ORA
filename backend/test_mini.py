"""Regression gates for auth, synchronization, proposals and durable mutations."""
import base64, json, os, tempfile, unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
os.environ['APP_ENV']='test'
os.environ['ORA_API_TOKEN']='test-key-not-a-secret'
from fastapi.testclient import TestClient
import next_api as api
from mini.store import Store, initial
from mini.intelligence import respond

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
class AIProviderTests(unittest.TestCase):
 def test_deepseek_chat_and_tool_round_trip(self):
  from unittest.mock import Mock
  tool_call={'id':'call-1','type':'function','function':{'name':'propose_task',
             'arguments':'{"title":"Plan launch","due_at":"","priority":2}'}}
  replies=[Mock(status_code=200,ok=True,json=lambda:{'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[tool_call]}}]}),
           Mock(status_code=200,ok=True,json=lambda:{'choices':[{'message':{'role':'assistant','content':'Please review the task.'}}]})]
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-deepseek-key','GROQ_API_KEY':'test-groq-key','ORA_AI_PROVIDER':''}):
   with patch('mini.intelligence.requests.post',side_effect=replies) as post:
    reply,proposals=respond(initial(),'Plan my launch')
   with patch.object(api,'db') as workspace:
    workspace.return_value.healthy.return_value=True
    self.assertEqual(api.health()['ai_provider'],'deepseek')
    self.assertTrue(api.health()['ai_configured'])
  self.assertEqual(reply,'Please review the task.')
  self.assertEqual(proposals[0]['kind'],'task')
  self.assertEqual(post.call_args_list[0].args[0],'https://api.deepseek.com/chat/completions')
  self.assertEqual(post.call_args_list[0].kwargs['json']['model'],'deepseek-flash')
  self.assertEqual(post.call_args_list[0].kwargs['json']['thinking'],{'type':'disabled'})
  self.assertEqual(post.call_args_list[1].kwargs['json']['messages'][-1]['tool_call_id'],'call-1')

 def test_explicit_provider_and_missing_key(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-deepseek-key','GROQ_API_KEY':'test-groq-key','ORA_AI_PROVIDER':'groq'}):
   from mini.intelligence import ai_provider
   self.assertEqual(ai_provider()['url'],'https://api.groq.com/openai/v1/chat/completions')
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'','GROQ_API_KEY':'test-groq-key','ORA_AI_PROVIDER':'deepseek'}):
   # The probe also checks storage; this test only asserts provider configuration.
   with patch.object(api,'db') as workspace:
    workspace.return_value.healthy.return_value=True
    self.assertFalse(api.health()['ai_configured'])
   with self.assertRaisesRegex(RuntimeError,'DEEPSEEK_API_KEY'):
    respond(initial(),'Hello')

 def test_rejected_deepseek_key_does_not_expose_secret(self):
  from unittest.mock import Mock
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'private-test-key','ORA_AI_PROVIDER':'deepseek'}):
   with patch('mini.intelligence.requests.post',return_value=Mock(status_code=401,ok=False)):
    with self.assertRaisesRegex(RuntimeError,'API key was rejected') as error:
     respond(initial(),'Hello')
  self.assertNotIn('private-test-key',str(error.exception))

class WhatsAppBridgeTests(unittest.TestCase):
    """The WhatsApp bridge shares the one free service, so its link must survive sleep.

    Render Free destroys the container (and its filesystem) after 15 minutes idle.
    These gates pin the two behaviours that make WhatsApp usable anyway: the
    linked-device credentials live in Postgres, and the bridge is only ever reached
    on loopback with the internal token.
    """

    setUp = MiniTests.setUp
    tearDown = MiniTests.tearDown
    state = MiniTests.state

    ENV_KEYS = ('WA_EMBEDDED', 'WA_SIDECAR_URL', 'WA_SIDECAR_PORT', 'WA_API_SECRET', 'ORA_INTERNAL_TOKEN')

    def setUp(self):
        MiniTests.setUp(self)
        self._env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)
        os.environ['ORA_INTERNAL_TOKEN'] = 'internal-token-for-tests-1234'
        os.environ['WA_API_SECRET'] = 'sidecar-secret-for-tests'
        self.bridge = {'X-ORA-Token': os.environ['ORA_INTERNAL_TOKEN']}

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        MiniTests.tearDown(self)

    @staticmethod
    def bundle():
        return base64.b64encode(json.dumps({'creds.json': '{}', 'pre-key-1.json': '{}'}).encode()).decode()

    def test_session_round_trip_survives_a_restart(self):
        url = '/api/whatsapp/session'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.put(url, json={'b64': self.bundle()}).status_code, 401)
        self.assertEqual(self.client.put(url, headers=self.bridge, json={'b64': 'not-a-bundle'}).status_code, 400)
        self.assertEqual(self.client.put(url, headers=self.bridge, json={'b64': self.bundle()}).status_code, 200)
        self.assertEqual(self.client.get(url, headers=self.bridge).json()['b64'], self.bundle())
        # Durable, not just cached in the running process.
        self.assertEqual(Store(url='', path=api.store.path).kv_get('whatsapp.session'), self.bundle())
        # Deleting needs bridge or owner credentials.
        self.assertEqual(self.client.request('DELETE', url).status_code, 401)
        self.assertEqual(self.client.request('DELETE', url, headers=self.bridge).status_code, 200)
        self.assertEqual(self.client.get(url, headers=self.bridge).status_code, 404)

    def test_session_never_reaches_a_client_snapshot(self):
        self.client.put('/api/whatsapp/session', headers=self.bridge, json={'b64': self.bundle()})
        sync = json.dumps(self.state())
        self.assertNotIn('creds.json', sync)
        self.assertNotIn(self.bundle()[:24], sync)
        self.assertNotIn('whatsapp', self.state())

    def test_session_backup_is_size_limited(self):
        oversized = base64.b64encode(json.dumps({'creds.json': 'x' * api.WA_SESSION_MAX_BYTES}).encode()).decode()
        self.assertEqual(self.client.put('/api/whatsapp/session', headers=self.bridge,
                                        json={'b64': oversized}).status_code, 400)

    def test_embedded_bridge_is_addressed_on_loopback(self):
        from mini import wa_bridge
        self.assertEqual(wa_bridge.sidecar_base(), '')
        with patch.dict(os.environ, {'WA_EMBEDDED': '1', 'WA_SIDECAR_PORT': '8080'}):
            self.assertEqual(wa_bridge.sidecar_base(), 'http://127.0.0.1:8080')
            self.assertTrue(wa_bridge.child_env()['ORA_BACKEND_URL'].startswith('http://127.0.0.1:'))
            # The bridge must never bind the port Render gave to the API.
            self.assertEqual(wa_bridge.child_env()['PORT'], '8080')
            # …and it must not inherit credentials it has no use for.
            child = wa_bridge.child_env()
            self.assertNotIn('DATABASE_URL', child)
            self.assertNotIn('ORA_API_TOKEN', child)
            self.assertIn('ORA_INTERNAL_TOKEN', child)
        with patch.dict(os.environ, {'WA_EMBEDDED': '1', 'WA_SIDECAR_URL': 'https://sidecar.example.com/'}):
            self.assertEqual(wa_bridge.sidecar_base(), 'https://sidecar.example.com')

    def test_mirror_switches_on_with_the_embedded_bridge(self):
        from mini import whatsapp
        with patch.dict(os.environ, {'ORA_WA_NOTIFY_NUMBER': '254700000000', 'WA_EMBEDDED': '1', 'WA_SIDECAR_URL': ''}):
            self.assertTrue(whatsapp.configured())
        with patch.dict(os.environ, {'ORA_WA_NOTIFY_NUMBER': '', 'WA_EMBEDDED': '1'}):
            self.assertFalse(whatsapp.configured())

    def test_status_is_disabled_without_a_bridge_and_private_with_one(self):
        self.assertEqual(self.client.get('/api/v2/whatsapp/status', headers=self.owner).json(),
                         {'enabled': False, 'linked': False, 'state': 'disabled'})
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), \
             patch('connectors.whatsapp.get_status', return_value={'ok': True, 'state': 'open', 'me': '254712345678'}):
            body = self.client.get('/api/v2/whatsapp/status', headers=self.owner).json()
        self.assertEqual(body, {'enabled': True, 'linked': True, 'state': 'open'})
        self.assertNotIn('254712345678', json.dumps(body))

    def test_pairing_page_requires_the_owner_key(self):
        self.assertEqual(self.client.get('/api/whatsapp/pairing').status_code, 401)
        self.assertEqual(self.client.get('/api/whatsapp/pairing?token=wrong').status_code, 401)
        self.assertEqual(self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN']).status_code, 503)

    def test_pairing_page_serves_the_qr_without_the_sidecar_secret(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'ok': True, 'state': 'connecting', 'linked': False,
                                   'qr': 'data:image/png;base64,AAAA'}
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), patch('requests.get', return_value=reply) as get:
            page = self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN'])
        self.assertEqual(page.status_code, 200)
        self.assertIn('data:image/png;base64,AAAA', page.text)
        self.assertNotIn(os.environ['WA_API_SECRET'], page.text)
        self.assertEqual(get.call_args.kwargs['headers']['x-api-secret'], os.environ['WA_API_SECRET'])

    def test_pairing_page_reports_a_linked_device(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'ok': True, 'state': 'open', 'linked': True, 'qr': None}
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), patch('requests.get', return_value=reply):
            page = self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN'])
        self.assertEqual(page.status_code, 200)
        self.assertIn('WhatsApp is linked', page.text)
        self.assertNotIn('http-equiv="refresh"', page.text)

    def test_pairing_page_offers_a_phone_number_code(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'ok': True, 'state': 'connecting', 'linked': False,
                                   'qr': None, 'code': 'ABCD-1234'}
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), patch('requests.get', return_value=reply):
            page = self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN'])
        self.assertEqual(page.status_code, 200)
        self.assertIn('ABCD-1234', page.text)
        self.assertIn('Link with phone number', page.text)

    def test_pairing_page_rejects_markup_from_the_bridge(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'ok': True, 'state': 'connecting', 'linked': False,
                                   'qr': 'javascript:alert(1)', 'code': '<script>alert(1)</script>'}
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), patch('requests.get', return_value=reply):
            page = self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN'])
        self.assertNotIn('javascript:', page.text)
        self.assertNotIn('<script>', page.text)

    def test_pairing_page_survives_a_bridge_that_is_still_booting(self):
        with patch.dict(os.environ, {'WA_EMBEDDED': '1'}), patch('requests.get', side_effect=OSError('refused')):
            page = self.client.get('/api/whatsapp/pairing?token=' + os.environ['ORA_API_TOKEN'])
        self.assertEqual(page.status_code, 503)
        self.assertIn('starting', page.json()['detail'].lower())


if __name__=='__main__':unittest.main()


# The Render Free budget gates live in their own module. Importing the classes
# here keeps the existing CI gate running them without editing the workflow file.
from test_free_tier import FreeTierTests, StoreEfficiencyTests  # noqa: E402,F401
