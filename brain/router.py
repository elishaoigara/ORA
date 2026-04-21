def classify_intent(text: str) -> str:
    text = text.lower().strip()

    # SYSTEM COMMANDS
    if text.startswith("/status"):
        return "status"

    if text.startswith("/alerts"):
        return "alerts"

    if text.startswith("/task"):
        return "task"

    if text.startswith("/ack"):
        return "ack"

    if text.startswith("/remind"):
        return "reminder"

    if text.startswith("/mood"):
        return "mood"

    # MEMORY QUERIES
    if any(x in text for x in ["what did we discuss", "remember", "earlier", "yesterday"]):
        return "memory"

    # DEFAULT → AI CHAT
    return "chat"