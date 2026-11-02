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
 def link(self):
  phone,device_id,_=self.phone()
  api.db().mutate(lambda s:s.update(telegram={'chat_id':12345,'user_id':12345}))
  with patch('mini.telegram.token',return_value='test-bot'), patch('mini.companion.token',return_value='test-bot'):
   self.assertEqual(self.op('companion.telegram',{'enabled':True},phone).status_code,200)
  return phone,device_id
 def test_scope_and_token_redaction(self):
  phone,d=self.link()
  state=self.state(phone)
  self.assertTrue(state['devices'][0]['telegram_alerts_enabled'])
  self.assertNotIn('12345',str(state))
  self.assertEqual(self.op('companion.telegram',{'enabled':True}).status_code,403)
  self.assertEqual(self.op('companion.telegram',{'enabled':'yes'},phone).status_code,422)
  self.assertEqual(self.op('companion.push',{'token':'ExpoPushToken[abcdefghijk123]'},phone).status_code,410)
  self.op('companion.telegram',{'enabled':False},phone)
  self.assertFalse(self.state(phone)['devices'][0]['telegram_alerts_enabled'])
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
 def test_delivery_retry_dedup_and_privacy(self):
  phone,d=self.link()
  def add(s):
   s['settings'].update(quiet_start=0,quiet_end=0)
   alert(s,d,'same','Sensitive title','Sensitive body','alerts');alert(s,d,'same','Title','Body','alerts')
  api.db().mutate(add)
  from fastapi import HTTPException
  with patch('mini.companion.token',return_value='bot'), patch('mini.companion.bot_call',side_effect=HTTPException(503,'secret-url')):
   dispatch(api.db())
  state=api.db().read();self.assertEqual(len(state['alerts']),1);self.assertEqual(state['alerts'][0]['delivery'],'retry')
  self.assertNotIn('secret-url',str(self.state(phone)))
  api.db().mutate(lambda s:s['alerts'][0].update(retry_at=0))
  with patch('mini.companion.token',return_value='bot'), patch('mini.companion.bot_call',return_value={'message_id':9}) as send:
   dispatch(api.db());dispatch(api.db())
   send.assert_called_once()
   self.assertNotIn('Sensitive',str(send.call_args))
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'sent_to_telegram')
 def test_recurring_and_edit_conflict(self):
  task=self.op('task.create',{'title':'Daily','due_at':'2026-01-01T09:00:00+00:00','repeat':'daily'}).json()
  self.op('task.complete',{'id':task['id'],'version':1})
  t=self.state()['tasks'][0];self.assertFalse(t['done']);self.assertEqual(t['version'],2)
  self.assertEqual(self.op('task.update',{'id':t['id'],'version':1,'title':'Changed'}).status_code,409)
 def test_cron_requires_separate_secret(self):
  self.assertEqual(self.client.post('/api/companion/tick',headers=self.owner).status_code,401)
 def test_quiet_hours_optout_expiry_and_old_expo_jobs(self):
  phone,d=self.link()
  api.db().mutate(lambda s:alert(s,d,'quiet','Title','Body','alerts'))
  with patch('mini.companion.token',return_value='bot'), patch('mini.companion.quiet',return_value=True), patch('mini.companion.bot_call') as send:
   dispatch(api.db());send.assert_not_called()
  self.op('companion.telegram',{'enabled':False},phone)
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'cancelled')
  def old(s):
   a=s['alerts'][0];a.update(delivery='pending');a.pop('transport')
  api.db().mutate(old)
  with patch('mini.companion.bot_call') as send:
   dispatch(api.db());send.assert_not_called()
  self.assertEqual(api.db().read()['alerts'][0]['delivery'],'retired')
 def test_relink_does_not_redirect_queued_private_alert(self):
  phone,d=self.link()
  def queue(s):
   s['settings'].update(quiet_start=0,quiet_end=0)
   alert(s,d,'new','Private','Details','alerts')
   s['telegram']['chat_id']=999
  api.db().mutate(queue)
  with patch('mini.companion.token',return_value='bot'), patch('mini.companion.bot_call') as send:
   dispatch(api.db());send.assert_not_called()
  self.assertFalse(self.state(phone)['devices'][0]['telegram_alerts_enabled'])
 def test_expired_and_exhausted_jobs_do_not_send(self):
  phone,d=self.link()
  def queue(s):
   s['settings'].update(quiet_start=0,quiet_end=0)
   alert(s,d,'expired','Title','Body','alerts');s['alerts'][-1]['expires']=0
   alert(s,d,'exhausted','Title','Body','alerts');s['alerts'][-1].update(attempts=5,delivery='sending',retry_at=0)
  api.db().mutate(queue)
  with patch('mini.companion.token',return_value='bot'), patch('mini.companion.bot_call') as send:
   dispatch(api.db());send.assert_not_called()
  self.assertEqual([a['delivery'] for a in api.db().read()['alerts']],['expired','failed'])
