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


# ─── Base Tool ────────────────────────────────────────────────────────────────

class Tool(ABC):
    name: str = ""
    description: str = ""

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
        from research_agent import deep_research
        query = input.get("query", "")
        if not query:
            return {"ok": False, "error": "query required"}
        result = deep_research(query)
        return {
            "ok": True,
            "content": result.get("content") or result.get("result", ""),
            "sources": result.get("sources", []),
            "title": result.get("title", ""),
        }


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
        from connectors.github import get_github_summary
        summary = get_github_summary()
        return {"ok": True, "summary": summary}


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


# ─── Registry ─────────────────────────────────────────────────────────────────

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
            WebSearchTool(),
            WeatherTool(),
            CalendarTodayTool(),
            CalendarImminentTool(),
            GmailSummaryTool(),
            GitHubSummaryTool(),
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

    def run(self, name: str, input: dict | None = None) -> dict:
        """
        Run a tool by name. Returns {"ok": False, "error": ...} if not found.
        """
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: '{name}'"}
        return tool.safe_run(input or {})

    def list_tools(self) -> list[dict]:
        """Return all registered tools with name and description."""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={list(self._tools.keys())}>"


# ─── Global singleton ─────────────────────────────────────────────────────────
registry = ToolRegistry()
