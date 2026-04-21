from database import log_alert

def execute(decision):
    from telegram_bot import notify
    actions = decision.get("actions", [])
    for action in actions:
        if action["type"] == "alert":
            log_alert(
                rule_name="decision_engine",
                message=action["message"],
                severity=action.get("severity", "medium")
            )
            notify(action["message"], is_alert=True)