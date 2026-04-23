import { useState, useEffect, useRef } from "react"
import API from "../api"

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)

  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const abortRef = useRef(null)

  // load history
  useEffect(() => {
    fetch(`${API}/conversation-history`)
      .then(async (r) => {
        if (!r.ok) throw new Error("Failed to load history")
        return r.json()
      })
      .then((data) => setMessages(Array.isArray(data) ? data : []))
      .catch((err) => {
        console.error("History error:", err)
      })
  }, [])

  // auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  const send = async () => {
    if (!input.trim() || loading) return

    const text = input.trim()
    setInput("")

    // cancel previous request
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    setMessages((prev) => [...prev, { role: "user", content: text }])
    setLoading(true)

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`)
      }

      const data = await res.json()

      const reply =
        data?.reply ||
        data?.error ||
        "[INVALID RESPONSE]"

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: reply },
      ])

    } catch (err) {
      if (err.name !== "AbortError") {
        console.error("Chat error:", err)

        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "[CONNECTION ERROR]" },
        ])
      }
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
          Direct channel to ORA · Context-aware intelligence system
        </div>
      </div>

      <div className="chat-messages">

        {messages.length === 0 && (
          <div className="empty" style={{ marginTop: "4rem" }}>
            <div className="empty-icon">◎</div>
            <div className="glow" style={{ marginBottom: 8 }}>
              ORA STANDING BY
            </div>
            <div>Ask about tasks, files, system state, or anything else</div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`msg ${m.role === "user" ? "user" : "ora"}`}
          >
            <div className="msg-avatar">
              {m.role === "user" ? "EL" : "◎"}
            </div>

            <div className="msg-bubble">
              {m.role === "assistant" && (
                <div className="msg-label">ORA // RESPONSE</div>
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
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="TRANSMIT MESSAGE // Enter to send"
            rows={2}
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