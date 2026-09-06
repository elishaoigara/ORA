import time
import unittest
from unittest.mock import patch
import test_mini as fixtures
from mini.companion import alert, dispatch, weather_check
import next_api as api

class CompanionTests(unittest.TestCase):
 setUp=fixtures.MiniTests.setUp
 tearDown=fixtures.MiniTests.tearDown
 op=fixtures.MiniTests.op
 state=fixtures.MiniTests.state
 phone=fixtures.MiniTests.phone
 def test_scope_and_token_redaction(self):
  phone,_,_=self.phone()
  self.assertEqual(self.op('companion.push',{'token':'ExpoPushToken[abcdefghijk123]'},phone).status_code,200)
  text=str(self.state(phone));self.assertNotIn('abcdefghijk123',text)
  self.assertTrue(self.state(phone)['devices'][0]['push_registered'])
  self.assertEqual(self.op('companion.push',{'token':'bad'},phone).status_code,422)
  self.assertEqual(self.op('companion.push',{'token':'ExpoPushToken[abcdefghijk123]'}).status_code,403)
 def test_weather_consent_and_disable(self):
  phone,_,_=self.phone();p=dict(enabled=True,latitude=-1.29,longitude=36.82,source='location',label='Area',rain=60,heat=32,wind=40)
  self.assertEqual(self.op('companion.weather',p,phone).status_code,403)
  p['source']='city';self.assertEqual(self.op('companion.weather',p,phone).status_code,200)
  d=api.db().read()['devices'][0]['id']
  fake=dict(date='2026-09-06',temperature_2m_min=15,temperature_2m_max=34,precipitation_probability_max=80,wind_speed_10m_max=20,uv_index_max=9,fetched_at=time.time())
  with patch('mini.companion.forecast',return_value=fake) as f, patch('mini.companion.quiet', return_value=False):
   weather_check(api.db(),d);weather_check(api.db(),d);self.assertEqual(f.call_count,1)
  self.assertEqual(len(self.state(phone)['alerts']),1)
  self.op('companion.weather',{'enabled':False},phone)
  self.assertNotIn('weather',api.db().read()['devices'][0])
 def test_delivery_invalid_token_and_dedup(self):
  phone,_,_=self.phone();self.op('companion.push',{'token':'ExpoPushToken[abcdefghijk123]'},phone)
  d=api.db().read()['devices'][0]['id']
  def add(s):
   s['settings'].update(quiet_start=0,quiet_end=0)
   alert(s,d,'same','Title','Body','alerts');alert(s,d,'same','Title','Body','alerts')
  api.db().mutate(add)
  with patch('mini.companion.expo',return_value={'status':'error','details':{'error':'DeviceNotRegistered'}}):dispatch(api.db())
  state=api.db().read();self.assertEqual(len(state['alerts']),1);self.assertEqual(state['alerts'][0]['delivery'],'failed');self.assertNotIn('push_token',state['devices'][0])
 def test_recurring_and_edit_conflict(self):
  task=self.op('task.create',{'title':'Daily','due_at':'2026-01-01T09:00:00+00:00','repeat':'daily'}).json()
  self.op('task.complete',{'id':task['id'],'version':1})
  t=self.state()['tasks'][0];self.assertFalse(t['done']);self.assertEqual(t['version'],2)
  self.assertEqual(self.op('task.update',{'id':t['id'],'version':1,'title':'Changed'}).status_code,409)
 def test_cron_requires_separate_secret(self):
  self.assertEqual(self.client.post('/api/companion/tick',headers=self.owner).status_code,401)
 def test_push_ticket_receipt_and_transport_retry(self):
  phone,_,_=self.phone();self.op('companion.push',{'token':'ExpoPushToken[abcdefghijk123]'},phone)
  def seed(s):
   s['settings'].update(quiet_start=0,quiet_end=0)
   alert(s,s['devices'][0]['id'],'receipt','Title','Body','alerts')
  api.db().mutate(seed)
  with patch('mini.companion.expo',return_value={'status':'ok','id':'ticket-1'}):dispatch(api.db())
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'ticket')
  api.db().mutate(lambda s:s['alerts'][0].update(retry_at=0))
  import requests
  with patch('mini.companion.expo',side_effect=requests.Timeout()):dispatch(api.db())
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'ticket')
  api.db().mutate(lambda s:s['alerts'][0].update(retry_at=0))
  with patch('mini.companion.expo',return_value={'ticket-1':{'status':'ok'}}):dispatch(api.db())
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'provider_accepted')
