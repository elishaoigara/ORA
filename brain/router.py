"""
ORA Brain — Multi-Agent Coordinator (Free Tier Optimized)
===========================================================
Optimized for Render free tier with cross-platform compatibility.
"""

from __future__ import annotations

import re
import json
import time
import threading
import functools
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from contextlib import contextmanager
import sys

# ─────────────────────────────────────────────────────────────────────────────
# FREE TIER CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

FREE_TIER_CONFIG = {
    "agent_timeout_seconds": 12,        # Render free tier: 15s timeout buffer
    "max_context_chars": 800,           # Reduced from 1200
    "max_memory_chars": 400,            # Reduced from 600
    "max_kb_chars": 400,                # Reduced from 600
    "max_history_messages": 3,          # Reduced from 6
    "cache_ttl_seconds": 300,           # 5 minute cache
    "max_parallel_agents": 1,           # Disable parallel (memory constrained)
    "enable_background_learning": False, # Disable to save CPU
}

# Simple cache for expensive operations
class TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        self._cache.clear()

_intent_cache = TTLCache(FREE_TIER_CONFIG["cache_ttl_seconds"])
_pipeline_cache = TTLCache(FREE_TIER_CONFIG["cache_ttl_seconds"])

# ─────────────────────────────────────────────────────────────────────────────
# CROSS-PLATFORM TIMEOUT (Works on Windows & Unix)
# ─────────────────────────────────────────────────────────────────────────────

class TimeoutError(Exception):
    """Custom timeout exception"""
    pass

@contextmanager
def agent_timeout(agent_name: str, seconds: int = FREE_TIER_CONFIG["agent_timeout_seconds"]):
    """
    Cross-platform timeout context manager using threading.
    Works on Windows, macOS, and Linux.
    """
    result = {"timed_out": False}
    
    def timeout_checker():
        time.sleep(seconds)
        result["timed_out"] = True
    
    timer = threading.Thread(target=timeout_checker, daemon=True)
    timer.start()
    
    try:
        yield
        if result["timed_out"]:
            raise TimeoutError(f"Agent '{agent_name}' exceeded {seconds}s timeout")
    finally:
        # No need to stop the thread, it's daemon and will exit when main thread ends
        pass

# Alternative: Use concurrent.futures for more precise control
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

def run_with_timeout(func, args=(), kwargs=None, timeout=12):
    """Run a function with timeout using ThreadPoolExecutor"""
    if kwargs is None:
        kwargs = {}
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            raise TimeoutError(f"Function timed out after {timeout}s")

# ─────────────────────────────────────────────────────────────────────────────
# TYPE DEFINITIONS (Fix Pylance errors)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from groq.types.chat import (
        ChatCompletionMessageParam,
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
        ChatCompletionAssistantMessageParam,
    )
except ImportError:
    # Fallback for when groq is not installed
    ChatCompletionMessageParam = dict
    ChatCompletionSystemMessageParam = dict
    ChatCompletionUserMessageParam = dict
    ChatCompletionAssistantMessageParam = dict

def build_typed_message(role: str, content: str):
    """Build properly typed message for Groq API"""
    try:
        if role == "system":
            return ChatCompletionSystemMessageParam(role="system", content=content)
        elif role == "user":
            return ChatCompletionUserMessageParam(role="user", content=content)
        elif role == "assistant":
            return ChatCompletionAssistantMessageParam(role="assistant", content=content)
        else:
            return ChatCompletionUserMessageParam(role="user", content=content)
    except (NameError, TypeError):
        # Fallback for when types aren't available
        return {"role": role, "content": content}

# ─────────────────────────────────────────────────────────────────────────────
# INTENT CLASSIFICATION (Cached)
# ─────────────────────────────────────────────────────────────────────────────

# Simplified patterns for faster matching
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("research_then_content", re.compile(
        r"\b(research.*(and|then).*(write|draft|create)|find.*write)\b",
        re.IGNORECASE,
    )),
    ("code", re.compile(
        r"\b(scan (repo|code)|failing (ci|test)|stale pr|code (review|quality))\b",
        re.IGNORECASE,
    )),
    ("research", re.compile(
        r"\b(research|deep.?dive|investigate|search for|web search)\b",
        re.IGNORECASE,
    )),
    ("content", re.compile(
        r"\b(write|draft|create).{0,30}(post|article|blog|email|tweet)\b",
        re.IGNORECASE,
    )),
    ("memory_write", re.compile(
        r"\b(remember|note that|save that|my (name|preference|goal) is)\b",
        re.IGNORECASE,
    )),
    ("memory_read", re.compile(
        r"\b(what do you (know|remember) about me|my (profile|preferences))\b",
        re.IGNORECASE,
    )),
    ("task", re.compile(
        r"\b(add task|create task|my tasks|mark.*done|remind me)\b",
        re.IGNORECASE,
    )),
    ("goal", re.compile(
        r"\b(goal|objective|progress|check.?in)\b",
        re.IGNORECASE,
    )),
    ("knowledge", re.compile(
        r"\b(knowledge|document|pdf|uploaded|from the (doc|file))\b",
        re.IGNORECASE,
    )),
]

def classify_intent(query: str) -> str:
    """Cached intent classification"""
    cache_key = query.lower().strip()
    cached = _intent_cache.get(cache_key)
    if cached:
        return cached
    
    q = query.strip()
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(q):
            _intent_cache.set(cache_key, intent)
            return intent
    
    # Quick length check (no complex regex)
    intent = "simple" if len(q.split()) <= 5 else "complex"
    _intent_cache.set(cache_key, intent)
    return intent

def classify(query: str) -> str:
    """Backward-compat"""
    intent = classify_intent(query)
    if intent in {"research", "research_then_content", "content", "code", "goal", "complex"}:
        return "complex"
    if intent in {"knowledge"}:
        return "document"
    return "simple"

def model_for(query_type: str) -> tuple[str, int]:
    """Returns (model_name, max_tokens) - optimized for free tier"""
    if query_type == "simple":
        return "llama-3.1-8b-instant", 150
    if query_type == "document":
        return "llama-3.1-8b-instant", 300
    return "llama-3.3-70b-versatile", 500

# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE BUS (Memory Optimized)
# ─────────────────────────────────────────────────────────────────────────────

class MessageBus:
    """Shared state with memory optimization for free tier"""
    __slots__ = (
        '_lock', 'query', 'intent', 'started_at', 'context',
        'reply', 'chain_log', 'memory_ctx', 'kb_ctx',
        'research_result', 'content_draft', 'code_result',
        'task_result', 'goal_result', 'memory_result'
    )
    
    def __init__(self, query: str, intent: str):
        self._lock = threading.Lock()
        self.query: str = query
        self.intent: str = intent
        self.started_at: str = datetime.now().isoformat()
        
        self.context: List[Dict] = []
        self.reply: str = ""
        self.chain_log: List[Dict] = []
        
        self.memory_ctx: str = ""
        self.kb_ctx: str = ""
        
        self.research_result: Optional[Dict] = None
        self.content_draft: Optional[Dict] = None
        self.code_result: Optional[Dict] = None
        self.task_result: Optional[Dict] = None
        self.goal_result: Optional[Dict] = None
        self.memory_result: Optional[Dict] = None
    
    def post(self, agent_name: str, key: str, value: Any, duration_ms: int = 0) -> None:
        with self._lock:
            setattr(self, key, value)
            if len(self.chain_log) < 10:
                self.chain_log.append({
                    "agent": agent_name,
                    "key": key,
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now().isoformat(),
                })
    
    def add_context(self, agent_name: str, summary: str) -> None:
        with self._lock:
            truncated = summary[:FREE_TIER_CONFIG["max_context_chars"]]
            self.context.append({"agent": agent_name, "summary": truncated})
            if len(self.context) > 5:
                self.context.pop(0)
    
    def full_context(self) -> str:
        return "\n\n".join(
            f"[{c['agent']}]\n{c['summary'][:200]}" for c in self.context[-3:]
        )

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE MAP (Cached)
# ─────────────────────────────────────────────────────────────────────────────

def build_pipeline(intent: str) -> List[str]:
    """Cached pipeline builder"""
    cache_key = intent
    cached = _pipeline_cache.get(cache_key)
    if cached:
        return cached
    
    pipelines: Dict[str, List[str]] = {
        "research_then_content": ["research", "content"],
        "research": ["research"],
        "content": ["knowledge", "content"],
        "code": ["code"],
        "memory_write": ["memory"],
        "memory_read": ["memory"],
        "knowledge": ["knowledge"],
        "task": ["task"],
        "goal": ["goal"],
        "complex": ["knowledge", "chat"],
        "simple": ["chat"],
    }
    result = pipelines.get(intent, ["chat"])
    _pipeline_cache.set(cache_key, result)
    return result

# ─────────────────────────────────────────────────────────────────────────────
# AGENTS (Lazy imports, timeout-protected)
# ─────────────────────────────────────────────────────────────────────────────

def _time_ms() -> int:
    return int(time.time() * 1000)

# ── Memory Agent ─────────────────────────────────────────────────────────────
def _run_memory_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    parts: List[str] = []
    
    try:
        from intelligence.learning_engine import get_facts_as_context
        
        facts = get_facts_as_context(limit=10)
        if facts:
            parts.append(facts[:FREE_TIER_CONFIG["max_memory_chars"]])
        
        if bus.intent == "memory_write":
            from intelligence.learning_engine import extract_explicit_facts
            extract_explicit_facts(bus.query)
            bus.reply = "Got it — I've remembered that."
    except ImportError:
        pass
    except Exception as e:
        print(f"[MEMORY] {e}")
    
    bus.memory_ctx = "\n\n".join(parts)[:FREE_TIER_CONFIG["max_memory_chars"]]
    bus.add_context("Memory", bus.memory_ctx[:200] or "No memory.")

# ── Knowledge Agent ──────────────────────────────────────────────────────────
def _run_knowledge_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from knowledge.pipeline import search_and_format
        kb = search_and_format(bus.query, n_results=2)
        bus.kb_ctx = (kb or "")[:FREE_TIER_CONFIG["max_kb_chars"]]
        if bus.kb_ctx:
            bus.add_context("Knowledge", bus.kb_ctx[:200])
    except Exception as e:
        print(f"[KNOWLEDGE] {e}")
        bus.kb_ctx = ""

# ── Research Agent with Timeout ──────────────────────────────────────────────
def _run_research_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from research_agent import deep_research
        
        # Use run_with_timeout for better timeout control
        def do_research():
            return deep_research(bus.query)
        
        result = run_with_timeout(do_research, timeout=10)
        bus.research_result = result
        synthesis = result.get("content", "") or result.get("synthesis", "")
        
        if synthesis:
            bus.add_context("Research", synthesis[:FREE_TIER_CONFIG["max_context_chars"]])
        
        if bus.intent == "research":
            bus.reply = synthesis[:500] or "Research complete."
    except TimeoutError:
        bus.reply = "Research timed out. Please try a simpler query."
        bus.add_context("Research", "Research timed out")
    except Exception as e:
        print(f"[RESEARCH] {e}")
        bus.add_context("Research", f"Research failed: {str(e)[:100]}")

# ── Content Agent ────────────────────────────────────────────────────────────
def _run_content_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from agents.content_agent import create_draft
        
        extra = ""
        if bus.research_result:
            extra = (bus.research_result.get("content") or 
                    bus.research_result.get("synthesis", ""))[:800]
        elif bus.kb_ctx:
            extra = bus.kb_ctx[:400]
        
        content_type = _detect_content_type(bus.query)
        tone = _detect_tone(bus.query)
        
        draft = create_draft(
            topic=bus.query,
            content_type=content_type,
            tone=tone,
            length="short",
            extra_context=extra,
        )
        
        bus.content_draft = draft
        draft_text = draft.get("draft_text", "")
        bus.reply = draft_text[:800]
        bus.add_context("Content", f"Draft: {draft_text[:100]}...")
    except Exception as e:
        print(f"[CONTENT] {e}")
        bus.add_context("Content", f"Content failed: {str(e)[:100]}")

def _detect_content_type(query: str) -> str:
    q = query.lower()
    if "linkedin" in q: return "linkedin"
    if "tweet" in q or "twitter" in q: return "twitter"
    if "email" in q: return "email"
    if "blog" in q: return "blog"
    return "post"

def _detect_tone(query: str) -> str:
    q = query.lower()
    if "professional" in q: return "professional"
    if "casual" in q: return "casual"
    return "professional"

# ── Code Agent ───────────────────────────────────────────────────────────────
def _run_code_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from agents.code_agent import scan_all_repos, ask_code_agent
        
        def do_code_work():
            if "scan all" in bus.query.lower():
                return scan_all_repos()
            else:
                return ask_code_agent(bus.query)
        
        result = run_with_timeout(do_code_work, timeout=10)
        
        if isinstance(result, dict) and "scanned" in result:
            summary = f"Scanned {result.get('scanned', 0)} repos."
        else:
            summary = str(result)[:300]
        
        bus.code_result = {"result": result}
        bus.reply = summary
        bus.add_context("Code", summary[:200])
    except TimeoutError:
        bus.reply = "Code scan timed out. Try a more specific query."
    except Exception as e:
        print(f"[CODE] {e}")
        bus.add_context("Code", f"Code failed: {str(e)[:100]}")

# ── Task Agent ───────────────────────────────────────────────────────────────
def _run_task_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from database import get_tasks, add_task, complete_task
        
        ql = bus.query.lower()
        
        if any(word in ql for word in ["mark", "complete", "done"]):
            tasks = get_tasks("pending")
            if tasks:
                complete_task(tasks[0][0])
                bus.reply = f"✓ Marked '{tasks[0][1][:50]}' as done."
            else:
                bus.reply = "No pending tasks to complete."
        elif any(word in ql for word in ["add", "create", "new"]):
            words = bus.query.split()
            task_text = " ".join(words[words.index("task")+1:] if "task" in words else words[-5:])
            if task_text:
                add_task(task_text[:50], "medium", None)
                bus.reply = f"Task added: '{task_text[:50]}'"
            else:
                bus.reply = "What task should I add?"
        else:
            tasks = get_tasks("pending")
            if tasks:
                lines = [f"• {t[1][:50]}" for t in tasks[:5]]
                bus.reply = f"{len(tasks)} pending tasks:\n" + "\n".join(lines)
            else:
                bus.reply = "No pending tasks."
        
        bus.add_context("Task", bus.reply[:200])
    except Exception as e:
        print(f"[TASK] {e}")
        bus.add_context("Task", f"Task failed: {str(e)[:100]}")

# ── Goal Agent ───────────────────────────────────────────────────────────────
def _run_goal_agent(bus: MessageBus) -> None:
    t0 = _time_ms()
    try:
        from intelligence.goals_engine import get_goals, add_goal
        
        if any(word in bus.query.lower() for word in ["add", "set"]):
            words = bus.query.split()
            goal_text = " ".join(words[words.index("goal")+1:] if "goal" in words else words[-5:])
            if goal_text:
                add_goal(goal_text[:80])
                bus.reply = f"Goal set: '{goal_text[:80]}'"
            else:
                bus.reply = "What goal would you like to set?"
        else:
            goals = get_goals("active")
            if goals:
                avg_progress = sum(g.get("progress", 0) for g in goals) // len(goals)
                lines = [f"• {g['goal'][:40]} — {g['progress']}%" for g in goals[:3]]
                bus.reply = f"{len(goals)} goals, avg {avg_progress}%:\n" + "\n".join(lines)
            else:
                bus.reply = "No active goals. Say 'add goal [description]' to set one."
        
        bus.add_context("Goal", bus.reply[:200])
    except Exception as e:
        print(f"[GOAL] {e}")
        bus.add_context("Goal", f"Goal failed: {str(e)[:100]}")

# ── Chat Agent (Fixed Type Error) ────────────────────────────────────────────
def _run_chat_agent(bus: MessageBus) -> None:
    """Terminal agent with proper typing and free tier optimizations"""
    if bus.reply:
        return
    
    t0 = _time_ms()
    try:
        from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
        from groq import Groq
        from context import build_system_prompt
        from database import get_conversation_history
        
        client = Groq(api_key=GROQ_API_KEY)
        
        system = build_system_prompt(query=bus.query)
        
        ctx_text = bus.full_context()
        if ctx_text:
            system += f"\n\n## CONTEXT\n{ctx_text[:FREE_TIER_CONFIG['max_context_chars']]}"
        
        if bus.memory_ctx:
            system += f"\n\n## MEMORY\n{bus.memory_ctx[:FREE_TIER_CONFIG['max_memory_chars']]}"
        
        if bus.kb_ctx:
            system += f"\n\n## KNOWLEDGE\n{bus.kb_ctx[:FREE_TIER_CONFIG['max_kb_chars']]}"
        
        # Build properly typed messages
        messages: List = []
        messages.append(build_typed_message("system", system))
        
        history = get_conversation_history(limit=FREE_TIER_CONFIG["max_history_messages"])
        for role, content, _ in history:
            if role in ["user", "assistant"]:
                messages.append(build_typed_message(role, content[:200]))
        
        messages.append(build_typed_message("user", bus.query))
        
        intent = bus.intent
        model = GROQ_MODEL_FALLBACK if intent == "simple" else GROQ_MODEL_PRIMARY
        max_tokens = 150 if intent == "simple" else 400
        
        def do_chat():
            return client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.35,
            )
        
        response = run_with_timeout(do_chat, timeout=10)
        bus.reply = (response.choices[0].message.content or "").strip()[:500]
        
    except TimeoutError:
        bus.reply = "I'm taking too long to respond. Please try a simpler question."
    except Exception as e:
        print(f"[CHAT] {e}")
        bus.reply = "ORA encountered an error. Please try again."

# ── Notifier Agent (Disabled for free tier) ──────────────────────────────────
def _run_notifier_agent(bus: MessageBus) -> None:
    """Disabled on free tier to save resources"""
    pass

# ─────────────────────────────────────────────────────────────────────────────
# COORDINATOR
# ─────────────────────────────────────────────────────────────────────────────

_AGENT_FN: Dict[str, Any] = {
    "memory": _run_memory_agent,
    "knowledge": _run_knowledge_agent,
    "research": _run_research_agent,
    "content": _run_content_agent,
    "code": _run_code_agent,
    "task": _run_task_agent,
    "goal": _run_goal_agent,
    "chat": _run_chat_agent,
    "notify": _run_notifier_agent,
}

class Coordinator:
    """Free tier optimized coordinator"""
    
    @staticmethod
    def run(query: str, save_history: bool = True) -> Dict:
        intent = classify_intent(query)
        pipeline = build_pipeline(intent)
        bus = MessageBus(query=query, intent=intent)
        
        for agent_name in pipeline:
            fn = _AGENT_FN.get(agent_name)
            if fn is None:
                continue
            
            try:
                with agent_timeout(agent_name):
                    fn(bus)
            except TimeoutError as e:
                print(f"[COORDINATOR] {e}")
                bus.add_context(agent_name, f"Agent timed out")
                if not bus.reply:
                    bus.reply = f"The {agent_name} agent timed out. Please simplify your request."
            except Exception as e:
                print(f"[COORDINATOR] {agent_name} error: {e}")
                if not bus.reply:
                    bus.reply = f"An error occurred in {agent_name}. Please try again."
        
        # Reduced background operations for free tier
        if save_history and bus.reply and FREE_TIER_CONFIG["enable_background_learning"]:
            try:
                from database import save_conversation
                save_conversation("user", query[:200])
                save_conversation("assistant", bus.reply[:200])
            except Exception:
                pass
        
        return {
            "reply": bus.reply or "No response generated.",
            "intent": intent,
            "pipeline": pipeline,
            "query_type": classify(query),
        }

# Module singleton
coordinator = Coordinator()

def run(query: str) -> Dict:
    """Convenience wrapper"""
    return Coordinator.run(query)