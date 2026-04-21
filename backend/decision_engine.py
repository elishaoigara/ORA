from datetime import datetime
from database import log_alert

def decide(context: dict):
    cpu = context.get("cpu", 0)
    ram = context.get("ram", 0)
    disk = context.get("disk_free_gb", 999)

    decision = {
        "timestamp": datetime.now().isoformat(),
        "actions": [],
        "reasoning": []
    }

    if cpu > 85:
        decision["actions"].append({"type": "alert", "message": f"High CPU: {cpu}%", "severity": "high"})
        decision["reasoning"].append("CPU overload risk")

    if ram > 90:
        decision["actions"].append({"type": "alert", "message": f"High RAM: {ram}%", "severity": "high"})
        decision["reasoning"].append("RAM pressure detected")

    if disk < 5:
        decision["actions"].append({"type": "alert", "message": f"Low disk: {disk:.1f}GB left", "severity": "medium"})
        decision["reasoning"].append("Disk space critical")

    if not decision["actions"]:
        decision["actions"].append({"type": "log", "message": "All systems normal"})
        decision["reasoning"].append("No issues detected")

    for action in decision["actions"]:
        if action["type"] == "alert":
            log_alert("decision_engine", action["message"], action.get("severity", "medium"))

    return decision