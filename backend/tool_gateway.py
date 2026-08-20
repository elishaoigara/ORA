"""Central Phase 6 execution gateway for typed ORA tools."""

from __future__ import annotations

from typing import Any

from action_ledger import approve_action, create_action, execute_action
from tool_contracts import ToolContractError


def _action_title(tool, details: dict[str, Any]) -> str:
    return str(details.get("title") or f"Run {tool.name}")


def submit_tool_call(tool, payload: dict[str, Any] | None = None, source: str = "tool_registry") -> dict[str, Any]:
    """Validate and route one registry call through the action policy."""
    spec = tool.get_spec()
    try:
        values = spec.validate(payload)
        details = tool.prepare_action(values)
    except ToolContractError as exc:
        return {"ok": False, "status": "invalid_input", "tool": spec.name, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": "preparation_failed", "tool": spec.name, "error": str(exc)}

    if not spec.action_type:
        return tool.safe_run(values)

    action_payload = details.get("payload", values)
    action = create_action(
        action_key=str(details.get("action_key") or spec.name),
        action_type=spec.action_type,
        title=_action_title(tool, details),
        description=str(details.get("description") or spec.description),
        payload=action_payload,
        risk=spec.risk,
        requires_approval=spec.needs_approval,
        source=source,
        idempotency_key=details.get("idempotency_key") or spec.idempotency_key(action_payload),
        max_retries=spec.max_retries,
        verification_required=bool(spec.action_type),
    )

    if action["status"] in {"completed", "failed", "rejected", "cancelled"}:
        return {"ok": action["status"] == "completed", "status": action["status"], "tool": spec.name, "action": action}
    if spec.needs_approval:
        return {"ok": True, "status": "action_proposed", "tool": spec.name, "action": action}

    approved = approve_action(action["id"])

    executed = execute_action(approved["id"]) if approved else None
    if not executed:
        return {"ok": False, "status": "execution_failed", "tool": spec.name, "action": approved}
    if executed["status"] == "completed" and executed.get("verification_status") == "pending":
        from action_ledger import verify_action
        result = executed.get("result") or {}
        receipt_keys = {
            "gmail.create_draft": "draft_id",
            "gmail.send_new": "message_id",
            "gmail.send_reply": "reply_id",
            "calendar.create": "id",
            "calendar.update": "id",
            "calendar.delete": "status",
        }
        key = receipt_keys.get(spec.action_type)
        verified = bool(result.get(key)) if key else bool(result.get("ok"))
        executed = verify_action(executed["id"], verified, {"mode": "connector_receipt", "key": key}) or executed
    return {"ok": executed["status"] == "completed", "status": executed["status"], "tool": spec.name, "action": executed}
