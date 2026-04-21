import ast
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import get_recent_alerts, get_system_stats, acknowledge_alert
from memory.profile import get_all_profile
from memory.events import get_recent_events
from memory.preferences import get_preferences

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ORA online"}

@app.get("/api/status")
def get_status():
    row = get_system_stats()
    if not row:
        return {"status": "warming_up"}
    data = ast.literal_eval(row[0])
    return {
        "cpu": data.get("cpu_percent"),
        "ram": data.get("ram_percent"),
        "disk_free_gb": round(data.get("disk_free_gb", 0), 1),
        "last_updated": row[1]
    }

@app.get("/api/alerts")
def get_alerts():
    alerts = get_recent_alerts(20)
    return [
        {
            "id": a[0],
            "rule": a[1],
            "message": a[2],
            "severity": a[3],
            "timestamp": a[4],
            "acknowledged": bool(a[5])
        }
        for a in alerts
    ]

@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    acknowledge_alert(alert_id)
    return {"status": "acknowledged"}

@app.get("/api/memory/profile")
def get_profile():
    return get_all_profile()

@app.get("/api/memory/events")
def get_events():
    events = get_recent_events(limit=20)
    return [
        {"type": e[0], "summary": e[1], "importance": e[3], "timestamp": e[4]}
        for e in events
    ]

@app.get("/api/memory/preferences")
def get_prefs():
    prefs = get_preferences()
    return [
        {"category": p[0], "key": p[1], "value": p[2], "confidence": p[3]}
        for p in prefs
    ]