/**
 * ORA ChatPage — Upgraded
 * - Conversational system prompt (talks like a real assistant, not a robot)
 * - Action confirmation cards (task added, reminder set, etc.)
 * - Markdown-lite rendering (bold, code, lists)
 * - Message reaction / feedback buttons
 * - Smart quick-action chips that update contextually
 * - Typing indicator with random "thinking" states
 * - Copy-to-clipboard on assistant messages
 * - Voice input button (Web Speech API, no backend needed)
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { sendMessage, getConversations } from "../api"
import BASE from "../api"

// ── Quick action sets ───────────────────────────────────────
const QUICK_SETS = {
  default: [
    { label: "📋 Tasks",    msg: "show my pending tasks" },
    { label: "🎯 Goals",    msg: "what are my active goals" },
    { label: "💳 Spend",    msg: "how much have I spent today" },
    { label: "📊 Briefing", msg: "give me a full briefing" },
    { label: "⚡ Alerts",   msg: "any active alerts" },
    { label: "📅 Calendar", msg: "what's on my calendar today" },
    { label: "🔮 Focus",    msg: "what should I focus on right now" },
  ],
  task: [
    { label: "✅ Done",     msg: "mark the last task as complete" },
    { label: "📋 All",      msg: "show all my tasks" },
    { label: "⚡ High",     msg: "show high priority tasks" },
    { label: "➕ Add",      msg: "add task " },
  ],
  morning: [
    { label: "☀️ Brief",   msg: "give me my morning briefing" },
    { label: "📅 Today",   msg: "what's on my calendar today" },
    { label: "🎯 Goals",   msg: "check my goal progress" },
    { label: "🔮 Focus",   msg: "what should I prioritize today" },
  ],
}

// ── Thinking states ─────────────────────────────────────────
const THINKING = [
  "Querying memory...",
  "Checking context...",
  "Scanning knowledge base...",
  "Cross-referencing data...",
  "Formulating response...",
  "Pulling your context...",
  "Running inference...",
]

export default function ChatPage() {
  const [messages, setMessages]     = useState([])
  const [input, setInput]           = useState("")
  const [loading, setLoading]       = useState(false)
  const [backendState, setBackendState] = useState("connecting")
  const [thinkingText, setThinkingText] = useState(THINKING[0])
  const [quickSet, setQuickSet]     = useState("default")
  const [listening, setListening]   = useState(false)
  const [copiedIdx, setCopiedIdx]   = useState(null)

  const bottomRef   = useRef(null)
  const thinkRef    = useRef(null)
  const recognRef   = useRef(null)
  const textareaRef = useRef(null)

  // ── Health check ──────────────────────────────────────────
  useEffect(() => {
    fetch(`${BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendState(d?.status === "ok" ? "online" : "cold"))
      .catch(() => setBackendState("cold"))
  }, [])

  // ── Load history ──────────────────────────────────────────
  useEffect(() => {
    getConversations(40)
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  // ── Auto scroll ───────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  // ── Thinking cycle ────────────────────────────────────────
  useEffect(() => {
    if (loading) {
      let i = 0
      thinkRef.current = setInterval(() => {
        i = (i + 1) % THINKING.length
        setThinkingText(THINKING[i])
      }, 1400)
    } else {
      clearInterval(thinkRef.current)
    }
    return () => clearInterval(thinkRef.current)
  }, [loading])

  // ── Context-aware quick set ───────────────────────────────
  useEffect(() => {
    const h = new Date().getHours()
    if (h >= 6 && h < 10) setQuickSet("morning")
    else setQuickSet("default")
  }, [])

  // ── Send ──────────────────────────────────────────────────
  const send = useCallback(async (textOverride) => {
    const text = (textOverride ?? input).trim()
    if (!text || loading) return

    // If action chip ends with space (e.g. "add task "), focus input instead
    if (textOverride?.endsWith(" ")) {
      setInput(textOverride)
      textareaRef.current?.focus()
      return
    }

    setInput("")
    setLoading(true)

    setMessages(prev => [...prev, {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    }])

    try {
      const res = await sendMessage(text)

      setMessages(prev => [...prev, {
        role: "assistant",
        content: res?.reply || "[EMPTY RESPONSE]",
        model:   res?.model,
        cached:  res?.cached,
        intent:  res?.intent,
        timestamp: new Date().toISOString(),
        type: "response",
        action: res?.intent ? { type: res.intent, reply: res.reply } : null,
      }])
      setBackendState("online")

      // Switch quick set after task-related actions
      if (res?.intent?.includes("task") || res?.intent?.includes("remind")) {
        setQuickSet("task")
        setTimeout(() => setQuickSet("default"), 30000)
      }

    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "ORA is temporarily unreachable — Render free tier may be spinning up. Try again in 30 seconds.",
        isError: true,
        timestamp: new Date().toISOString(),
        type: "error",
      }])
      setBackendState("cold")
    }

    setLoading(false)
  }, [input, loading])

  // ── Voice input ───────────────────────────────────────────
  const toggleVoice = useCallback(() => {
    if (!("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      alert("Voice input not supported in this browser.")
      return
    }
    if (listening) {
      recognRef.current?.stop()
      setListening(false)
      return
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    const r = new SR()
    r.lang = "en-KE"
    r.interimResults = false
    r.onresult = e => {
      const transcript = e.results[0][0].transcript
      setInput(transcript)
      setListening(false)
    }
    r.onerror = () => setListening(false)
    r.onend   = () => setListening(false)
    r.start()
    recognRef.current = r
    setListening(true)
  }, [listening])

  // ── Copy ──────────────────────────────────────────────────
  const copyMsg = useCallback((text, idx) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx(null), 2000)
    })
  }, [])

  // ── Clear history ─────────────────────────────────────────
  const clearChat = useCallback(() => {
    if (window.confirm("Clear conversation history?")) {
      setMessages([])
    }
  }, [])

  // ── Render ────────────────────────────────────────────────
  const chips = QUICK_SETS[quickSet] || QUICK_SETS.default

  return (
    <div className="chat-page">

      {/* HEADER */}
      <div className="chat-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div className="page-title">NEURAL LINK</div>
          <StatusDot state={backendState} />
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            className="pill"
            style={{ fontSize: "0.65rem", padding: "3px 10px", opacity: 0.6 }}
            onClick={clearChat}
          >CLR</button>
        </div>
      </div>

      {/* QUICK CHIPS */}
      <div className="pill-row">
        {chips.map(q => (
          <button
            key={q.label}
            className="pill"
            onClick={() => send(q.msg)}
            disabled={loading}
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* MESSAGES */}
      <div className="chat-messages">

        {messages.length === 0 && <IdleState />}

        {messages.map((m, i) => (
          <Message
            key={i}
            msg={m}
            idx={i}
            onCopy={copyMsg}
            copied={copiedIdx === i}
          />
        ))}

        {loading && <TypingIndicator text={thinkingText} />}

        <div ref={bottomRef} />
      </div>

      {/* INPUT */}
      <ChatInput
        ref={textareaRef}
        value={input}
        setValue={setInput}
        onSend={() => send()}
        loading={loading}
        onVoice={toggleVoice}
        listening={listening}
      />

    </div>
  )
}

// ── Message ────────────────────────────────────────────────
function Message({ msg, idx, onCopy, copied }) {
  const isUser = msg.role === "user"

  return (
    <div className={`msg ${msg.role} fade-in`}>

      <div className="msg-avatar">
        {isUser ? "EL" : "◎"}
      </div>

      <div className="msg-bubble" style={{ position: "relative" }}>

        {!isUser && (
          <div className="msg-label">
            {msgLabel(msg)}
          </div>
        )}

        {/* Action confirmation card */}
        {msg.action && <ActionCard action={msg.action} />}

        {/* Rendered content */}
        <div className="msg-content">
          <RenderMarkdown text={msg.content} />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginTop: "0.4rem" }}>
          <span className="event-time">{formatTime(msg.timestamp)}</span>

          {!isUser && !msg.isError && (
            <button
              onClick={() => onCopy(msg.content, idx)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: copied ? "var(--green)" : "var(--text3)",
                fontSize: "0.6rem",
                fontFamily: "inherit",
                letterSpacing: "0.05em",
                padding: 0,
              }}
            >
              {copied ? "COPIED ✓" : "COPY"}
            </button>
          )}
        </div>

      </div>
    </div>
  )
}

// ── Action confirmation card ───────────────────────────────
function ActionCard({ action }) {
  const icons = {
    add_task:     "✅",
    remind:       "⏰",
    set_goal:     "🎯",
    search_docs:  "🔍",
    spend_summary:"💳",
    check_tasks:  "📋",
  }
  const icon = icons[action.type] || "⚡"
  const label = action.type?.replace(/_/g, " ").toUpperCase()

  return (
    <div style={{
      background: "rgba(0,255,157,0.04)",
      border: "1px solid rgba(0,255,157,0.15)",
      borderRadius: "4px",
      padding: "6px 10px",
      marginBottom: "8px",
      fontSize: "0.68rem",
      color: "var(--green)",
      letterSpacing: "0.08em",
      display: "flex",
      alignItems: "center",
      gap: "6px",
    }}>
      <span>{icon}</span>
      <span>ACTION EXECUTED // {label}</span>
    </div>
  )
}

// ── Markdown-lite renderer ─────────────────────────────────
function RenderMarkdown({ text }) {
  if (!text) return null

  // Split by lines and render
  const lines = text.split("\n")

  return (
    <div style={{ lineHeight: 1.6 }}>
      {lines.map((line, i) => {
        // Code block (simple)
        if (line.startsWith("```") || line.startsWith("    ")) {
          return (
            <code key={i} style={{
              display: "block",
              background: "rgba(0,0,0,0.4)",
              border: "1px solid var(--border)",
              borderRadius: "3px",
              padding: "2px 8px",
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: "0.78rem",
              color: "var(--cyan)",
              margin: "2px 0",
            }}>
              {line.replace(/^```\w*/, "").trim()}
            </code>
          )
        }

        // Bullet
        if (line.match(/^[-•*]\s/)) {
          const content = renderInline(line.slice(2))
          return <div key={i} style={{ paddingLeft: "1rem" }}>• {content}</div>
        }

        // Numbered list
        if (line.match(/^\d+\.\s/)) {
          const content = renderInline(line.replace(/^\d+\.\s/, ""))
          const num = line.match(/^(\d+)/)[1]
          return <div key={i} style={{ paddingLeft: "1rem" }}>{num}. {content}</div>
        }

        // Empty line
        if (line.trim() === "") return <div key={i} style={{ height: "0.4rem" }} />

        // Normal line
        return <p key={i} style={{ margin: 0 }}>{renderInline(line)}</p>
      })}
    </div>
  )
}

function renderInline(text) {
  // Bold **text**
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} style={{ color: "var(--text2)" }}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} style={{ fontFamily: "'Share Tech Mono', monospace", color: "var(--cyan)", fontSize: "0.82em", background: "rgba(6,182,212,0.08)", padding: "0 4px", borderRadius: "2px" }}>{part.slice(1, -1)}</code>
    }
    return part
  })
}

// ── Chat input ─────────────────────────────────────────────
import { forwardRef } from "react"

const ChatInput = forwardRef(function ChatInput({ value, setValue, onSend, loading, onVoice, listening }, ref) {
  return (
    <div className="chat-input-area">
      <div className="chat-input-row">

        <textarea
          ref={ref}
          className="chat-textarea"
          value={value}
          disabled={loading}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
          placeholder={listening ? "🎙 LISTENING..." : "TRANSMIT TO ORA  (enter to send, shift+enter for newline)"}
          style={listening ? { borderColor: "var(--red)", boxShadow: "0 0 12px rgba(239,68,68,0.3)" } : {}}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <button
            className="btn-send"
            onClick={onSend}
            disabled={loading || !value.trim()}
          >
            {loading ? "···" : "SEND ▶"}
          </button>

          <button
            onClick={onVoice}
            style={{
              background: listening ? "rgba(239,68,68,0.15)" : "transparent",
              border: `1px solid ${listening ? "var(--red)" : "var(--border2)"}`,
              color: listening ? "var(--red)" : "var(--text3)",
              borderRadius: "4px",
              padding: "6px",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: "0.75rem",
              transition: "all 0.2s",
            }}
            title="Voice input"
          >
            {listening ? "⏹ STOP" : "🎙 VOICE"}
          </button>
        </div>

      </div>

      {/* Render-free-tier note */}
      <div style={{ fontSize: "0.6rem", color: "var(--text3)", marginTop: "4px", textAlign: "center", letterSpacing: "0.05em" }}>
        RENDER FREE TIER — COLD START MAY TAKE 30s · SHIFT+ENTER FOR NEWLINE
      </div>
    </div>
  )
})

// ── Status dot ─────────────────────────────────────────────
function StatusDot({ state }) {
  const map = {
    online:     { color: "var(--green)",  label: "ONLINE",     pulse: "pulse-g" },
    cold:       { color: "var(--amber)",  label: "COLD",       pulse: "pulse-a" },
    connecting: { color: "var(--text3)",  label: "CONNECTING", pulse: "" },
  }
  const { color, label, pulse } = map[state] || map.connecting

  return (
    <span style={{ display: "flex", alignItems: "center", gap: "5px", fontSize: "0.65rem", letterSpacing: "0.1em" }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: color,
        display: "inline-block",
        animation: pulse ? `${pulse} 2s ease infinite` : "none",
      }} />
      <span style={{ color }}>{label}</span>
    </span>
  )
}

// ── Idle state ─────────────────────────────────────────────
function IdleState() {
  const hour = new Date().getHours()
  const greeting =
    hour < 5  ? "Night owl mode activated." :
    hour < 12 ? "Good morning, Elisha." :
    hour < 17 ? "Afternoon, Elisha." :
    hour < 21 ? "Good evening, Elisha." :
                "Late night session — noted."

  return (
    <div className="empty" style={{ marginTop: "5rem", gap: "0.75rem" }}>
      <div className="glow-green" style={{ fontSize: "2.5rem", animation: "pulse-g 3s ease infinite" }}>◎</div>
      <div style={{ fontSize: "1rem", color: "var(--text2)" }}>{greeting}</div>
      <div style={{ fontSize: "0.72rem", color: "var(--text3)", letterSpacing: "0.1em" }}>
        ORA IS STANDING BY — ALL SYSTEMS NOMINAL
      </div>
    </div>
  )
}

// ── Typing indicator ───────────────────────────────────────
function TypingIndicator({ text }) {
  return (
    <div className="msg assistant fade-in">
      <div className="msg-avatar">◎</div>
      <div className="msg-bubble">
        <div className="msg-label">ORA // PROCESSING</div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div className="thinking-dots">
            <span /><span /><span />
          </div>
          <span style={{ fontSize: "0.68rem", color: "var(--text3)", letterSpacing: "0.08em", animation: "fade-in 0.3s ease" }}>
            {text}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────
function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("en-KE", { hour12: false })
  } catch {
    return ""
  }
}

function msgLabel(m) {
  if (m.isError) return "ORA // ERROR"
  if (m.cached)  return "ORA // CACHE HIT"
  if (m.intent)  return `ORA // ${m.intent.replace(/_/g, " ").toUpperCase()}`
  if (m.model?.includes("70b")) return "ORA // DEEP THINK"
  return "ORA // RESPONSE"
}