"""
ORA Brain — Multi-Agent Coordinator  (brain/router.py)
"""

from __future__ import annotations
import re, json, time, threading, traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_CFG = {"agent_timeout":12,"max_ctx_chars":900,"max_mem_chars":500,"max_kb_chars":500,"max_history":4,"cache_ttl":300}

class _TTLCache:
    def __init__(self,ttl=300): self._d={}; self._ttl=ttl
    def get(self,k):
        if k in self._d:
            v,ts=self._d[k]
            if time.time()-ts<self._ttl: return v
            del self._d[k]
        return None
    def set(self,k,v): self._d[k]=(v,time.time())

_icache=_TTLCache(300); _pcache=_TTLCache(300)

class AgentTimeoutError(Exception): pass

def _run_with_timeout(fn,*args,timeout=12,**kw):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut=ex.submit(fn,*args,**kw)
        try: return fut.result(timeout=timeout)
        except FutureTimeoutError: raise AgentTimeoutError(f"Timed out after {timeout}s")

_INTENT_PATTERNS=[
    ("research_then_content",re.compile(r"\b(research.{1,40}(and|then).{1,20}(write|draft|create|post)|find.{1,30}(and|then).{1,20}(write|draft))\b",re.I)),
    ("briefing",re.compile(r"\b(briefing|brief me|full brief|status update|what'?s? my status|catch me up|morning brief|evening brief|what'?s? going on)\b",re.I)),
    ("code",re.compile(r"\b(scan (repo|repos|code|branch)|failing (ci|test|check|build)|stale pr|dead branch|code (review|quality|issue|agent)|open (github )?issue|repo health)\b",re.I)),
    ("research",re.compile(r"\b(research|deep.?dive|investigate|look up|find out about|latest on|news about|search for|web search)\b",re.I)),
    ("content",re.compile(r"\b(write|draft|create|generate|compose|produce)\b.{0,40}\b(post|article|blog|email|tweet|thread|linkedin|caption|newsletter|script|copy|content)\b",re.I)),
    ("memory_write",re.compile(r"\b(remember|note that|save that|store that|my (name|preference|goal|email|role|company|style) is|i (prefer|like|hate|use|work at|am|live in))\b",re.I)),
    ("memory_read",re.compile(r"\b(what do you (know|remember) about me|my (profile|preferences|facts)|what have (i|you) (told|learned)|recall)\b",re.I)),
    ("knowledge",re.compile(r"\b(summarize|summary|according to|from (the|my) (doc|file|pdf|notes)|what does .{0,30} say|search (my )?knowledge|uploaded)\b",re.I)),
    ("task",re.compile(r"\b(add task|create task|new task|remind me to|mark .{0,20} (done|complete|finished)|my (tasks|todos)|what(\'s| is) (pending|due|overdue))\b",re.I)),
    ("goal",re.compile(r"\b(goal|objective|aim|target|milestone|how am i doing|check.?in|track(ing)?)\b",re.I)),
    ("calendar",re.compile(r"\b(calendar|meetings?|schedule|agenda|what'?s? on today|any events|upcoming events)\b",re.I)),
    ("weather",re.compile(r"\b(weather|raining|temperature|forecast|how'?s? the weather|is it hot)\b",re.I)),
    ("spend",re.compile(r"\b(how much|spent|spend|mpesa|m-pesa|transactions|balance|money today)\b",re.I)),
    ("complex",re.compile(r"\b(plan|strategy|analyze|compare|explain|why|how should|what would|recommend|advice|steps|roadmap|breakdown)\b",re.I)),
]

def classify_intent(query):
    k=query.lower().strip(); cached=_icache.get(k)
    if cached: return cached
    for intent,pat in _INTENT_PATTERNS:
        if pat.search(query): _icache.set(k,intent); return intent
    r="simple" if len(query.split())<=5 else "complex"; _icache.set(k,r); return r

def classify(query):
    i=classify_intent(query)
    if i in {"research","research_then_content","content","code","goal","complex","briefing"}: return "complex"
    if i=="knowledge": return "document"
    return "simple"

def model_for(qt):
    if qt=="simple": return "llama-3.1-8b-instant",160
    if qt=="document": return "llama-3.1-8b-instant",320
    return "llama-3.3-70b-versatile",520

def build_pipeline(intent):
    cached=_pcache.get(intent)
    if cached: return cached
    M={"research_then_content":["memory","research","content","notify"],"research":["memory","research","notify"],"content":["memory","knowledge","content"],"code":["code","notify"],"memory_write":["memory"],"memory_read":["memory","chat"],"knowledge":["knowledge","chat"],"task":["intent"],"goal":["intent"],"calendar":["intent"],"weather":["intent"],"spend":["intent"],"briefing":["briefing"],"complex":["memory","knowledge","chat"],"simple":["chat"]}
    r=M.get(intent,["chat"]); _pcache.set(intent,r); return r

class MessageBus:
    __slots__=("_lock","query","intent","started_at","context","reply","chain_log","memory_ctx","kb_ctx","research_result","content_draft","code_result","task_result","goal_result","memory_result")
    def __init__(self,query,intent):
        self._lock=threading.Lock(); self.query=query; self.intent=intent; self.started_at=datetime.now().isoformat()
        self.context=[]; self.reply=""; self.chain_log=[]; self.memory_ctx=""; self.kb_ctx=""
        self.research_result=None; self.content_draft=None; self.code_result=None
        self.task_result=None; self.goal_result=None; self.memory_result=None
    def post(self,agent,key,value,ms=0):
        with self._lock:
            setattr(self,key,value)
            if len(self.chain_log)<12: self.chain_log.append({"agent":agent,"key":key,"duration_ms":ms,"ts":datetime.now().isoformat()})
    def add_context(self,agent,summary):
        with self._lock:
            self.context.append({"agent":agent,"summary":summary[:900]})
            if len(self.context)>6: self.context.pop(0)
    def full_context(self):
        return "\n\n".join(f"[{c['agent']}]\n{c['summary'][:300]}" for c in self.context[-4:])

def _ms(): return int(time.time()*1000)

def _run_intent_agent(bus):
    t0=_ms()
    try:
        from Intent_parser import parse_intent,execute_intent
        io=parse_intent(bus.query)
        if io:
            r=execute_intent(io)
            if r: bus.reply=r; bus.post("IntentAgent","task_result",{"type":io["type"],"reply":r},_ms()-t0); return
    except Exception as e: print(f"[INTENT_AGENT] {e}")
    _run_chat_agent(bus)

def _run_memory_agent(bus):
    t0=_ms(); parts=[]
    try:
        from intelligence.learning_engine import get_facts_as_context,extract_explicit_facts
        f=get_facts_as_context(limit=15)
        if f: parts.append(f[:500])
        if bus.intent=="memory_write":
            extract_explicit_facts(bus.query); bus.reply="Got it — I've remembered that."
            bus.memory_ctx="\n\n".join(parts); bus.add_context("MemoryAgent","Stored new fact.")
            bus.post("MemoryAgent","memory_result",{"action":"stored","from":bus.query},_ms()-t0); return
    except Exception as e: print(f"[MEMORY_AGENT] facts: {e}")
    try:
        from memory.profile import get_all_profile
        p=get_all_profile()
        if p: parts.append("Profile:\n"+"\n".join(f"{k}: {v}" for k,v in list(p.items())[:8]))
    except Exception as e: print(f"[MEMORY_AGENT] profile: {e}")
    try:
        from memory.preferences import get_preferences
        pr=get_preferences()
        if pr: parts.append("Preferences:\n"+"\n".join(f"{r[0]}/{r[1]}: {r[2]}" for r in pr[:6]))
    except Exception as e: print(f"[MEMORY_AGENT] prefs: {e}")
    try:
        from memory.events import get_important_events
        ev=get_important_events(min_importance=7,limit=4)
        if ev: parts.append("Important events:\n"+"\n".join(f"- {e[1]}" for e in ev))
    except Exception as e: print(f"[MEMORY_AGENT] events: {e}")
    bus.memory_ctx="\n\n".join(parts)[:500]; bus.add_context("MemoryAgent",bus.memory_ctx[:300] or "No memory context.")
    bus.chain_log.append({"agent":"MemoryAgent","key":"memory_ctx","duration_ms":_ms()-t0,"ts":datetime.now().isoformat()})

def _run_knowledge_agent(bus):
    t0=_ms()
    try:
        from knowledge.pipeline import search_and_format
        kb=search_and_format(bus.query,n_results=3) or ""
        bus.kb_ctx=kb[:500]
        if bus.kb_ctx: bus.add_context("KnowledgeAgent",bus.kb_ctx[:300])
    except Exception as e: print(f"[KNOWLEDGE_AGENT] {e}")
    bus.chain_log.append({"agent":"KnowledgeAgent","key":"kb_ctx","duration_ms":_ms()-t0,"ts":datetime.now().isoformat()})

def _run_research_agent(bus):
    t0=_ms()
    try:
        from research_agent import deep_research
        result=_run_with_timeout(deep_research,bus.query,timeout=10)
        synthesis=result.get("content") or result.get("result","")
        bus.post("ResearchAgent","research_result",result,_ms()-t0)
        if synthesis: bus.add_context("ResearchAgent",synthesis[:900])
        if bus.intent=="research": bus.reply=synthesis[:600] or "Research complete."
    except AgentTimeoutError: bus.reply="Research timed out."; bus.add_context("ResearchAgent","Timed out.")
    except Exception as e: print(f"[RESEARCH_AGENT] {e}"); bus.add_context("ResearchAgent",f"Failed: {str(e)[:100]}")

def _detect_content_type(q):
    ql=q.lower()
    for kw,ct in [("linkedin","linkedin"),("twitter","twitter"),("tweet","twitter"),("thread","twitter"),("instagram","instagram"),("email","email"),("blog","blog"),("newsletter","newsletter"),("script","script"),("caption","caption")]:
        if kw in ql: return ct
    return "post"

def _detect_tone(q):
    ql=q.lower()
    if any(w in ql for w in ("professional","formal","business")): return "professional"
    if any(w in ql for w in ("casual","friendly","conversational")): return "casual"
    if any(w in ql for w in ("inspiring","motivational")): return "inspirational"
    if any(w in ql for w in ("technical","developer","engineering")): return "technical"
    if any(w in ql for w in ("funny","humor","witty")): return "humorous"
    return "professional"

def _run_content_agent(bus):
    t0=_ms()
    try:
        from agents.content_agent import create_draft
        extra=""
        if bus.research_result: extra=(bus.research_result.get("content") or bus.research_result.get("result",""))[:800]
        elif bus.kb_ctx: extra=bus.kb_ctx[:500]
        draft=create_draft(topic=bus.query,content_type=_detect_content_type(bus.query),tone=_detect_tone(bus.query),length="medium",extra_context=extra)
        draft_text=draft.get("draft") or draft.get("draft_text","")
        bus.post("ContentAgent","content_draft",draft,_ms()-t0)
        bus.reply=draft_text
        bus.add_context("ContentAgent",f"Draft: {draft_text[:150]}")
    except Exception as e: print(f"[CONTENT_AGENT] {e}"); traceback.print_exc()

def _build_code_summary(result):
    if "answer" in result: return str(result["answer"])[:500]
    if "repos" in result: return f"Scanned {result.get('scanned',0)} repos:\n"+"\n".join(f"{r['repo']}: {r['health']}/100" for r in result.get("repos",[])[:4])
    if "health" in result: return f"{result.get('repo')}: health {result.get('health')}/100. {result.get('summary','')[:200]}"
    return str(result)[:300]

def _run_code_agent(bus):
    t0=_ms()
    try:
        from agents.code_agent import scan_all_repos,scan_repo,ask_code_agent
        ql=bus.query.lower()
        def _work():
            if re.search(r"\b(scan all|all repos)\b",ql): return scan_all_repos()
            m=re.search(r"\b(scan|check|review)\s+([a-zA-Z0-9_\-\.]+)\b",bus.query,re.I)
            if m: return scan_repo(m.group(2))
            return {"answer":ask_code_agent(bus.query)}
        result=_run_with_timeout(_work,timeout=10)
        summary=_build_code_summary(result)
        bus.post("CodeAgent","code_result",result,_ms()-t0); bus.reply=summary; bus.add_context("CodeAgent",summary[:400])
    except AgentTimeoutError: bus.reply="Code scan timed out."
    except Exception as e: print(f"[CODE_AGENT] {e}"); traceback.print_exc()

def _run_briefing_agent(bus):
    t0=_ms(); parts=["Here's your status:\n"]
    try:
        from database import get_tasks
        tasks=get_tasks("pending")
        if tasks:
            now=datetime.now(); overdue=[t for t in tasks if t[4] and _parse_dt(t[4])<now]; high=[t for t in tasks if t[2]=="high"]
            lines=[f"  {'🔴' if t[2]=='high' else '🟡'} [{t[0]}] {t[1][:55]}"+(" ⚠ OVERDUE" if t[4] and _parse_dt(t[4])<now else "") for t in tasks[:6]]
            parts.append(f"📋 **Tasks** — {len(tasks)} pending"+(f", {len(overdue)} overdue" if overdue else "")+(f", {len(high)} high priority" if high else "")+":\n"+"\n".join(lines))
        else: parts.append("📋 **Tasks** — All clear.")
    except Exception as e: print(f"[BRIEFING] tasks: {e}")
    try:
        from intelligence.goals_engine import get_goals
        goals=get_goals("active")
        if goals:
            avg=int(sum(g.get("progress",0) for g in goals)/len(goals))
            parts.append(f"🎯 **Goals** — {len(goals)} active, {avg}% avg:\n"+"\n".join(f"  • {g['goal'][:55]} — {g['progress']}%"+(f" (due {g['due_at'][:10]})" if g.get('due_at') else "") for g in goals[:4]))
    except Exception as e: print(f"[BRIEFING] goals: {e}")
    try:
        from connectors.calendar import get_events_today,format_events_for_context
        ev=get_events_today()
        parts.append("📅 **Calendar** — "+(format_events_for_context(ev)[:300] if ev else "Nothing today."))
    except: pass
    try:
        from connectors.google_auth import is_authorized
        from connectors.gmail import get_gmail_summary
        if is_authorized():
            g=get_gmail_summary()
            if g and g.get("unread_count",0)>0: parts.append(f"📧 **Email** — {g['unread_count']} unread")
    except: pass
    try:
        from mpesa_engine import get_today_spend,get_average_daily_spend
        def _f(v):
            try: return float(v) if v is not None else 0.0
            except: return 0.0
        today=_f(get_today_spend()); avg=_f(get_average_daily_spend())
        if today>0: parts.append(f"💳 **Spend** — KES {today:,.0f} today ({'↑ above avg' if avg and today>avg*1.3 else '≈ normal'})")
    except: pass
    try:
        from connectors.weather import get_weather_summary
        w=get_weather_summary()
        if w: parts.append(f"🌤 **Weather** — {w}")
    except: pass
    try:
        from agents.code_agent import get_code_stats
        s=get_code_stats()
        if s.get("total_runs",0)>0: parts.append(f"⌥ **Code** — {s.get('open',0)} open findings, avg health {s.get('avg_health',0)}/100"+(f", ⚠ {s['critical']} critical" if s.get('critical') else ""))
    except: pass
    bus.reply="\n\n".join(parts); bus.post("BriefingAgent","task_result",{"briefing":bus.reply},_ms()-t0)

def _run_chat_agent(bus):
    if bus.reply: return
    t0=_ms()
    try:
        from config import GROQ_API_KEY,GROQ_MODEL_PRIMARY,GROQ_MODEL_FALLBACK
        from groq import Groq
        from context import build_system_prompt
        from database import get_conversation_history
        client=Groq(api_key=GROQ_API_KEY)
        system=build_system_prompt(query=bus.query)
        ctx=bus.full_context()
        if ctx: system+=f"\n\n## AGENT CONTEXT\n{ctx[:900]}"
        if bus.memory_ctx: system+=f"\n\n## MEMORY\n{bus.memory_ctx[:500]}"
        if bus.kb_ctx: system+=f"\n\n## KNOWLEDGE BASE\n{bus.kb_ctx[:500]}"
        messages=[{"role":"system","content":system}]
        for role,content,_ in get_conversation_history(limit=4):
            if role in ("user","assistant"): messages.append({"role":role,"content":content[:250]})
        messages.append({"role":"user","content":bus.query})
        model=GROQ_MODEL_FALLBACK if bus.intent=="simple" else GROQ_MODEL_PRIMARY
        max_tok=160 if bus.intent=="simple" else 520
        def _call():
            try: return client.chat.completions.create(model=model,messages=messages,max_tokens=max_tok,temperature=0.35)
            except: return client.chat.completions.create(model=GROQ_MODEL_FALLBACK,messages=messages,max_tokens=220,temperature=0.35)
        resp=_run_with_timeout(_call,timeout=10)
        bus.reply=(resp.choices[0].message.content or "").strip()
        bus.chain_log.append({"agent":"ChatAgent","key":"reply","duration_ms":_ms()-t0,"ts":datetime.now().isoformat()})
    except AgentTimeoutError: bus.reply="Taking too long — try a simpler question."
    except Exception as e: print(f"[CHAT_AGENT] {e}"); traceback.print_exc(); bus.reply="ORA error. Please try again."

def _run_notifier_agent(bus):
    if bus.intent not in {"research","research_then_content","code"}: return
    t0=_ms()
    try:
        from intelligence.notifier import dual_notify
        if bus.intent=="code" and bus.code_result: title,body="ORA Code Agent",_build_code_summary(bus.code_result)[:200]
        elif bus.research_result:
            title="ORA Research"; body=f"Research complete: {bus.research_result.get('title',bus.query[:60])}"
            if bus.content_draft: body+=f" → Draft created ({_detect_content_type(bus.query)})"
        else: title,body="ORA",bus.reply[:200]
        if body: dual_notify(title=title,body=body); bus.chain_log.append({"agent":"NotifierAgent","key":"notified","duration_ms":_ms()-t0,"ts":datetime.now().isoformat()})
    except Exception as e: print(f"[NOTIFIER_AGENT] {e}")

_AGENT_FN={"intent":_run_intent_agent,"memory":_run_memory_agent,"knowledge":_run_knowledge_agent,"research":_run_research_agent,"content":_run_content_agent,"code":_run_code_agent,"briefing":_run_briefing_agent,"chat":_run_chat_agent,"notify":_run_notifier_agent}

class Coordinator:
    @staticmethod
    def run(query,save_history=True):
        intent=classify_intent(query); pipeline=build_pipeline(intent); bus=MessageBus(query=query,intent=intent)
        for name in pipeline:
            fn=_AGENT_FN.get(name)
            if fn is None: print(f"[COORDINATOR] Unknown agent '{name}'"); continue
            try: fn(bus)
            except AgentTimeoutError as e: print(f"[COORDINATOR] Timeout {name}: {e}"); bus.add_context(name,"Timed out"); bus.reply=bus.reply or f"{name} timed out."
            except Exception as e: print(f"[COORDINATOR] {name} error: {e}"); traceback.print_exc()
        if save_history and bus.reply:
            try:
                from database import save_conversation
                save_conversation("user",query[:300]); save_conversation("assistant",bus.reply[:300])
            except: pass
            try:
                from intelligence.learning_engine import extract_facts_from_exchange,extract_explicit_facts
                extract_explicit_facts(query)
                threading.Thread(target=extract_facts_from_exchange,args=(query,bus.reply),daemon=True).start()
            except: pass
        return {"reply":bus.reply or "No response generated.","query_type":classify(query),"intent":intent,"pipeline":pipeline,"chain_log":bus.chain_log,"research":bus.research_result,"draft":bus.content_draft,"code":bus.code_result}

coordinator=Coordinator()
def run(query): return Coordinator.run(query)

def _parse_dt(s):
    try: return datetime.fromisoformat(s)
    except: return datetime.max
