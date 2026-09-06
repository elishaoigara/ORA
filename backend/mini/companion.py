"""Bounded weather checks and durable Expo push delivery; invoked by external cron."""
import os
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests


def quiet(settings, stamp=None):
    hour = datetime.fromtimestamp(stamp or time.time(), ZoneInfo(settings.get('timezone', 'Africa/Nairobi'))).hour
    start, end = settings.get('quiet_start', 22), settings.get('quiet_end', 7)
    return (start <= hour < end) if start < end else (hour >= start or hour < end) if start != end else False


def alert(state, device_id, key, title, body, category='weather'):
    rows = state.setdefault('alerts', [])
    rows[:] = [a for a in rows if a['created'] > time.time() - 30 * 86400][-499:]
    if any(a['key'] == key and a['device_id'] == device_id for a in rows):
        return
    rows.append(dict(id=uuid.uuid4().hex, device_id=device_id, key=key, title=title, body=body,
                     category=category, created=time.time(), expires=time.time()+86400,
                     read=False, delivery='pending', attempts=0, retry_at=0))


def forecast(latitude, longitude):
    response = requests.get('https://api.open-meteo.com/v1/forecast', params={
        'latitude': latitude, 'longitude': longitude, 'timezone': 'auto', 'forecast_days': 1,
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,uv_index_max',
    }, timeout=12)
    response.raise_for_status()
    d = response.json()['daily']
    return {k: d[k][0] for k in d if k != 'time'} | {'date': d['time'][0], 'fetched_at': time.time(), 'source': 'Open-Meteo'}


def weather_check(db, device_id):
    state = db.read()
    device = next((d for d in state['devices'] if d['id'] == device_id), {})
    prefs = device.get('weather', {})
    if device.get('revoked') or device.get('paused') or not prefs.get('enabled'):
        return None
    if prefs.get('source') == 'location' and (not device.get('permissions', {}).get('location') or prefs.get('updated', 0) < time.time()-86400):
        return None
    cached = device.get('forecast')
    if cached and cached.get('fetched_at', 0) > time.time()-3600:
        return cached
    result = forecast(prefs['latitude'], prefs['longitude'])
    def save(s):
        d = next((d for d in s['devices'] if d['id'] == device_id), {})
        if d.get('weather') != prefs or d.get('revoked') or d.get('paused'):
            return
        d['forecast'] = result
        parts = []
        if (result.get('precipitation_probability_max') or 0) >= prefs.get('rain', 60): parts.append('Rain is likely; carry an umbrella.')
        if (result.get('temperature_2m_max') or 0) >= prefs.get('heat', 32): parts.append('A hot day is forecast; plan shade and water.')
        if (result.get('wind_speed_10m_max') or 0) >= prefs.get('wind', 40): parts.append('Strong winds are forecast.')
        if (result.get('uv_index_max') or 0) >= 8: parts.append('Very high UV is forecast; consider sun protection.')
        summary = f"{prefs.get('label', 'Your area')}: {result['temperature_2m_min']}–{result['temperature_2m_max']}°C. Rain chance {result['precipitation_probability_max']}%."
        local = datetime.now(ZoneInfo(s['settings'].get('timezone', 'Africa/Nairobi')))
        slot = 'morning' if local.hour < 12 else 'evening'
        briefing_window = (s['settings'].get('briefing_hour', 7) <= local.hour < 12) or local.hour >= 18
        if not quiet(s['settings']) and (parts or (prefs.get('briefings', True) and briefing_window)):
            alert(s, device_id, f"weather:{result['date']}:{slot}", 'ORA · Weather outlook', summary+' '+' '.join(parts))
    db.mutate(save)
    return result


def expo(path, body):
    headers = {}
    if os.getenv('EXPO_ACCESS_TOKEN'): headers['Authorization'] = 'Bearer '+os.environ['EXPO_ACCESS_TOKEN']
    r = requests.post('https://exp.host/--/api/v2/push/'+path, json=body, headers=headers, timeout=12)
    r.raise_for_status()
    return r.json()['data']


def dispatch(db):
    # Claim in the database before network I/O to serialize overlapping cron calls.
    def claim(s):
        jobs = []
        for a in s.setdefault('alerts', []):
            d = next((d for d in s['devices'] if d['id'] == a['device_id']), {})
            if d.get('revoked') or d.get('paused') or not d.get('push_token'): continue
            if a['category'] == 'weather' and not d.get('weather', {}).get('enabled'): continue
            if a['delivery'] == 'ticket' and a.get('retry_at', 0) <= time.time():
                mode = 'receipt'
            elif a['delivery'] in ('pending', 'retry', 'sending') and a.get('retry_at', 0) <= time.time() and a['attempts'] < 5 and a['expires'] > time.time() and not quiet(s['settings']):
                mode = 'send'
                a['attempts'] += 1
                a['delivery'] = 'sending'
            else: continue
            a['retry_at'] = time.time()+300
            jobs.append((dict(a), dict(d), mode))
            if len(jobs) >= 10: break
        return jobs
    jobs = db.mutate(claim)
    for a, device, mode in jobs:
        try:
            if mode == 'receipt':
                result = expo('getReceipts', {'ids': [a['ticket']] }).get(a['ticket'])
                if not result:
                    result = {'status': 'error', 'details': {'error': 'ReceiptUnavailable'}} if a.get('ticket_at', 0) < time.time()-86400 else None
            else:
                private = device.get('private_notifications', True)
                result = expo('send', {'to': device['push_token'], 'title': 'ORA · New update' if private else a['title'],
                    'body': 'Open ORA to read your update.' if private else a['body'], 'sound': 'default',
                    'channelId': 'ora-weather' if a['category'] == 'weather' else 'ora-alerts',
                    'ttl': max(1, int(a['expires']-time.time())), 'data': {'alert_id': a['id']}})
        except (requests.RequestException, ValueError, KeyError):
            result = {'status': 'error', 'details': {'error': 'TransportError'}}
        def finish(s):
            row = next((x for x in s['alerts'] if x['id'] == a['id']), None)
            d = next((x for x in s['devices'] if x['id'] == device['id']), {})
            if not row: return
            if result is None:
                row['retry_at'] = time.time()+900
                return
            error = result.get('details', {}).get('error', 'PushError')
            if result.get('status') == 'ok':
                row['delivery'] = 'provider_accepted' if mode == 'receipt' else 'ticket'
                if mode == 'send': row.update(ticket=result['id'], ticket_at=time.time(), retry_at=time.time()+900)
            elif mode == 'receipt' and error == 'TransportError' and a.get('ticket_at', 0) > time.time()-86400:
                row.update(delivery='ticket', retry_at=time.time()+900, error=error)
            else:
                row.update(delivery='failed' if mode == 'receipt' or error == 'DeviceNotRegistered' or row['attempts'] >= 5 else 'retry', error=error, retry_at=time.time()+min(3600, 60*2**row['attempts']))
                if error == 'DeviceNotRegistered' and d.get('push_token') == device['push_token']:
                    d.pop('push_token', None)
        db.mutate(finish)
    return len(jobs)
