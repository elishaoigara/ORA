"""Bounded weather checks and durable Telegram alert delivery; invoked by external cron."""
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from fastapi import HTTPException
from mini.telegram import bot_call, token


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
                     read=False, delivery='pending', attempts=0, retry_at=0, transport='telegram',
                     telegram_chat_id=(device_for(state, device_id).get('telegram_alerts_chat_id')
                                       if device_for(state, device_id).get('telegram_alerts_enabled') else None)))


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


def delivery_status(state):
    telegram = state.get('telegram', {})
    return {'channel': 'telegram', 'configured': bool(token()),
            'linked': type(telegram.get('chat_id')) is int and telegram['chat_id'] > 0,
            'username': telegram.get('username')}


def enabled(device, state):
    chat_id = state.get('telegram', {}).get('chat_id')
    return (type(chat_id) is int and chat_id > 0 and device.get('telegram_alerts_enabled') is True
            and device.get('telegram_alerts_chat_id') == chat_id
            and not device.get('revoked') and not device.get('paused'))


def dispatch(db):
    # Claim before network I/O. Delivery is bounded and at-least-once: a timeout
    # after Telegram accepted a message can cause a retry, never a read receipt.
    def claim(s):
        jobs = []
        chat_id = s.get('telegram', {}).get('chat_id')
        for a in s.setdefault('alerts', []):
            if a['delivery'] not in ('pending', 'retry', 'sending', 'ticket'):
                continue
            if a.get('transport') != 'telegram':
                a['delivery'] = 'retired'  # Never replay an old Expo job to Telegram.
                continue
            if a['expires'] <= time.time():
                a['delivery'] = 'expired'
                continue
            d = device_for(s, a['device_id'])
            if not enabled(d, s) or a.get('telegram_chat_id') != chat_id:
                a['delivery'] = 'cancelled'
                continue
            if a['category'] == 'weather' and not d.get('weather', {}).get('enabled'):
                a['delivery'] = 'cancelled'
                continue
            if a.get('retry_at', 0) > time.time():
                continue
            if a['attempts'] >= 5:
                a['delivery'] = 'failed'
                continue
            if not token() or quiet(s['settings']):
                continue
            a.update(attempts=a['attempts']+1, delivery='sending',
                     retry_at=time.time()+300, lease=uuid.uuid4().hex)
            jobs.append(dict(a))
            if len(jobs) >= 10:
                break
        return jobs
    jobs = db.mutate(claim)
    for a in jobs:
        # Recheck opt-out/relink and use the latest privacy setting before sending.
        current = db.read()
        device = device_for(current, a['device_id'])
        row = next((x for x in current['alerts'] if x['id'] == a['id']), {})
        if (not enabled(device, current) or row.get('lease') != a['lease']
                or row.get('delivery') != 'sending'
                or current.get('telegram', {}).get('chat_id') != a['telegram_chat_id']):
            continue
        accepted = False
        try:
            private = device.get('private_notifications', True)
            text = ('ORA · New update\nOpen ORA to read your update.' if private
                    else (a['title'] + '\n' + a['body'])[:4000])
            result = bot_call('sendMessage', {'chat_id': a['telegram_chat_id'], 'text': text,
                                             'link_preview_options': {'is_disabled': True}})
            accepted = isinstance(result, dict) and type(result.get('message_id')) is int
        except (HTTPException, requests.RequestException, ValueError, KeyError, TypeError):
            pass  # Never store exception URLs, bot tokens, or private chat IDs.
        def finish(s):
            row = next((x for x in s['alerts'] if x['id'] == a['id']), None)
            if not row or row.get('lease') != a['lease'] or row['delivery'] != 'sending':
                return
            row.pop('lease', None)
            if accepted:
                row.update(delivery='sent_to_telegram', sent_at=time.time())
                row.pop('error', None)
            else:
                row.update(delivery='failed' if row['attempts'] >= 5 else 'retry',
                           error='Telegram unavailable. Check the bot connection.',
                           retry_at=time.time()+min(3600, 60*2**row['attempts']))
        db.mutate(finish)
    return len(jobs)


def device_for(state, device_id):
    if device_id == 'telegram-owner':
        t = state.get('telegram', {})
        return {'id': device_id, 'telegram_alerts_enabled': bool(t.get('alerts_enabled')),
                'telegram_alerts_chat_id': t.get('chat_id'),
                'private_notifications': t.get('private_alerts', True)}
    return next((d for d in state['devices'] if d['id'] == device_id), {})


def briefing(state):
    if state.get('telegram', {}).get('private_alerts', True):
        count = sum(not t.get('done') for t in state['tasks'])
        return f'Your ORA check-in: {count} open tasks. Use /tasks for details or /privacy off for detailed briefings.'
    tasks = sorted((t for t in state['tasks'] if not t.get('done')),
                   key=lambda t: (t.get('due_at') or '9999', t.get('priority', 2)))[:5]
    lines = [t['title'][:140] for t in tasks]
    return 'Your ORA check-in. ' + (' Next: ' + '; '.join(lines) if lines else 'You have no open tasks. What would you like to plan?')


def telegram_check(db):
    """One daily briefing independent of Android; optional scheduled phone check-in."""
    state = db.read()
    t = state.get('telegram', {})
    if not token() or not t.get('chat_id') or not t.get('user_id') or quiet(state['settings']):
        return
    local = datetime.now(ZoneInfo(state['settings'].get('timezone', 'Africa/Nairobi')))
    if local.hour < state['settings'].get('briefing_hour', 7):
        return
    day = local.date().isoformat()
    def queue(s):
        if s.get('telegram', {}).get('alerts_enabled'):
            alert(s, 'telegram-owner', 'telegram-briefing:' + day, 'ORA · Daily check-in', briefing(s), 'alerts')
    db.mutate(queue)
    if t.get('daily_calls'):
        from mini.calls import call_owner
        try:
            call_owner(db, 'daily:' + day, briefing(state), scheduled=True)
        except HTTPException:
            pass  # Missing config, quiet hours or the daily cap must not block alerts.
