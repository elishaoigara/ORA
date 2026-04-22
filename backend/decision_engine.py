def decide(context, use_ai=False, ai_handler=None):
    """
    Hybrid decision engine:
    - Rules first (fast, free)
    - AI fallback only when needed
    """

    reasoning = []
    actions = []

    cpu = context.get("cpu", 0)
    ram = context.get("ram", 0)
    disk = context.get("disk_free_gb", 999)

    # ─────────────────────────────────────────
    # RULE-BASED DECISIONS (PRIMARY LAYER)
    # ─────────────────────────────────────────
    if cpu > 85:
        reasoning.append(f"High CPU: {cpu}%")
        actions.append({
            "type": "alert",
            "message": f"High CPU usage: {cpu}%",
            "severity": "high"
        })

    if ram > 90:
        reasoning.append(f"High RAM: {ram}%")
        actions.append({
            "type": "alert",
            "message": f"High RAM usage: {ram}%",
            "severity": "high"
        })

    if disk < 5:
        reasoning.append(f"Low disk: {disk:.1f}GB")
        actions.append({
            "type": "alert",
            "message": f"Low disk space: {disk:.1f}GB",
            "severity": "medium"
        })

    # ─────────────────────────────────────────
    # INTELLIGENCE TRIGGER (WHEN RULES ARE NOT ENOUGH)
    # ─────────────────────────────────────────
    complex_state = (
        (70 < cpu <= 85) or
        (75 < ram <= 90) or
        (5 <= disk <= 10)
    )

    if not actions and complex_state:
        reasoning.append("Borderline system state detected")

        if use_ai and ai_handler:
            try:
                ai_result = ai_handler(context)

                return {
                    "reasoning": ["AI analysis"] + ai_result.get("reasoning", []),
                    "actions": ai_result.get("actions", [])
                }

            except Exception as e:
                reasoning.append(f"AI fallback failed: {e}")

    # ─────────────────────────────────────────
    # DEFAULT STATE
    # ─────────────────────────────────────────
    if not reasoning:
        reasoning.append("All systems normal")

    return {
        "reasoning": reasoning,
        "actions": actions
    }