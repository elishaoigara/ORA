"""Optional, owner-only spoken phone briefings. No automatic redial."""
import os
import re
import time
from xml.sax.saxutils import escape

import requests
from fastapi import HTTPException


def configured():
    return bool(re.fullmatch(r'AC[0-9a-fA-F]{32}', os.getenv('TWILIO_ACCOUNT_SID', ''))
                and os.getenv('TWILIO_AUTH_TOKEN')
                and all(re.fullmatch(r'\+[1-9][0-9]{7,14}', os.getenv(k, ''))
                        for k in ('TWILIO_FROM_NUMBER', 'ORA_CALL_PHONE_NUMBER')))


def call_owner(store, request_id, text, scheduled=False):
    from mini.companion import quiet
    if not configured():
        raise HTTPException(409, 'Phone calls need TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER and ORA_CALL_PHONE_NUMBER on Render. Set the destination to your own number.')
    def claim(s):
        telegram = s.get('telegram', {})
        if not telegram.get('chat_id') or not telegram.get('user_id'):
            raise HTTPException(403, 'Pair your private Telegram account first.')
        if scheduled and not telegram.get('daily_calls'):
            raise HTTPException(409, 'Daily calls are disabled.')
        if quiet(s['settings']):
            raise HTTPException(409, 'Calls are paused during your quiet hours.')
        previous = s.get('owner_call', {})
        if previous.get('request_id') == request_id:
            return False
        if previous.get('at', 0) > time.time()-86400:
            raise HTTPException(429, 'ORA permits at most one call attempt per 24 hours. No automatic redial.')
        s['owner_call'] = {'request_id': request_id, 'at': time.time(), 'status': 'submitting'}
        return True
    if not store.mutate(claim):
        return store.read()['owner_call']['status']
    status = 'unknown'
    try:
        account = os.environ['TWILIO_ACCOUNT_SID']
        response = requests.post('https://api.twilio.com/2010-04-01/Accounts/' + account + '/Calls.json',
            auth=(account, os.environ['TWILIO_AUTH_TOKEN']),
            data={'To': os.environ['ORA_CALL_PHONE_NUMBER'], 'From': os.environ['TWILIO_FROM_NUMBER'],
                  'Twiml': '<Response><Say>' + escape(('Hello, this is ORA, your AI assistant. ' + text)[:1000]) + '</Say><Hangup/></Response>',
                  'Timeout': '20', 'TimeLimit': '90', 'Record': 'false'}, timeout=(5, 20))
        if response.ok and isinstance(response.json().get('sid'), str):
            status = 'accepted'
        elif not response.ok:
            status = 'rejected'
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass  # A timeout may have placed a call. Do not retry or expose credentials.
    store.mutate(lambda s: s['owner_call'].update(status=status))
    return status
