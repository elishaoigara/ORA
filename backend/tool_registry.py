"""
ORA Tool Registry
=================
Inspired by Claude Code's 43-tool registry (BashTool, WebSearchTool, etc.)

Every capability ORA has is a self-contained Tool class with:
  - name: str           — unique identifier used by the router
  - description: str    — what it does (used for introspection/docs)
  - run(input) -> dict  — consistent interface: always returns {"ok": bool, ...}

The router calls tools by name through the registry instead of scattering
import logic across agent functions. This makes ORA's capabilities:
  - Discoverable (list all tools, describe them)
  - Testable in isolation
  - Droppable/addable without touching the router

Built-in tools (mirrors ORA's existing agents):
  web_search        — Tavily web search
  weather           — Open-Meteo weather
  calendar_today    — Google Calendar events today
  calendar_imminent — Upcoming events in N minutes
  gmail_summary     — Gmail unread summary
  github_summary    — GitHub connector summary
  mpesa_spend       — M-Pesa spend check
  knowledge_search  — RAG knowledge base search
  memory_read       — Load profile + facts
  memory_write      — Extract and store facts
  task_list         — List pending ORA tasks
  goal_list         — List active goals
  task_engine_stats — Agent task stats

Usage:
    from tool_registry import registry

    result = registry.run("web_search", {"query": "AI news Kenya"})
    # → {"ok": True, "content": "...", "sources": [...]}

    result = registry.run("weather", {})
    # → {"ok": True, "summary": "Sunny, 24°C in Nairobi"}

    # List all available tools
    tools = registry.list_tools()
"""

from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from typing import Any

from tool_contracts import ToolContractError, ToolSpec


# ─── Base Tool ────────────────────────────────────────────────────────────────

class Tool(ABC):
    name: str = ""
    description: str = ""
    tool_spec: ToolSpec | None = None

    def get_spec(self) -> ToolSpec:
        if self.tool_spec is not None:
            return self.tool_spec
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=getattr(self, "schema", {}),
        )

    def prepare_action(self, input: dict) -> dict[str, Any]:
        """Return action metadata for side-effecting tools; read tools return empty."""
        return {}

    @abstractmethod
    def run(self, input: dict) -> dict:
        """Execute tool. Must return dict with at least {"ok": bool}."""
        ...

    def safe_run(self, input: dict) -> dict:
        """Wraps run() with error handling — never raises."""
        try:
            return self.run(input)
        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "error": str(e), "tool": self.name}


# ─── Tool implementations ──────────────────────────────────────────────────────

class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web via Tavily. Input: {query: str, max_results?: int}"

    def run(self, input: dict) -> dict:
        query = (input.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "query required"}
        return {
            "ok": False,
            "error": "Web search is not configured in this deployment. Use browse with a direct URL.",
            "query": query,
        }


class BrowseTool(Tool):
    name        = "browse"
    description = "Fetch and read any URL — web pages, PDFs, YouTube transcripts. Input: {url: str, question?: str}"
    schema      = {
        "url":      {"type": "str", "required": True,  "desc": "Full URL to fetch"},
        "question": {"type": "str", "required": False, "desc": "Optional question to answer from the page"},
    }

    def run(self, input: dict) -> dict: # pyright: ignore[reportRedeclaration]
        from connectors.browse import browse
        url      = (input.get("url") or "").strip()
        question = (input.get("question") or "").strip() or None
        if not url:
            return {"ok": False, "error": "url is required"}
        return browse(url, question=question)


class WeatherTool(Tool):
    name = "weather"
    description = "Get current weather summary (Nairobi default). Input: {}"

    def run(self, input: dict) -> dict:
        from connectors.weather import get_weather_summary
        summary = get_weather_summary()
        return {"ok": True, "summary": summary or "Weather unavailable."}


class CalendarTodayTool(Tool):
    name = "calendar_today"
    description = "Get Google Calendar events for today. Input: {}"

    def run(self, input: dict) -> dict:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        formatted = format_events_for_context(events) if events else "No events today."
        return {"ok": True, "events": events, "formatted": formatted, "count": len(events)}


class CalendarImminentTool(Tool):
    name = "calendar_imminent"
    description = "Get events starting within N minutes. Input: {minutes?: int}"

    def run(self, input: dict) -> dict:
        from connectors.calendar import get_imminent_events
        minutes = int(input.get("minutes", 30))
        events = get_imminent_events(minutes)
        return {"ok": True, "events": events, "count": len(events)}


class GmailSummaryTool(Tool):
    name = "gmail_summary"
    description = "Get Gmail unread summary. Input: {}"

    def run(self, input: dict) -> dict:
        from connectors.gmail import get_gmail_summary
        from connectors.google_auth import is_authorized
        if not is_authorized():
            return {"ok": False, "error": "Google not authorized"}
        summary = get_gmail_summary()
        return {"ok": True, **summary}


class GitHubSummaryTool(Tool):
    name = "github_summary"
    description = "Get GitHub activity summary. Input: {}"

    def run(self, input: dict) -> dict:
        return {
            "ok": False,
            "error": "GitHub integration is not configured in this deployment.",
        }


class MpesaSpendTool(Tool):
    name = "mpesa_spend"
    description = "Check M-Pesa spending for today. Input: {}"

    def run(self, input: dict) -> dict:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        try:
            today = float(str(get_today_spend() or 0))
            avg = float(str(get_average_daily_spend() or 0))
        except Exception:
            today, avg = 0.0, 0.0
        return {
            "ok": True,
            "today_kes": today,
            "avg_daily_kes": avg,
            "above_average": today > avg * 1.3 if avg else False,
        }


class KnowledgeSearchTool(Tool):
    name = "knowledge_search"
    description = "Search ORA's knowledge base (RAG). Input: {query: str, n_results?: int}"

    def run(self, input: dict) -> dict:
        from knowledge.pipeline import search_and_format
        query = input.get("query", "")
        n = int(input.get("n_results", 3))
        if not query:
            return {"ok": False, "error": "query required"}
        context = search_and_format(query, n_results=n)
        return {"ok": True, "context": context or "", "found": bool(context and len(context.strip()) > 30)}


class MemoryReadTool(Tool):
    name = "memory_read"
    description = "Load user profile, facts, preferences, and important events. Input: {}"

    def run(self, input: dict) -> dict:
        parts = {}
        try:
            from memory.profile import get_all_profile
            parts["profile"] = get_all_profile()
        except Exception:
            parts["profile"] = {}
        try:
            from intelligence.learning_engine import get_facts_as_context
            parts["facts"] = get_facts_as_context(limit=15)
        except Exception:
            parts["facts"] = ""
        try:
            from memory.preferences import get_preferences
            prefs = get_preferences()
            parts["preferences"] = [{"category": r[0], "key": r[1], "value": r[2]} for r in prefs[:10]]
        except Exception:
            parts["preferences"] = []
        try:
            from memory.events import get_important_events
            events = get_important_events(min_importance=7, limit=5)
            parts["important_events"] = [{"type": e[1], "summary": e[2]} for e in events]
        except Exception:
            parts["important_events"] = []
        return {"ok": True, **parts}


class MemoryWriteTool(Tool):
    name = "memory_write"
    description = "Extract and store facts from a user message. Input: {text: str}"

    def run(self, input: dict) -> dict:
        text = input.get("text", "")
        if not text:
            return {"ok": False, "error": "text required"}
        try:
            from intelligence.learning_engine import extract_explicit_facts
            extract_explicit_facts(text)
            return {"ok": True, "stored": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class TaskListTool(Tool):
    name = "task_list"
    description = "List ORA tasks by status. Input: {status?: str}"

    def run(self, input: dict) -> dict:
        from database import get_tasks
        status = input.get("status", "pending")
        tasks = get_tasks(status)
        return {
            "ok": True,
            "tasks": [{"id": t[0], "title": t[1], "priority": t[2], "due_at": t[4]} for t in tasks],
            "count": len(tasks),
        }


class GoalListTool(Tool):
    name = "goal_list"
    description = "List active goals. Input: {status?: str}"

    def run(self, input: dict) -> dict:
        from intelligence.goals_engine import get_goals
        status = input.get("status", "active")
        goals = get_goals(status)
        return {"ok": True, "goals": goals, "count": len(goals)}


class TaskEngineStatsTool(Tool):
    name = "task_engine_stats"
    description = "Get agent task pipeline stats. Input: {}"

    def run(self, input: dict) -> dict:
        from task_engine import task_engine
        stats = task_engine.get_stats()
        return {"ok": True, **stats}


class RecentAgentTasksTool(Tool):
    name = "recent_agent_tasks"
    description = "Get recent agent task history. Input: {limit?: int, kind?: str, status?: str}"

    def run(self, input: dict) -> dict:
        from task_engine import task_engine
        tasks = task_engine.get_recent(
            limit=int(input.get("limit", 10)),
            kind=input.get("kind", ""),
            status=input.get("status", ""),
        )
        return {"ok": True, "tasks": tasks, "count": len(tasks)}


class CalendarCreateTool(Tool):
    name = "calendar_create"
    description = (
        "Create a new Google Calendar event from a natural-language description. "
        "Input: {text: str}  e.g. {\"text\": \"Team meeting tomorrow at 3pm for 1 hour\"}"
    )
    tool_spec = ToolSpec(
        name=name, description=description,
        input_schema={"text": {"type": "str", "required": True}},
        risk="external_write", side_effect="calendar.create",
        action_type="calendar.create", timeout_seconds=30, max_retries=1,
    )

    def prepare_action(self, input: dict) -> dict[str, Any]:
        from connectors.calendar import parse_event_request
        result = parse_event_request(input["text"])
        if not result.get("ok"):
            raise ToolContractError(result.get("error", "Could not parse calendar event"))
        event = result["event"]
        return {
            "payload": event,
            "title": f"Add calendar event: {event['title']}",
            "description": event.get("description", ""),
            "action_key": f"calendar.create:{event['title']}",
        }

    def run(self, input: dict) -> dict:
        from connectors.calendar import quick_event
        text = (input.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        result = quick_event(text)
        if result.get("ok"):
            e = result["event"]
            return {
                "ok":      True,
                "message": f"✅ Created: **{e['title']}** on {e['start'][:16].replace('T',' ')}",
                "event":   e,
            }
        return result


class CalendarUpdateTool(Tool):
    name = "calendar_update"
    description = (
        "Update an existing calendar event. "
        "Input: {event_id: str, title?: str, start?: ISO str, end?: ISO str, "
        "location?: str, description?: str}"
    )
    tool_spec = ToolSpec(
        name=name, description=description,
        input_schema={
            "event_id": {"type": "str", "required": True},
            "title": {"type": "str", "required": False},
            "start": {"type": "str", "required": False},
            "end": {"type": "str", "required": False},
            "location": {"type": "str", "required": False},
            "description": {"type": "str", "required": False},
        },
        risk="external_write", side_effect="calendar.update",
        action_type="calendar.update", timeout_seconds=30, max_retries=1,
    )

    def prepare_action(self, input: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        payload = dict(input)
        for key in ("start", "end"):
            if payload.get(key):
                dt = datetime.fromisoformat(payload[key])
                payload[key] = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
        if not any(payload.get(key) is not None for key in ("title", "start", "end", "location", "description")):
            raise ToolContractError("At least one event field is required")
        return {
            "payload": payload,
            "title": f"Update calendar event {input['event_id']}",
            "action_key": f"calendar.update:{input['event_id']}",
        }

    def run(self, input: dict) -> dict:
        from connectors.calendar import update_event
        from datetime import datetime, timezone
        event_id = input.get("event_id", "")
        if not event_id:
            return {"ok": False, "error": "event_id is required"}

        def _parse_dt(s):
            if not s:
                return None
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        result = update_event(
            event_id    = event_id,
            title       = input.get("title"),
            start       = _parse_dt(input.get("start")),
            end         = _parse_dt(input.get("end")),
            description = input.get("description"),
            location    = input.get("location"),
        )
        if result.get("ok"):
            e = result["event"]
            return {
                "ok":      True,
                "message": f"✅ Updated: **{e['title']}**",
                "event":   e,
            }
        return result


class CalendarDeleteTool(Tool):
    name = "calendar_delete"
    description = "Delete a calendar event by ID. Input: {event_id: str}"
    tool_spec = ToolSpec(
        name=name, description=description,
        input_schema={"event_id": {"type": "str", "required": True}},
        risk="irreversible", side_effect="calendar.delete",
        action_type="calendar.delete", timeout_seconds=30, max_retries=0,
    )

    def prepare_action(self, input: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": {"event_id": input["event_id"]},
            "title": f"Delete calendar event {input['event_id']}",
            "action_key": f"calendar.delete:{input['event_id']}",
        }

    def run(self, input: dict) -> dict:
        from connectors.calendar import delete_event
        event_id = input.get("event_id", "")
        if not event_id:
            return {"ok": False, "error": "event_id is required"}
        result = delete_event(event_id)
        if result.get("ok"):
            return {"ok": True, "message": f"🗑️ Event {event_id} deleted."}
        return result


class CalendarFreeSlotTool(Tool):
    name = "calendar_free_slot"
    description = (
        "Find the next free time slot in the calendar. "
        "Input: {duration_minutes?: int, hours_ahead?: int}  defaults: 60 min, 48 h"
    )

    def run(self, input: dict) -> dict:
        from connectors.calendar import find_free_slot
        result = find_free_slot(
            duration_minutes = int(input.get("duration_minutes", 60)),
            hours_ahead      = int(input.get("hours_ahead", 48)),
        )
        if result.get("ok"):
            start = result["start"]
            end   = result["end"]
            return {
                "ok":      True,
                "message": f"Next free slot: {start.strftime('%A %d %b, %H:%M')}–{end.strftime('%H:%M')} EAT",
                "start":   start.isoformat(),
                "end":     end.isoformat(),
            }
        return result




class SheetsCreateTool(Tool):
    name = "sheets_create"
    description = (
        "Create a Google Spreadsheet from a natural-language description. "
        "Use when the user says things like: 'make a spreadsheet of...', "
        "'put this in a sheet', 'create a Google Sheet with...', "
        "'log this as a spreadsheet'. "
        "Input: {text: str}  e.g. text=Spreadsheet of top 5 Kenyan banks"
    )

    def run(self, input: dict) -> dict:
        from connectors.sheets import create_sheet_from_prompt
        text = (input.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        return create_sheet_from_prompt(text)


class SheetsReadTool(Tool):
    name = "sheets_read"
    description = (
        "Read data from an existing Google Spreadsheet. "
        "Input: {url_or_id: str, tab?: str, range?: str}"
    )

    def run(self, input: dict) -> dict:
        from connectors.sheets import read_sheet
        url = (input.get("url_or_id") or input.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "url_or_id is required"}
        result = read_sheet(url,
                            tab=input.get("tab", "Sheet1"),
                            range_a1=input.get("range", ""))
        if result.get("ok"):
            rows = result["values"]
            preview = "\n".join(", ".join(str(c) for c in r) for r in rows[:5])
            result["message"] = (
                f"Read {result['rows']} rows × {result['cols']} cols.\n{preview}"
                + ("\n..." if result["rows"] > 5 else "")
            )
        return result


class SheetsWriteTool(Tool):
    name = "sheets_write"
    description = (
        "Write or append rows to an existing Google Spreadsheet. "
        "Input: {url_or_id: str, rows: [[...], ...], tab?: str, append?: bool}"
    )

    def run(self, input: dict) -> dict:
        from connectors.sheets import write_rows, append_rows
        url  = (input.get("url_or_id") or input.get("url") or "").strip()
        rows = input.get("rows", [])
        tab  = input.get("tab", "Sheet1")
        if not url:
            return {"ok": False, "error": "url_or_id is required"}
        if not rows:
            return {"ok": False, "error": "rows is required"}
        if input.get("append", True):
            return append_rows(url, rows, tab=tab)
        return write_rows(url, rows, tab=tab)


class MpesaSyncSheetTool(Tool):
    name = "mpesa_sync_sheet"
    description = (
        "Sync M-Pesa transaction history to a Google Sheet. "
        "Use when user asks to export, backup, or sync M-Pesa data to Sheets. "
        "Input: {days?: int}  default 30 days"
    )

    def run(self, input: dict) -> dict:
        from connectors.sheets import sync_mpesa_history
        days = int(input.get("days", 30))
        return sync_mpesa_history(days=days)

# ─── Registry ─────────────────────────────────────────────────────────────────

class GmailSendTool(Tool):
    name        = "gmail_send"
    description = "Send a new email via Gmail"
    tool_spec  = ToolSpec(
        name=name, description=description,
        input_schema={
            "to": {"type": "str", "required": True},
            "subject": {"type": "str", "required": True},
            "body": {"type": "str", "required": True},
            "cc": {"type": "str", "required": False},
            "account": {"type": "str", "required": False},
        },
        risk="external_communication", side_effect="gmail.send",
        action_type="gmail.send_new", timeout_seconds=30, max_retries=0,
    )
    schema      = {
        "to":      {"type": "str",  "required": True,  "desc": "Recipient email address"},
        "subject": {"type": "str",  "required": True,  "desc": "Email subject line"},
        "body":    {"type": "str",  "required": True,  "desc": "Email body (plain text)"},
        "cc":      {"type": "str",  "required": False, "desc": "CC address (optional)"},
        "account": {"type": "str",  "required": False, "desc": "primary or secondary (default: primary)"},
    }

    def prepare_action(self, input: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": {
                "to": input["to"].strip(), "subject": input["subject"].strip(),
                "body": input["body"].strip(), "cc": input.get("cc", ""),
                "account": input.get("account", "primary"),
            },
            "title": f"Send email to {input['to']}",
            "action_key": f"gmail.send:{input['to']}:{input['subject']}",
        }

    def run(self, input: dict) -> dict:
        from connectors.gmail import send_new_email
        to      = (input.get("to") or "").strip()
        subject = (input.get("subject") or "").strip()
        body    = (input.get("body") or "").strip()
        if not to or not subject or not body:
            return {"ok": False, "error": "to, subject, and body are all required"}
        return send_new_email(
            to=to,
            subject=subject,
            body=body,
            cc=input.get("cc", ""),
            account=input.get("account", "primary"),
        )


class GmailDraftTool(Tool):
    name        = "gmail_draft"
    description = "Save an email as a Gmail draft without sending"
    tool_spec  = ToolSpec(
        name=name, description=description,
        input_schema={
            "to": {"type": "str", "required": True},
            "subject": {"type": "str", "required": True},
            "body": {"type": "str", "required": True},
            "account": {"type": "str", "required": False},
        },
        risk="external_write", side_effect="gmail.create_draft",
        action_type="gmail.create_draft", timeout_seconds=30, max_retries=1,
    )
    schema      = {
        "to":      {"type": "str", "required": True,  "desc": "Recipient email address"},
        "subject": {"type": "str", "required": True,  "desc": "Email subject line"},
        "body":    {"type": "str", "required": True,  "desc": "Email body (plain text)"},
        "account": {"type": "str", "required": False, "desc": "primary or secondary"},
    }

    def prepare_action(self, input: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": {
                "to": input["to"].strip(), "subject": input["subject"].strip(),
                "body": input["body"].strip(), "account": input.get("account", "primary"),
            },
            "title": f"Create Gmail draft for {input['to']}",
            "action_key": f"gmail.draft:{input['to']}:{input['subject']}",
        }

    def run(self, input: dict) -> dict:
        from connectors.gmail import create_draft
        to      = (input.get("to") or "").strip()
        subject = (input.get("subject") or "").strip()
        body    = (input.get("body") or "").strip()
        if not to or not subject or not body:
            return {"ok": False, "error": "to, subject, and body are all required"}
        return create_draft(
            to=to,
            subject=subject,
            body=body,
            account=input.get("account", "primary"),
        )


class GmailReplyTool(Tool):
    name        = "gmail_reply"
    description = "Send a saved Gmail smart reply after explicit approval"
    tool_spec  = ToolSpec(
        name=name, description=description,
        input_schema={"reply_id": {"type": "int", "required": True}},
        risk="external_communication", side_effect="gmail.send_reply",
        action_type="gmail.send_reply", timeout_seconds=30, max_retries=0,
    )

    def prepare_action(self, input: dict[str, Any]) -> dict[str, Any]:
        from connectors.gmail import get_suggested_reply
        reply = get_suggested_reply(input["reply_id"])
        if not reply:
            raise ToolContractError("Reply not found")
        payload = {
            "reply_id": input["reply_id"],
            "to": reply.get("sender", ""),
            "subject": reply.get("subject", ""),
            "body": reply.get("suggested_text", ""),
            "thread_id": reply.get("thread_id"),
            "account": reply.get("account", "primary"),
        }
        return {
            "payload": payload,
            "title": f"Send reply to {reply.get('sender', 'email contact')}",
            "description": reply.get("subject", ""),
            "action_key": f"gmail.reply:{input['reply_id']}",
            "idempotency_key": f"gmail.reply:{input['reply_id']}:{reply.get('updated_at', reply.get('created_at', ''))}",
        }

    def run(self, input: dict) -> dict:
        return {"ok": False, "error": "Gmail replies must use the approval gateway"}


class ToolRegistry:
    """
    Central registry of all ORA tools.
    Tools are registered by name and invoked through run().
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_defaults()

    def _register_defaults(self):
        defaults = [
            BrowseTool(),
            WeatherTool(),
            CalendarTodayTool(),
            CalendarImminentTool(),
            CalendarCreateTool(),
            CalendarUpdateTool(),
            CalendarDeleteTool(),
            CalendarFreeSlotTool(),
            GmailSummaryTool(),
            GmailSendTool(),
            GmailDraftTool(),
            GmailReplyTool(),
            SheetsCreateTool(),
            SheetsReadTool(),
            SheetsWriteTool(),
            MpesaSyncSheetTool(),
            MpesaSpendTool(),
            KnowledgeSearchTool(),
            MemoryReadTool(),
            MemoryWriteTool(),
            TaskListTool(),
            GoalListTool(),
            TaskEngineStatsTool(),
            RecentAgentTasksTool(),
        ]
        for tool in defaults:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def run(self, name: str, input: dict | None = None, source: str = "tool_registry") -> dict:
        """Run one tool through typed validation and the central safety gateway."""
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: '{name}'"}
        from tool_gateway import submit_tool_call
        return submit_tool_call(tool, input or {}, source=source)

    def list_tools(self) -> list[dict]:
        """Return the complete typed contract for every registered tool."""
        return [t.get_spec().as_dict() for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def get_spec_for_action_type(self, action_type: str) -> ToolSpec | None:
        for tool in self._tools.values():
            spec = tool.get_spec()
            if spec.action_type == action_type:
                return spec
        return None

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={list(self._tools.keys())}>"


# ─── Global singleton ─────────────────────────────────────────────────────────
registry = ToolRegistry()