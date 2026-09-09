"""At most three read-only steps per routine, triggered by the existing external tick."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from mini.tools import execute_read, BY_NAME, connected
from mini.companion import alert, quiet

def tick_routines(store):
    state=store.read();local=datetime.now(ZoneInfo(state['settings'].get('timezone','Africa/Nairobi')))
    if quiet(state['settings']):return
    processed=0
    for routine in state.get('routines',[])[:10]:
        device=next((d for d in state['devices'] if d['id']==routine.get('device_id') and not d.get('revoked') and not d.get('paused')),None)
        if not device or not routine.get('enabled') or routine.get('hour') is None or local.hour<routine['hour']:continue
        day=local.date().isoformat()
        def claim(s):
            r=next(r for r in s['routines'] if r['id']==routine['id'])
            if r.get('last_day')==day:return False
            r.update(last_day=day,last_status='running');return True
        if not store.mutate(claim):continue
        processed+=1
        results=[]
        for step in routine['steps']:
            try:
                if step['tool'] in state.get('disabled_tools',[]) or not connected(BY_NAME[step['tool']]['service']):raise ValueError()
                results.append({'tool':step['tool'],'result':execute_read(step['tool'],step.get('args',{}),state,{'device_id':device['id']})})
            except Exception:results.append({'tool':step['tool'],'error':'Unavailable; check connection settings.'})
        def save(s):
            r=next(r for r in s['routines'] if r['id']==routine['id'])
            if not r.get('enabled'):return
            r.update(last_status='partial' if any('error' in v for v in results) else 'completed',last_result=results,last_at=time.time())
            alert(s,device['id'],'routine:'+r['id']+':'+day,'ORA · '+r['name'],'Your routine is ready. Open Tools → My routines to read the results.','alerts')
        store.mutate(save)
        if processed>=2:break
