import { useState, useEffect, useRef, useCallback } from "react"
import { sendMessage, getConversations } from "../api"
import BASE from "../api"

const QUICK = [
  { label: "📋 Tasks", msg: "show my pending tasks" },
  { label: "🎯 Goals", msg: "what are my active goals" },
  { label: "💳 Spend", msg: "how much have I spent today" },
  { label: "📊 Briefing", msg: "give me a full briefing" },
  { label: "⚡ Alerts", msg: "any active alerts" },
  { label: "📅 Calendar", msg: "what's on my calendar today" },
  { label: "🔮 Predict", msg: "what should I focus on" },
]

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [backendState, setBackendState] = useState("connecting")

  const bottomRef = useRef(null)
  const abortRef = useRef(null)

  /* ───────── HEALTH ───────── */
  useEffect(() => {
    fetch(`${BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendState(d?.status === "ok" ? "online" : "cold"))
      .catch(() => setBackendState("cold"))
  }, [])

  /* ───────── HISTORY ───────── */
  useEffect(() => {
    getConversations(40)
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  /* ───────── AUTO SCROLL ───────── */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  /* ───────── SEND ───────── */
  const send = useCallback(async (textOverride) => {
    const text = (textOverride ?? input).trim()
    if (!text || loading) return

    setInput("")
    setLoading(true)

    abortRef.current?.abort?.()
    abortRef.current = new AbortController()

    pushUser(text)

    try {
      const res = await sendMessage(text)

      pushAssistant(res)
      setBackendState("online")

    } catch {
      pushError()
      setBackendState("cold")
    }

    setLoading(false)
  }, [input, loading])

  /* ───────── MESSAGE HELPERS ───────── */

  const pushUser = (text) => {
    setMessages(prev => [...prev, {
      role: "user",
      content: text,
      timestamp: now()
    }])
  }

  const pushAssistant = (res) => {
    setMessages(prev => [...prev, {
      role: "assistant",
      content: res?.reply || "[EMPTY RESPONSE]",
      model: res?.model,
      cached: res?.cached,
      intent: res?.intent,
      timestamp: now(),
      type: "response"
    }])
  }

  const pushError = () => {
    setMessages(prev => [...prev, {
      role: "assistant",
      content: "⚠ ORA temporarily unavailable. Try again.",
      isError: true,
      timestamp: now(),
      type: "error"
    }])
  }

  /* ───────── RENDER ───────── */

  return (
    <div className="chat-page">

      {/* HEADER */}
      <div className="chat-header">
        <div className="page-title">NEURAL LINK</div>

        <div className="page-sub">
          Direct channel to ORA
          <StatusDot state={backendState} />
        </div>
      </div>

      {/* QUICK ACTIONS */}
      <div className="pill-row">
        {QUICK.map(q => (
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
          <Message key={i} msg={m} />
        ))}

        {loading && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* INPUT */}
      <ChatInput
        value={input}
        setValue={setInput}
        onSend={() => send()}
        loading={loading}
      />

    </div>
  )
}

/* ───────── COMPONENTS ───────── */

function Message({ msg }) {
  return (
    <div className={`msg ${msg.role} fade-in`}>

      <div className="msg-avatar">
        {msg.role === "user" ? "EL" : "◎"}
      </div>

      <div className="msg-bubble">

        {msg.role === "assistant" && (
          <div className="msg-label">
            {label(msg)}
          </div>
        )}

        <p>{msg.content}</p>

        <div className="event-time">
          {formatTime(msg.timestamp)}
        </div>

      </div>
    </div>
  )
}

function ChatInput({ value, setValue, onSend, loading }) {
  return (
    <div className="chat-input-area">
      <div className="chat-input-row">

        <textarea
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
          placeholder="TRANSMIT MESSAGE"
        />

        <button
          className="btn-send"
          onClick={onSend}
          disabled={loading || !value.trim()}
        >
          {loading ? "···" : "SEND ▶"}
        </button>

      </div>
    </div>
  )
}

function StatusDot({ state }) {
  const color =
    state === "online"
      ? "var(--green)"
      : state === "cold"
      ? "var(--amber)"
      : "var(--text3)"

  return (
    <span style={{ marginLeft: 10, color }}>
      ● {state.toUpperCase()}
    </span>
  )
}

/* ───────── HELPERS ───────── */

function now() {
  return new Date().toISOString()
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("en-KE", {
      hour12: false,
    })
  } catch {
    return ""
  }
}

function label(m) {
  if (m.isError) return "ORA // ERROR"
  if (m.cached) return "ORA // CACHE"
  if (m.intent) return `ORA // ${m.intent.toUpperCase()}`
  return "ORA // RESPONSE"
}

function IdleState() {
  return (
    <div className="empty" style={{ marginTop: "5rem" }}>
      <div className="glow-green" style={{ fontSize: "2rem" }}>◎</div>
      <div>ORA STANDING BY</div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="msg ora fade-in">
      <div className="msg-avatar">◎</div>
      <div className="msg-bubble">
        <div className="msg-label">ORA // PROCESSING</div>
        <div className="thinking-dots">
          <span /><span /><span />
        </div>
      </div>
    </div>
  )
}