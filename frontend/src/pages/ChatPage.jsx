import { useState, useEffect, useRef, useCallback } from "react"
import API from "../api"

const COLD_START_TIMEOUT_MS = 60_000
const PING_INTERVAL_MS      = 3_000

export default function ChatPage() {
  const [messages, setMessages]         = useState([])
  const [input, setInput]               = useState("")
  const [loading, setLoading]           = useState(false)
  const [theNumber, setTheNumber]       = useState(null)
  const [backendState, setBackendState] = useState("checking")

  const bottomRef   = useRef(null)
  const textareaRef = useRef(null)
  const abortRef    = useRef(null)
  const pingRef     = useRef(null)
  const pingStart   = useRef(null)

  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/ping`, { signal: AbortSignal.timeout(5000) })
      if (res.ok) {
        setBackendState("online")
        clearInterval(pingRef.current)
        return true
      }
    } catch (_) {}
    if (pingStart.current && Date.now() - pingStart.current > COLD_START_TIMEOUT_MS) {
      setBackendState("offline")
      clearInterval(pingRef.current)
    } else {
      setBackendState("cold_start")
    }
    return false
  }, [])

  useEffect(() => {
    pingStart.current = Date.now()
    checkBackend().then(online => {
      if (!online) pingRef.current = setInterval(checkBackend, PING_INTERVAL_MS)
    })
    return () => clearInterval(pingRef.current)
  }, [checkBackend])

  useEffect(() => {
    fetch(`${API}/api/conversations`)
      .then(r => r.ok ? r.json() : [])
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch(`${API}/api/tasks`)
      .then(r => r.ok ? r.json() : [])
      .then(tasks => {
        if (!Array.isArray(tasks) || !tasks.length) return
        const pri = { high: 3, medium: 2, low: 1 }
        const top = [...tasks].sort((a, b) => (pri[b.priority] || 0) - (pri[a.priority] || 0))[0]
        setTheNumber(top)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  const sendFeedback = async (msg, useful) => {
    if (!msg.chunk_ids?.length) return
    try {
      await fetch(`${API}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chunk_ids: msg.chunk_ids, query: msg.query || "", useful })
      })
      setMessages(prev => prev.map(m => m === msg ? { ...m, rated: useful ? "up" : "down" } : m))
    } catch (e) { console.error("Feedback error:", e) }
  }

  const send = async () => {
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput("")
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    setMessages(prev => [...prev, { role: "user", content: text }])
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: abortRef.current.signal,
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try { detail = (await res.json()).detail || detail } catch (_) {}
        throw new Error(detail)
      }
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data?.reply || "[EMPTY RESPONSE]",
        chunk_ids: data?.chunk_ids || [],
        query: text,
        rated: null,
        isError: data?.error === true
      }])
    } catch (err) {
      if (err.name !== "AbortError") {
        const isNetworkErr = err instanceof TypeError
        const hint = isNetworkErr
          ? `Cannot reach backend. Verify VITE_API_URL in Vercel. Current: ${API}`
          : err.message || "Unknown error"
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `⚠ ${hint}`,
          isError: true
        }])
      }
    }
    setLoading(false)
  }

  const onKey = e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send() }
  }

  const BackendBanner = () => {
    if (backendState === "online") return null
    const base = {
      margin: "0 1.5rem 1rem", padding: "0.6rem 1rem",
      borderRadius: 4, fontSize: "0.78rem",
      fontFamily: "Share Tech Mono, monospace",
    }
    if (backendState === "checking") return (
      <div style={{ ...base, background: "rgba(100,100,100,0.12)", border: "1px solid var(--border2)", color: "var(--text3)" }}>
        ◌ Connecting to ORA backend…
      </div>
    )
    if (backendState === "cold_start") return (
      <div style={{ ...base, background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.3)", color: "var(--amber)" }}>
        ⏳ ORA is waking up (Render cold start — ~30s). You can type while waiting.
      </div>
    )
    return (
      <div style={{ ...base, background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.3)", color: "var(--red)" }}>
        ✕ Backend unreachable. Verify VITE_API_URL in Vercel.{" "}
        Current: <code style={{ fontSize: "0.72rem" }}>{API}</code>
      </div>
    )
  }

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div className="page-title">// Neural Link</div>
        <div className="page-sub">
          Direct channel to ORA · Context-aware intelligence system
          {backendState === "online" && (
            <span style={{ marginLeft: 12, color: "var(--green)", fontSize: "0.6rem" }}>● LIVE</span>
          )}
        </div>
      </div>

      <BackendBanner />

      {theNumber && messages.length === 0 && (
        <div style={{
          margin: "0 1.5rem 1rem", padding: "0.75rem 1rem",
          background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.25)",
          borderLeft: "3px solid var(--amber)", borderRadius: 4,
        }}>
          <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.62rem", color: "var(--text3)", letterSpacing: 2, marginBottom: 4 }}>
            TODAY'S NUMBER
          </div>
          <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.9rem", color: "var(--amber)", textShadow: "0 0 10px rgba(245,158,11,0.4)" }}>
            {theNumber.title}
          </div>
          <div style={{ fontSize: "0.7rem", color: "var(--text3)", marginTop: 2 }}>
            Priority: {theNumber.priority?.toUpperCase()} · Focus here first
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty" style={{ marginTop: "4rem" }}>
            <div className="empty-icon">◎</div>
            <div className="glow" style={{ marginBottom: 8 }}>ORA STANDING BY</div>
            <div>Ask about tasks, files, system state, or anything else</div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role === "user" ? "user" : "ora"}`}>
            <div className="msg-avatar">{m.role === "user" ? "EL" : "◎"}</div>
            <div className="msg-bubble" style={{ flex: 1 }}>
              {m.role === "assistant" && (
                <div className="msg-label" style={m.isError ? { color: "var(--red)" } : {}}>
                  {m.isError ? "ORA // ERROR" : "ORA // RESPONSE"}
                </div>
              )}
              <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              {m.role === "assistant" && m.chunk_ids?.length > 0 && (
                <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
                  <span style={{ fontSize: "0.62rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>RATE:</span>
                  <button onClick={() => sendFeedback(m, true)} disabled={!!m.rated} style={{
                    background: "none", border: `1px solid ${m.rated === "up" ? "var(--green)" : "var(--border2)"}`,
                    color: m.rated === "up" ? "var(--green)" : "var(--text3)", cursor: m.rated ? "default" : "pointer",
                    padding: "2px 7px", fontSize: "0.7rem", borderRadius: 3,
                  }}>▲ USEFUL</button>
                  <button onClick={() => sendFeedback(m, false)} disabled={!!m.rated} style={{
                    background: "none", border: `1px solid ${m.rated === "down" ? "var(--red)" : "var(--border2)"}`,
                    color: m.rated === "down" ? "var(--red)" : "var(--text3)", cursor: m.rated ? "default" : "pointer",
                    padding: "2px 7px", fontSize: "0.7rem", borderRadius: 3,
                  }}>▼ NOT USEFUL</button>
                  {m.rated && <span style={{ fontSize: "0.62rem", color: "var(--text3)" }}>· logged</span>}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg ora">
            <div className="msg-avatar">◎</div>
            <div className="msg-bubble">
              <div className="msg-label">ORA // PROCESSING</div>
              <div className="thinking-dots"><span>▪</span><span>▪</span><span>▪</span></div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            disabled={loading}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder={
              backendState === "cold_start"
                ? "ORA warming up — message will send when ready…"
                : "TRANSMIT MESSAGE // Enter to send"
            }
            rows={2}
          />
          <button
            className="btn-send"
            onClick={send}
            disabled={loading || !input.trim() || backendState === "offline"}
          >
            {loading ? "..." : "SEND ▶"}
          </button>
        </div>
      </div>
    </div>
  )
}
