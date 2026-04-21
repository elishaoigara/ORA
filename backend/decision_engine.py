def decide(context):
    reasoning = []
    actions = []

    cpu = context.get("cpu", 0)
    ram = context.get("ram", 0)
    disk = context.get("disk_free_gb", 999)

    if cpu > 85:
        reasoning.append(f"High CPU: {cpu}%")
        actions.append({"type": "alert", "message": f"High CPU usage: {cpu}%", "severity": "high"})

    if ram > 90:
        reasoning.append(f"High RAM: {ram}%")
        actions.append({"type": "alert", "message": f"High RAM usage: {ram}%", "severity": "high"})

    if disk < 5:
        reasoning.append(f"Low disk: {disk:.1f}GB")
        actions.append({"type": "alert", "message": f"Low disk space: {disk:.1f}GB", "severity": "medium"})

    if not reasoning:
        reasoning.append("All systems normal")

    return {"reasoning": reasoning, "actions": actions}