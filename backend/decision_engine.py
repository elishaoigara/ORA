from ai_budget import ai_budget
def decide(context, use_ai=False, ai_handler=None):
    """
    Hybrid decision engine:
    - Rules first (fast, free)
    - AI fallback only when truly needed
    """

    reasoning = []
    actions = []

    cpu = context.get("cpu", 0)
    ram = context.get("ram", 0)
    disk = context.get("disk_free_gb", 999)

    # ─────────────────────────────────────────
    # RULE LAYER (PRIMARY - 90% OF CASES)
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
    # DEFAULT RULE RESULT
    # ─────────────────────────────────────────
    if not reasoning:
        reasoning.append("All systems normal")

    # ─────────────────────────────────────────
    # AI TRIGGER LOGIC (STRICTED)
    # ─────────────────────────────────────────
    complex_state = (
        (70 < cpu <= 85) or
        (75 < ram <= 90) or
        (5 <= disk <= 10)
    )

    # AI ONLY if:
    # - no critical rule triggered
    # - system is in gray zone
    # - AI is explicitly enabled
    if not actions and complex_state and use_ai and ai_handler:

        reasoning.append("Borderline system state detected")

        try:
            ai_result = ai_handler(context)

            # safety checks (VERY IMPORTANT for production stability)
            if not isinstance(ai_result, dict):
                raise ValueError("AI returned invalid format")

            return {
                "reasoning": ["AI analysis"] + ai_result.get("reasoning", []),
                "actions": ai_result.get("actions", [])
            }

        except Exception as e:
            reasoning.append(f"AI fallback failed: {str(e)}")

    # ─────────────────────────────────────────
    # FINAL OUTPUT (SAFE GUARANTEE)
    # ─────────────────────────────────────────
    return {
        "reasoning": reasoning,
        "actions": actions
    }