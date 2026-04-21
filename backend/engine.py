# ORA's rules engine
# Each rule takes data dict, returns (triggered: bool, message: str)
# Add new rules as functions, register in RULES list at the bottom

def check_high_cpu(data):
    cpu = data.get("cpu_percent", 0)
    if cpu > 85:
        return True, f"High CPU usage: {cpu}%"
    return False, ""

def check_high_ram(data):
    ram = data.get("ram_percent", 0)
    if ram > 90:
        return True, f"High RAM usage: {ram}%"
    return False, ""

def check_low_disk(data):
    disk = data.get("disk_free_gb", 999)
    if disk < 5:
        return True, f"Low disk space: {disk:.1f}GB remaining"
    return False, ""

# (rule_name, function, severity)
# severity: "low", "medium", "high"
RULES = [
    ("high_cpu", check_high_cpu, "high"),
    ("high_ram", check_high_ram, "high"),
    ("low_disk", check_low_disk, "medium"),
]

def run_rules(data):
    triggered = []
    for rule_name, rule_fn, severity in RULES:
        fired, message = rule_fn(data)
        if fired:
            triggered.append((rule_name, message, severity))
    return triggered