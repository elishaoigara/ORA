"""Read-only legacy import. Inspect counts first; --apply imports into an EMPTY Mini workspace."""
import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from mini.store import Store, now


def read_legacy(path):
    conn=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def rows(name):
        return [dict(r) for r in conn.execute('SELECT * FROM '+name)] if name in tables else []
    def timestamp(value):
        try:
            d=datetime.fromisoformat(value)
            return (d if d.tzinfo else d.replace(tzinfo=ZoneInfo('Africa/Nairobi'))).astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError):return None
    tasks=[{'id':'legacy-task-'+str(t['id']),'title':str(t.get('title','Task'))[:240],
            'due_at':timestamp(t.get('due_at')),'done':t.get('status') in ('done','completed'),
            'priority':{'low':1,'medium':2,'high':3}.get(t.get('priority'),2),'version':1,
            'created_at':timestamp(t.get('created_at')) or now()} for t in rows('tasks')]
    history=rows('conversation_history') or rows('conversations')
    messages=[{'id':'legacy-message-'+str(m['id']),'role':m['role'],'text':str(m.get('content',''))[:8000],
               'created_at':timestamp(m.get('created_at') or m.get('timestamp')) or now()} for m in history if m['role'] in ('user','assistant')][-300:]
    # Only facts the old review workflow explicitly confirmed become trusted memory.
    memories=[{'id':'legacy-memory-'+str(m['id']),'text':' '.join(str(m.get(k) or '') for k in ('subject','predicate','object')).strip()[:1000],
               'created_at':now()} for m in rows('learned_facts') if m.get('status') in ('confirmed','verified')]
    memories=[m for m in memories if m['text']]
    conn.close()
    if len(tasks)>500 or len(memories)>200:raise ValueError('Archive excess tasks/memories before importing (500 tasks / 200 memories maximum).')
    return {'tasks':tasks,'messages':messages,'memories':memories}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_file');parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();data=read_legacy(args.sqlite_file)
    print(json.dumps({key:len(value) for key,value in data.items()},indent=2))
    if args.apply:
        from dotenv import load_dotenv
        load_dotenv()
        store=Store()
        def apply(state):
            if any(state[key] for key in data):raise ValueError('Destination is not empty; import cancelled without changes.')
            state.update(data)
            return {'imported':True}
        store.mutate(apply)
        print('Imported. Original database unchanged. Re-upload documents and pair devices again.')
