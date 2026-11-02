import os
import unittest
from unittest.mock import patch, Mock
from fastapi import HTTPException
import requests
import test_mini as fixtures
import next_api as api
from mini.voice import transcribe_note, bounded_audio, speech
from mini.calls import call_owner, configured

class VoiceCallsTests(unittest.TestCase):
    setUp=fixtures.MiniTests.setUp
    tearDown=fixtures.MiniTests.tearDown

    def env(self):
        return patch.dict(os.environ, {'TWILIO_ACCOUNT_SID':'AC'+'a'*32, 'TWILIO_AUTH_TOKEN':'test-secret',
            'TWILIO_FROM_NUMBER':'+15550000001','ORA_CALL_PHONE_NUMBER':'+15550000002'})

    def setup_calls(self):
        api.store.mutate(lambda s:(s.update(telegram={'chat_id':123,'user_id':123}),s['settings'].update(quiet_start=0,quiet_end=0)))

    def test_call_single_recipient_xml_escape_and_no_duplicate(self):
        self.setup_calls()
        response=Mock(ok=True);response.json.return_value={'sid':'CA123'}
        with self.env(),patch('mini.calls.requests.post',return_value=response) as send:
            self.assertTrue(configured())
            self.assertEqual(call_owner(api.store,'once','Check A < B & C'),'accepted')
            self.assertEqual(call_owner(api.store,'once','Again'),'accepted')
            with self.assertRaises(HTTPException) as error:call_owner(api.store,'twice','Again')
            self.assertEqual(error.exception.status_code,429)
            send.assert_called_once();data=send.call_args.kwargs['data']
            self.assertEqual(data['To'],'+15550000002');self.assertIn('&lt; B &amp; C',data['Twiml'])
            self.assertEqual(data['Record'],'false');self.assertEqual(data['TimeLimit'],'90')
        self.assertNotIn('+1555',str(api.store.read()))

    def test_uncertain_call_is_not_redialed_and_quiet_hours_apply(self):
        self.setup_calls()
        with self.env(),patch('mini.calls.requests.post',side_effect=requests.Timeout('secret')) as send:
            self.assertEqual(call_owner(api.store,'once','Hi'),'unknown')
            self.assertEqual(call_owner(api.store,'once','Hi'),'unknown');send.assert_called_once()
        api.store.mutate(lambda s:s.pop('owner_call'))
        with self.env(),patch('mini.companion.quiet',return_value=True),patch('mini.calls.requests.post') as send:
            with self.assertRaises(HTTPException):call_owner(api.store,'quiet','Hi')
            send.assert_not_called()
        self.assertNotIn('owner_call',api.store.read())

    def test_scheduled_calls_require_optin(self):
        self.setup_calls()
        with self.env(),patch('mini.calls.requests.post') as send:
            with self.assertRaises(HTTPException):call_owner(api.store,'daily','Hi',scheduled=True)
            send.assert_not_called()

    def test_voice_download_bounds_and_path_validation(self):
        note={'file_id':'id','duration':5,'file_size':20}
        with patch.dict(os.environ,{'GROQ_API_KEY':'fake'}),patch('mini.telegram.bot_call',return_value={'file_path':'../secret'}),patch('mini.voice.requests.get') as fetch:
            with self.assertRaises(HTTPException):transcribe_note(note)
            fetch.assert_not_called()
            with self.assertRaises(HTTPException):transcribe_note(dict(note,duration=181))
        response=Mock();response.iter_content.return_value=[b'x'*10,b'y'*10]
        with self.assertRaises(ValueError):bounded_audio(response,15)

    def test_real_wav_to_opus_conversion_with_mock_groq(self):
        import io,wave
        data=io.BytesIO()
        with wave.open(data,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\0\0'*2400)
        response=Mock();response.iter_content.return_value=[data.getvalue()]
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'GROQ_API_KEY':'fake'}),patch('mini.voice.requests.post',return_value=response) as call:
            result=speech('Hello')
            self.assertTrue(result.startswith(b'OggS'))
            self.assertEqual(call.call_args.kwargs['json']['response_format'],'wav')
