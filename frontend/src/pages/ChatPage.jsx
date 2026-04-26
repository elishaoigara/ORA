import { useState, useEffect, useRef } from "react"
import { sendMessage, getConversations } from "../api"
import BASE from "../api"

const QUICK = [
  { label: "📋 Tasks",    msg: "show my pending tasks" },
  { label: "🎯 Goals",    msg: "what are my active goals" },
  { label: "💳 Spend",    msg: "how much have I spent today" },
  { label: "📊 Briefing", msg: "give me a full briefing" },
  { label: "⚡ Alerts",   msg: "any active alerts" },
  { label: "📅 Calendar", msg: "what's on my calendar today" },
  { label: "🔮 Predict",  msg: "what should I focus on" },
]

const MODEL_COLORS = {
  "llama-3.1-8b-instant":     "var(--text3)",
  "llama-3.3-70b-versatile":  "var(--green)",
  "deepseek-r1-distill-llama-70b": "var(--purple)",
  "mixtral-8x7b-32768":       "var(--cyan)",
}

export default function ChatPage() {
  const [messages,     setMessages]     = useState([])
  const [input,        setInput]        = useState("")
  const [loading,      setLoading]      = useState(false)
  const [backendState, setBackendState] = useState("connecting")

  const bottomRef = useRef(null)
  const abortRef  = useRef(null)
  const inputRef  = useRef(null)

  // Health check
  useEffect(() => {
    fetch(`${BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendState(d?.status === "ok" ? "online" : "cold"))
      .catch(() => setBackendState("cold"))
  }, [])

  // Load history
  useEffect(() => {
    getConversations(40)
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  const send = async (textOverride) => {
    const text = (textOverride ?? input).trim()
    if (!text || loading) return

    setInput("")
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    setMessages(prev => [...prev, { role: "user", content: text, timestamp: new Date().toISOString() }])
    setLoading(true)

    try {
      const res = await sendMessage(text)
      setMessages(prev => [...prev, {
        role:      "assistant",
        content:   res?.reply || "[EMPTY RESPONSE]",
        model:     res?.model,
        cached:    res?.cached,
        intent:    res?.intent,
        timestamp: new Date().toISOString(),
      }])
      setBackendState("online")
    } catch {
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: "⚠ ORA temporarily unavailable. Try again.",
        isError: true,
        timestamp: new Date().toISOString(),
      }])
      setBackendState("cold")
    }

    setLoading(false)
  }

  return (
    <div className="chat-page">

      <div className="chat-header">
        <div className="page-title">// Neural Link</div>
        <div className="page-sub">
          Direct channel to ORA
          {backendState === "online" && <span style={{ marginLeft: 10, color: "var(--green)" }}>● LIVE</span>}
          {backendState === "cold"   && <span style={{ marginLeft: 10, color: "var(--amber)" }}>● WAKING</span>}
          {backendState === "connecting" && <span style={{ marginLeft: 10, color: "var(--text3)" }}>● CONNECTING</span>}
        </div>
      </div>

      {/* Quick pills */}
      <div className="pill-row" style={{ padding: ".5rem 1.25rem .25rem" }}>
        {QUICK.map(q => (
          <button key={q.label} className="pill" onClick={() => send(q.msg)} disabled={loading}>
            {q.label}
          </button>
        ))}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty" style={{ marginTop: "5rem" }}>
            <div style={{ fontSize: "2.5rem", color: "var(--green)", textShadow: "0 0 20px rgba(0,255,157,.4)" }}>◎</div>
            <div className="glow-green" style={{ letterSpacing: 4, fontFamily: "Orbitron, monospace" }}>ORA STANDING BY</div>
            <div style={{ color: "var(--text3)", fontSize: ".75rem", letterSpacing: 2 }}>Ask anything or tap a quick action</div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role === "user" ? "user" : "ora"} fade-in`}>
            <div className="msg-avatar">
              {m.role === "user" ? "EL" : "◎"}
            </div>
            <div className="msg-bubble">
              {m.role === "assistant" && (
                <div className="msg-label">
                  {m.isError  ? "ORA // ERROR" :
                   m.cached   ? "ORA // CACHE HIT" :
                   m.intent   ? `ORA // ${m.intent.toUpperCase()}` :
                   "ORA // RESPONSE"}
                  {m.model && (
                    <span style={{ marginLeft: 8, color: MODEL_COLORS[m.model] || "var(--text3)", fontSize: ".55rem" }}>
                      [{m.model?.split("-")[0]}]
                    </span>
                  )}
                </div>
              )}
              <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{m.content}</p>
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".55rem", color: "var(--text3)", marginTop: 5, textAlign: m.role === "user" ? "right" : "left" }}>
                {m.timestamp ? new Date(m.timestamp).toLocaleTimeString("en-KE", { hour12: false }) : ""}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg ora fade-in">
            <div className="msg-avatar">◎</div>
            <div className="msg-bubble">
              <div className="msg-label">ORA // PROCESSING</div>
              <div className="thinking-dots">
                <span /><span /><span />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={inputRef}
            className="chat-textarea"
            value={input}
            disabled={loading}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="TRANSMIT MESSAGE // Enter to send · Shift+Enter for new line"
            rows={1}
          />
          <button className="btn-send" onClick={() => send()} disabled={loading || !input.trim()}>
            {loading ? "···" : "SEND ▶"}
          </button>
        </div>
      </div>

    </div>
  )
}