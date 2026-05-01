"""
ORA Brain — Multi-Agent Coordinator  (brain/router.py)
=======================================================

This IS the central brain. Every message that enters ORA passes through here.

The flow:
  1. classify_intent()     — 14 intent types, cached, zero AI cost
  2. build_pipeline()      — maps intent → ordered agent list
  3. MessageBus            — shared state that flows through the whole chain
  4. Coordinator.run()     — executes agents left-to-right, each builds on the last
  5. api.py /api/chat      — calls Coordinator.run() for agent-worthy queries

Agent registry (every ORA subsystem wired in):
  IntentAgent     — Intent_parser.py fast path, zero LLM cost
  MemoryAgent     — learning_engine + memory/profile + memory/preferences + events
  KnowledgeAgent  — knowledge/pipeline RAG search
  ResearchAgent   — research_agent.py deep_research (Tavily + Groq)
  ContentAgent    — agents/content_agent.py create_draft
  CodeAgent       — agents/code_agent.py scan / ask
  BriefingAgent   — tasks + goals + calendar + gmail + spend + weather + code health
  ChatAgent       — Groq with full context.py system prompt + all bus context
  NotifierAgent   — intelligence/notifier dual_notify (Telegram + FCM)

Pipeline examples:
  "research AI agents and write a LinkedIn post"
      → [memory, research, content, notify]
  "scan my repos"
      → [code, notify]
  "what are my tasks today"
      → [intent]        ← instant, zero LLM
  "brief me"
      → [briefing]
  "remember I prefer Python"
      → [memory]
  "write a blog post about ORA"
      → [memory, knowledge, content]

Backward compatibility:
  classify(query)   — still returns 'simple' | 'document' | 'complex'
  model_for(type)   — still returns (model_name, max_tokens)
  Both are imported by api.py for its simple Groq path.

Free-tier hardening:
  - Every agent wrapped in _run_with_timeout() (12s ceiling)
  - TTLCache prevents re-classifying identical queries
  - All context strings truncated to stay under RAM limits
  - Background learning is daemon-threaded and fire-and-forget
"""

from __future__ import annotations

import re
import json
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# FREE-TIER CONFIG
# ─────────────────────────────────────────────────────────────────────────────

_CFG = {
    "agent_timeout":  12,   # seconds per agent call
    "max_ctx_chars":  900,  # context string ceiling
    "max_mem_chars":  500,  # memory string ceiling
    "max_kb_chars":   500,  # KB string ceiling
    "max_history":    4,    # conversation turns to inject
    "cache_ttl":      300,  # 5-min TTL cache
}


# ─────────────────────────────────────────────────────────────────────────────
# TTL CACHE
# ─────────────────────────────────────────────────────────────────────────────

class _TTLCache:
    def __init__(self, ttl: int = 300):
        self._d: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        if key in self._d:
            v, ts = self._d[key]
            if time.time() - ts < self._ttl:
                return v
            del self._d[key]
        return None

    def set(self, key: str, value: Any) -> None:
        self._d[key] = (value, time.time())


_icache = _TTLCache(_CFG["cache_ttl"])
_pcache = _TTLCache(_CFG["cache_ttl"])


# ─────────────────────────────────────────────────────────────────────────────
# TIMEOUT HELPER (cross-platform — works on Windows + Linux/Render)
# ─────────────────────────────────────────────────────────────────────────────

class AgentTimeoutError(Exception):
    pass


def _run_with_timeout(fn: Any, *args: Any, timeout: int = _CFG["agent_timeout"],
                      **kwargs: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except FutureTimeoutError:
            raise AgentTimeoutError(f"Timed out after {timeout}s")


# ─────────────────────────────────────────────────────────────────────────────
# INTENT CLASSIFICATION  (14 types, pure regex, zero LLM cost)
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # Compound pipelines (most specific first)
    ("research_then_content", re.compile(
        r"\b(research.{1,40}(and|then).{1,20}(write|draft|create|post)"
        r"|find.{1,30}(and|then).{1,20}(write|draft))\b", re.I,
    )),
    # Single-step intents
    ("briefing", re.compile(
        r"\b(briefing|brief me|full brief|status update|what'?s? my status"
        r"|catch me up|morning brief|evening brief|what'?s? going on)\b", re.I,
    )),
    ("code", re.compile(
        r"\b(scan (repo|repos|code|branch)"
        r"|failing (ci|test|check|build)|stale pr|dead branch"
        r"|code (review|quality|issue|agent)"
        r"|open (github )?issue|repo health)\b", re.I,
    )),
    ("research", re.compile(
        r"\b(research|deep.?dive|investigate|look up|find out about"
        r"|latest on|news about|search for|web search)\b", re.I,
    )),
    ("content", re.compile(
        r"\b(write|draft|create|generate|compose|produce)\b.{0,40}"
        r"\b(post|article|blog|email|tweet|thread|linkedin|caption"
        r"|newsletter|script|copy|content)\b", re.I,
    )),
    ("memory_write", re.compile(
        r"\b(remember|note that|save that|store that"
        r"|my (name|preference|goal|email|role|company|style) is"
        r"|i (prefer|like|hate|use|work at|am|live in))\b", re.I,
    )),
    ("memory_read", re.compile(
        r"\b(what do you (know|remember) about me"
        r"|my (profile|preferences|facts)"
        r"|what have (i|you) (told|learned)|recall)\b", re.I,
    )),
    ("knowledge", re.compile(
        r"\b(summarize|summary|according to|from (the|my) (doc|file|pdf|notes)"
        r"|what does .{0,30} say|search (my )?knowledge|uploaded)\b", re.I,
    )),
    ("task", re.compile(
        r"\b(add task|create task|new task|remind me to"
        r"|mark .{0,20} (done|complete|finished)"
        r"|my (tasks|todos)|what('s| is) (pending|due|overdue))\b", re.I,
    )),
    ("goal", re.compile(
        r"\b(goal|objective|aim|target|milestone"
        r"|how am i doing|check.?in|track(ing)?)\b", re.I,
    )),
    ("calendar", re.compile(
        r"\b(calendar|meetings?|schedule|agenda|what'?s? on today"
        r"|any events|upcoming events)\b", re.I,
    )),
    ("weather", re.compile(
        r"\b(weather|raining|temperature|forecast|how'?s? the weather|is it hot)\b",
        re.I,
    )),
    ("spend", re.compile(
        r"\b(how much|spent|spend|mpesa|m-pesa|transactions|balance|money today)\b",
        re.I,
    )),
    ("complex", re.compile(
        r"\b(plan|strategy|analyze|compare|explain|why|how should"
        r"|what would|recommend|advice|steps|roadmap|breakdown)\b", re.I,
    )),
]


def classify_intent(query: str) -> str:
    """Return one of 14 intent types. Cached."""
    key    = query.lower().strip()
    cached = _icache.get(key)
    if cached:
        return cached

    for intent, pat in _INTENT_PATTERNS:
        if pat.search(query):
            _icache.set(key, intent)
            return intent

    result = "simple" if len(query.split()) <= 5 else "complex"
    _icache.set(key, result)
    return result


# ── Backward-compat aliases ────────────────────────────────────────────────────

def classify(query: str) -> str:
    """Maps new intents → 'simple' | 'document' | 'complex' for api.py."""
    intent = classify_intent(query)
    if intent in {"research", "research_then_content", "content", "code",
                  "goal", "complex", "briefing"}:
        return "complex"
    if intent == "knowledge":
        return "document"
    return "simple"


def model_for(query_type: str) -> Tuple[str, int]:
    """Returns (model_name, max_tokens). Free-tier optimised."""
    if query_type == "simple":
        return "llama-3.1-8b-instant", 160
    if query_type == "document":
        return "llama-3.1-8b-instant", 320
    return "llama-3.3-70b-versatile", 520


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE MAP
# ─────────────────────────────────────────────────────────────────────────────

def build_pipeline(intent: str) -> List[str]:
    """Maps intent → ordered list of agent names."""
    cached = _pcache.get(intent)
    if cached:
        return cached

    _MAP: Dict[str, List[str]] = {
        "research_then_content": ["memory", "research", "content", "notify"],
        "research":              ["memory", "research",             "notify"],
        "content":               ["memory", "knowledge", "content"],
        "code":                  ["code",                           "notify"],
        "memory_write":          ["memory"],
        "memory_read":           ["memory", "chat"],
        "knowledge":             ["knowledge", "chat"],
        # Fast-path intents handled entirely by Intent_parser.py (zero LLM)
        "task":                  ["intent"],
        "goal":                  ["intent"],
        "calendar":              ["intent"],
        "weather":               ["intent"],
        "spend":                 ["intent"],
        "briefing":              ["briefing"],
        "complex":               ["memory", "knowledge", "chat"],
        "simple":                ["chat"],
    }
    result = _MAP.get(intent, ["chat"])
    _pcache.set(intent, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE BUS
# ─────────────────────────────────────────────────────────────────────────────

class MessageBus:
    """
    Shared mutable state that flows through the agent pipeline in one run.
    Each agent reads what it needs and posts its output back.
    Thread-safe via a single lock.
    """
    __slots__ = (
        "_lock", "query", "intent", "started_at",
        "context", "reply", "chain_log",
        "memory_ctx", "kb_ctx",
        "research_result", "content_draft", "code_result",
        "task_result", "goal_result", "memory_result",
    )

    def __init__(self, query: str, intent: str):
        self._lock           = threading.Lock()
        self.query           = query
        self.intent          = intent
        self.started_at      = datetime.now().isoformat()
        self.context:  List[Dict[str, str]] = []
        self.reply:    str           = ""
        self.chain_log: List[Dict[str, Any]] = []
        self.memory_ctx: str         = ""
        self.kb_ctx:     str         = ""
        self.research_result: Optional[Dict[str, Any]] = None
        self.content_draft:   Optional[Dict[str, Any]] = None
        self.code_result:     Optional[Dict[str, Any]] = None
        self.task_result:     Optional[Dict[str, Any]] = None
        self.goal_result:     Optional[Dict[str, Any]] = None
        self.memory_result:   Optional[Dict[str, Any]] = None

    def post(self, agent: str, key: str, value: Any, ms: int = 0) -> None:
        with self._lock:
            setattr(self, key, value)
            if len(self.chain_log) < 12:
                self.chain_log.append({
                    "agent": agent, "key": key,
                    "duration_ms": ms, "ts": datetime.now().isoformat(),
                })

    def add_context(self, agent: str, summary: str) -> None:
        with self._lock:
            self.context.append({
                "agent":   agent,
                "summary": summary[:_CFG["max_ctx_chars"]],
            })
            if len(self.context) > 6:
                self.context.pop(0)

    def full_context(self) -> str:
        return "\n\n".join(
            f"[{c['agent']}]\n{c['summary'][:300]}"
            for c in self.context[-4:]
        )


# ─────────────────────────────────────────────────────────────────────────────
# TIMING HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _ms() -> int:
    return int(time.time() * 1000)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _run_intent_agent(bus: MessageBus) -> None:
    t0 = _ms()
    try:
        from Intent_parser import parse_intent, execute_intent
        intent_obj = parse_intent(bus.query)
        if intent_obj:
            result = execute_intent(intent_obj)
            if result:
                bus.reply = result
                bus.post("IntentAgent", "task_result",
                         {"type": intent_obj["type"], "reply": result}, _ms() - t0)
                return
    except Exception as e:
        print(f"[INTENT_AGENT] {e}")
    _run_chat_agent(bus)


def _run_memory_agent(bus: MessageBus) -> None:
    t0    = _ms()
    parts: List[str] = []

    try:
        from intelligence.learning_engine import get_facts_as_context, extract_explicit_facts
        facts = get_facts_as_context(limit=15)
        if facts:
            parts.append(facts[:_CFG["max_mem_chars"]])
        if bus.intent == "memory_write":
            extract_explicit_facts(bus.query)
            bus.reply = "Got it — I've remembered that."
            bus.memory_ctx = "\n\n".join(parts)
            bus.add_context("MemoryAgent", "Stored new fact.")
            bus.post("MemoryAgent", "memory_result",
                     {"action": "stored", "from": bus.query}, _ms() - t0)
            return
    except Exception as e:
        print(f"[MEMORY_AGENT] facts: {e}")

    try:
        from memory.profile import get_all_profile
        profile = get_all_profile()
        if profile:
            lines = [f"{k}: {v}" for k, v in list(profile.items())[:8]]
            parts.append("Profile:\n" + "\n".join(lines))
    except Exception as e:
        print(f"[MEMORY_AGENT] profile: {e}")

    try:
        from memory.preferences import get_preferences
        prefs = get_preferences()
        if prefs:
            plines = [f"{r[0]}/{r[1]}: {r[2]}" for r in prefs[:6]]
            parts.append("Preferences:\n" + "\n".join(plines))
    except Exception as e:
        print(f"[MEMORY_AGENT] prefs: {e}")

    try:
        from memory.events import get_important_events
        events = get_important_events(min_importance=7, limit=4)
        if events:
            elines = [f"- {e[1]}" for e in events]
            parts.append("Important events:\n" + "\n".join(elines))
    except Exception as e:
        print(f"[MEMORY_AGENT] events: {e}")

    bus.memory_ctx = "\n\n".join(parts)[:_CFG["max_mem_chars"]]
    bus.add_context("MemoryAgent", bus.memory_ctx[:300] or "No memory context.")
    bus.chain_log.append({
        "agent": "MemoryAgent", "key": "memory_ctx",
        "duration_ms": _ms() - t0, "ts": datetime.now().isoformat(),
    })


def _run_knowledge_agent(bus: MessageBus) -> None:
    t0 = _ms()
    try:
        from knowledge.pipeline import search_and_format
        kb = search_and_format(bus.query, n_results=3) or ""
        bus.kb_ctx = kb[:_CFG["max_kb_chars"]]
        if bus.kb_ctx:
            bus.add_context("KnowledgeAgent", bus.kb_ctx[:300])
    except Exception as e:
        print(f"[KNOWLEDGE_AGENT] {e}")
    bus.chain_log.append({
        "agent": "KnowledgeAgent", "key": "kb_ctx",
        "duration_ms": _ms() - t0, "ts": datetime.now().isoformat(),
    })


def _run_research_agent(bus: MessageBus) -> None:
    t0 = _ms()
    try:
        from research_agent import deep_research
        result    = _run_with_timeout(deep_research, bus.query, timeout=10)
        synthesis = result.get("content") or result.get("synthesis", "")
        bus.post("ResearchAgent", "research_result", result, _ms() - t0)
        if synthesis:
            bus.add_context("ResearchAgent", synthesis[:_CFG["max_ctx_chars"]])
        if bus.intent == "research":
            bus.reply = synthesis[:600] or "Research complete — no synthesis generated."
    except AgentTimeoutError:
        bus.reply = "Research timed out. Try a more focused query."
        bus.add_context("ResearchAgent", "Research timed out.")
    except Exception as e:
        print(f"[RESEARCH_AGENT] {e}")
        bus.add_context("ResearchAgent", f"Research failed: {str(e)[:100]}")


def _run_content_agent(bus: MessageBus) -> None:
    t0 = _ms()
    try:
        from agents.content_agent import create_draft
        extra = ""
        if bus.research_result:
            extra = (bus.research_result.get("content")
                     or bus.research_result.get("synthesis", ""))[:800]
        elif bus.kb_ctx:
            extra = bus.kb_ctx[:500]
        draft = create_draft(
            topic        = bus.query,
            content_type = _detect_content_type(bus.query),
            tone         = _detect_tone(bus.query),
            length       = "medium",
            extra_context= extra,
        )
        draft_text = draft.get("draft_text", "")
        bus.post("ContentAgent", "content_draft", draft, _ms() - t0)
        bus.reply = draft_text
        bus.add_context("ContentAgent",
                        f"Draft ({_detect_content_type(bus.query)}): {draft_text[:150]}…")
    except Exception as e:
        print(f"[CONTENT_AGENT] {e}")
        traceback.print_exc()
        bus.add_context("ContentAgent", f"Content creation failed: {str(e)[:100]}")


def _detect_content_type(q: str) -> str:
    ql = q.lower()
    for kw, ct in [
        ("linkedin", "linkedin"), ("twitter", "twitter"),  ("tweet",   "twitter"),
        ("thread",   "twitter"),  ("instagram","instagram"),("email",   "email"),
        ("blog",     "blog"),     ("newsletter","newsletter"),("script", "script"),
        ("caption",  "caption"),
    ]:
        if kw in ql:
            return ct
    return "post"


def _detect_tone(q: str) -> str:
    ql = q.lower()
    if any(w in ql for w in ("professional", "formal", "business")):    return "professional"
    if any(w in ql for w in ("casual", "friendly", "conversational")):  return "casual"
    if any(w in ql for w in ("inspiring", "motivational")):             return "inspirational"
    if any(w in ql for w in ("technical", "developer", "engineering")): return "technical"
    if any(w in ql for w in ("funny", "humor", "witty")):               return "humorous"
    return "professional"


def _run_code_agent(bus: MessageBus) -> None:
    t0 = _ms()
    try:
        from agents.code_agent import scan_all_repos, scan_repo, ask_code_agent
        ql = bus.query.lower()
        def _work():
            if re.search(r"\b(scan all|all repos)\b", ql):
                return scan_all_repos()
            m = re.search(r"\b(scan|check|review)\s+([a-zA-Z0-9_\-\.]+)\b", bus.query, re.I)
            if m:
                return scan_repo(m.group(2))
            return {"answer": ask_code_agent(bus.query)}
        result  = _run_with_timeout(_work, timeout=10)
        summary = _build_code_summary(result)
        bus.post("CodeAgent", "code_result", result, _ms() - t0)
        bus.reply = summary
        bus.add_context("CodeAgent", summary[:400])
    except AgentTimeoutError:
        bus.reply = "Code scan timed out. Target a specific repo."
    except Exception as e:
        print(f"[CODE_AGENT] {e}")
        traceback.print_exc()
        bus.add_context("CodeAgent", f"Code agent failed: {str(e)[:100]}")


def _build_code_summary(result: Dict[str, Any]) -> str:
    if "answer" in result:
        return str(result["answer"])[:500]
    if "repos" in result:
        lines = [f"{r['repo']}: {r['health']}/100 ({r.get('findings',0)} findings)"
                 for r in result.get("repos", [])[:4]]
        return f"Scanned {result.get('scanned',0)} repos:\n" + "\n".join(lines)
    if "health" in result:
        return (f"{result.get('repo')}: health {result.get('health')}/100. "
                f"{result.get('summary','')[:200]}")
    return str(result)[:300]


def _run_briefing_agent(bus: MessageBus) -> None:
    t0    = _ms()
    parts: List[str] = ["Here's your status:\n"]

    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if tasks:
            now     = datetime.now()
            overdue = [t for t in tasks if t[4] and _parse_dt(t[4]) < now]
            high    = [t for t in tasks if t[2] == "high"]
            lines   = [
                f"  {'🔴' if t[2]=='high' else '🟡'} [{t[0]}] {t[1][:55]}"
                + (" ⚠ OVERDUE" if t[4] and _parse_dt(t[4]) < now else "")
                for t in tasks[:6]
            ]
            parts.append(
                f"📋 **Tasks** — {len(tasks)} pending"
                + (f", {len(overdue)} overdue" if overdue else "")
                + (f", {len(high)} high priority" if high else "")
                + ":\n" + "\n".join(lines)
            )
        else:
            parts.append("📋 **Tasks** — All clear.")
    except Exception as e:
        print(f"[BRIEFING] tasks: {e}")

    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if goals:
            avg   = int(sum(g.get("progress", 0) for g in goals) / len(goals))
            lines = [
                f"  • {g['goal'][:55]} — {g['progress']}%"
                + (f" (due {g['due_at'][:10]})" if g.get("due_at") else "")
                for g in goals[:4]
            ]
            parts.append(f"🎯 **Goals** — {len(goals)} active, {avg}% avg:\n"
                         + "\n".join(lines))
    except Exception as e:
        print(f"[BRIEFING] goals: {e}")

    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            parts.append("📅 **Calendar** — "
                         + format_events_for_context(events)[:300])
        else:
            parts.append("📅 **Calendar** — Nothing scheduled today.")
    except Exception:
        pass

    try:
        from connectors.gmail import get_gmail_summary
        from connectors.google_auth import is_authorized
        if is_authorized():
            gmail = get_gmail_summary()
            if gmail and gmail.get("unread_count", 0) > 0:
                parts.append(f"📧 **Email** — {gmail['unread_count']} unread")
    except Exception:
        pass

    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        def _f(v: Any) -> float:
            try:
                return float(v) if v is not None else 0.0
            except Exception:
                return 0.0
        today = _f(get_today_spend())
        avg   = _f(get_average_daily_spend())
        if today > 0:
            trend = "↑ above avg" if avg and today > avg * 1.3 else "≈ normal"
            parts.append(f"💳 **Spend** — KES {today:,.0f} today ({trend})")
    except Exception:
        pass

    try:
        from connectors.weather import get_weather_summary
        w = get_weather_summary()
        if w:
            parts.append(f"🌤 **Weather** — {w}")
    except Exception:
        pass

    try:
        from agents.code_agent import get_code_stats
        stats = get_code_stats()
        if stats.get("total_runs", 0) > 0:
            parts.append(
                f"⌥ **Code** — {stats.get('open',0)} open findings, "
                f"avg health {stats.get('avg_health',0)}/100"
                + (f", ⚠ {stats['critical']} critical" if stats.get("critical") else "")
            )
    except Exception:
        pass

    bus.reply = "\n\n".join(parts)
    bus.post("BriefingAgent", "task_result", {"briefing": bus.reply}, _ms() - t0)


def _run_chat_agent(bus: MessageBus) -> None:
    if bus.reply:
        return
    t0 = _ms()
    try:
        from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
        from groq import Groq
        from context import build_system_prompt
        from database import get_conversation_history

        client = Groq(api_key=GROQ_API_KEY)
        system = build_system_prompt(query=bus.query)

        ctx_text = bus.full_context()
        if ctx_text:
            system += f"\n\n## AGENT CONTEXT\n{ctx_text[:_CFG['max_ctx_chars']]}"
        if bus.memory_ctx:
            system += f"\n\n## MEMORY\n{bus.memory_ctx[:_CFG['max_mem_chars']]}"
        if bus.kb_ctx:
            system += f"\n\n## KNOWLEDGE BASE\n{bus.kb_ctx[:_CFG['max_kb_chars']]}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        history = get_conversation_history(limit=_CFG["max_history"])
        for role, content, _ in history:
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content[:250]})
        messages.append({"role": "user", "content": bus.query})

        model   = GROQ_MODEL_FALLBACK if bus.intent == "simple" else GROQ_MODEL_PRIMARY
        max_tok = 160 if bus.intent == "simple" else 520

        def _call() -> Any:
            try:
                return client.chat.completions.create(
                    model=model, messages=messages,  # type: ignore[arg-type]
                    max_tokens=max_tok, temperature=0.35,
                )
            except Exception:
                return client.chat.completions.create(
                    model=GROQ_MODEL_FALLBACK, messages=messages,  # type: ignore[arg-type]
                    max_tokens=220, temperature=0.35,
                )

        resp      = _run_with_timeout(_call, timeout=10)
        bus.reply = (resp.choices[0].message.content or "").strip()
        bus.chain_log.append({
            "agent": "ChatAgent", "key": "reply",
            "duration_ms": _ms() - t0, "ts": datetime.now().isoformat(),
        })

    except AgentTimeoutError:
        bus.reply = "Taking too long — try a simpler question."
    except Exception as e:
        print(f"[CHAT_AGENT] {e}")
        traceback.print_exc()
        bus.reply = "ORA error. Please try again."


def _run_notifier_agent(bus: MessageBus) -> None:
    _notify_intents = {"research", "research_then_content", "code"}
    if bus.intent not in _notify_intents:
        return
    t0 = _ms()
    try:
        from intelligence.notifier import dual_notify
        title, body = _build_notification(bus)
        if body:
            dual_notify(title=title, body=body)
            bus.chain_log.append({
                "agent": "NotifierAgent", "key": "notified",
                "duration_ms": _ms() - t0, "ts": datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[NOTIFIER_AGENT] {e}")


def _build_notification(bus: MessageBus) -> Tuple[str, str]:
    if bus.intent == "code" and bus.code_result:
        return "ORA Code Agent", _build_code_summary(bus.code_result)[:200]
    if bus.intent in ("research", "research_then_content") and bus.research_result:
        title_text = bus.research_result.get("title", bus.query[:60])
        body = f"Research complete: {title_text}"
        if bus.content_draft:
            body += f" → Draft created ({_detect_content_type(bus.query)})"
        return "ORA Research", body
    return "ORA", (bus.reply[:200] if bus.reply else "")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT FUNCTION MAP
# ─────────────────────────────────────────────────────────────────────────────

_AGENT_FN: Dict[str, Any] = {
    "intent":    _run_intent_agent,
    "memory":    _run_memory_agent,
    "knowledge": _run_knowledge_agent,
    "research":  _run_research_agent,
    "content":   _run_content_agent,
    "code":      _run_code_agent,
    "briefing":  _run_briefing_agent,
    "chat":      _run_chat_agent,
    "notify":    _run_notifier_agent,
}


# ─────────────────────────────────────────────────────────────────────────────
# COORDINATOR — public entry point
# ─────────────────────────────────────────────────────────────────────────────

class Coordinator:
    """
    The single entry point for all ORA messages.
    Called by api.py /api/chat:
        result = Coordinator.run(text, save_history=False)
    """

    @staticmethod
    def run(query: str, save_history: bool = True) -> Dict[str, Any]:
        intent   = classify_intent(query)
        pipeline = build_pipeline(intent)
        bus      = MessageBus(query=query, intent=intent)

        for agent_name in pipeline:
            fn = _AGENT_FN.get(agent_name)
            if fn is None:
                print(f"[COORDINATOR] Unknown agent '{agent_name}' — skipping")
                continue
            try:
                fn(bus)
            except AgentTimeoutError as e:
                print(f"[COORDINATOR] Timeout in '{agent_name}': {e}")
                bus.add_context(agent_name, "Agent timed out")
                if not bus.reply:
                    bus.reply = (f"The {agent_name} step timed out. "
                                 "Please simplify your request.")
            except Exception as e:
                print(f"[COORDINATOR] '{agent_name}' error: {e}")
                traceback.print_exc()

        if save_history and bus.reply:
            try:
                from database import save_conversation
                save_conversation("user",      query[:300])
                save_conversation("assistant", bus.reply[:300])
            except Exception:
                pass
            try:
                from intelligence.learning_engine import (
                    extract_facts_from_exchange, extract_explicit_facts,
                )
                extract_explicit_facts(query)
                threading.Thread(
                    target=extract_facts_from_exchange,
                    args=(query, bus.reply),
                    daemon=True,
                ).start()
            except Exception:
                pass

        return {
            "reply":      bus.reply or "No response generated.",
            "query_type": classify(query),
            "intent":     intent,
            "pipeline":   pipeline,
            "chain_log":  bus.chain_log,
            "research":   bus.research_result,
            "draft":      bus.content_draft,
            "code":       bus.code_result,
        }


# Module-level convenience
coordinator = Coordinator()

def run(query: str) -> Dict[str, Any]:
    return Coordinator.run(query)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.max