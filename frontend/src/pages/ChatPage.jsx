import { useState, useEffect, useRef } from "react"
import API from "../api"

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [backendState, setBackendState] = useState("connecting")

  const bottomRef = useRef(null)
  const abortRef = useRef(null)

  // ✅ backend check
  useEffect(() => {
    fetch(`${API}/api/health`)
      .then(() => setBackendState("online"))
      .catch(() => setBackendState("cold"))
  }, [])

  // ✅ FIXED: correct history endpoint
  useEffect(() => {
    fetch(`${API}/api/conversations`)
      .then(r => r.ok ? r.json() : [])
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

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
        signal: abortRef.current.signal
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = await res.json()

      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: data?.reply || "[EMPTY RESPONSE]"
        }
      ])

      setBackendState("online")

    } catch (err) {
      console.error(err)

      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: "⚠ ORA temporarily unavailable.",
          isError: true
        }
      ])

      setBackendState("cold")
    }

    setLoading(false)
  }

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat-page">

      <div className="chat-header">
        <div className="page-title">// Neural Link</div>
        <div className="page-sub">
          Direct channel to ORA
          {backendState === "online" && (
            <span style={{ marginLeft: 10, color: "var(--green)" }}>● LIVE</span>
          )}
          {backendState === "cold" && (
            <span style={{ marginLeft: 10, color: "var(--amber)" }}>● WAKING</span>
          )}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty" style={{ marginTop: "4rem" }}>
            <div className="empty-icon">◎</div>
            <div className="glow">ORA STANDING BY</div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role === "user" ? "user" : "ora"}`}>
            <div className="msg-avatar">
              {m.role === "user" ? "EL" : "◎"}
            </div>

            <div className="msg-bubble">
              {m.role === "assistant" && (
                <div className="msg-label">
                  {m.isError ? "ORA // ERROR" : "ORA // RESPONSE"}
                </div>
              )}
              <div style={{ whiteSpace: "pre-wrap" }}>
                {m.content}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg ora">
            <div className="msg-avatar">◎</div>
            <div className="msg-bubble">
              <div className="msg-label">ORA // PROCESSING</div>
              <div className="thinking-dots">
                <span>▪</span><span>▪</span><span>▪</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-input-row">

          <textarea
            className="chat-textarea"
            value={input}
            disabled={loading}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="TRANSMIT MESSAGE // Enter to send"
          />

          <button
            className="btn-send"
            onClick={send}
            disabled={loading || !input.trim()}
          >
            {loading ? "..." : "SEND ▶"}
          </button>

        </div>
      </div>

    </div>
  )
}