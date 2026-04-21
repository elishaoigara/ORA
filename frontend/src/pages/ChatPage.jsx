import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  const loadHistory = async () => {
    try {
      const data = await fetch(`${API}/api/conversations`).then(r => r.json())
      setMessages(data)
    } catch {}
  }

  useEffect(() => {
    loadHistory()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const send = async () => {
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput("")
    setMessages(prev => [...prev, { role: "user", content: text }])
    setLoading(true)

    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }])
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "ORA is unreachable." }])
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
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.title}>💬 Chat with ORA</h1>
        <p style={s.sub}>Ask anything — ORA knows your context and your files</p>
      </div>

      <div style={s.chatBox}>
        {messages.length === 0 && (
          <div style={s.empty}>
            <p>👁 ORA is ready. Ask me anything.</p>
            <p style={{ color: "#333", marginTop: 8, fontSize: "0.85rem" }}>
              Try: "What should I focus on today?" or "Summarise my notes on X"
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 12 }}>
            <div style={{
              ...s.bubble,
              background: m.role === "user" ? "#1e1e3a" : "#0f0f1a",
              borderColor: m.role === "user" ? "#7c6af7" : "#1a1a2e",
              maxWidth: m.role === "assistant" ? "80%" : "65%"
            }}>
              {m.role === "assistant" && <div style={s.oraLabel}>👁 ORA</div>}
              <p style={{ fontSize: "0.9rem", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{m.content}</p>
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
            <div style={{ ...s.bubble, background: "#0f0f1a", borderColor: "#1a1a2e" }}>
              <div style={s.oraLabel}>👁 ORA</div>
              <p style={{ color: "#444", fontSize: "0.85rem" }}>🧠 thinking...</p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div style={s.inputRow}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Message ORA... (Enter to send)"
          style={s.input}
          rows={2}
        />
        <button onClick={send} disabled={loading || !input.trim()} style={s.sendBtn}>
          Send
        </button>
      </div>
    </div>
  )
}

const s = {
  page: { display: "flex", flexDirection: "column", height: "100vh", padding: "1.5rem" },
  header: { marginBottom: "1rem" },
  title: { color: "#7c6af7", fontSize: "1.3rem", fontWeight: 700 },
  sub: { color: "#333", fontSize: "0.8rem", marginTop: 4 },
  chatBox: { flex: 1, overflowY: "auto", padding: "1rem 0" },
  empty: { textAlign: "center", color: "#444", marginTop: "4rem" },
  bubble: { border: "1px solid", borderRadius: 12, padding: "0.75rem 1rem" },
  oraLabel: { color: "#7c6af7", fontSize: "0.72rem", fontWeight: 700, marginBottom: 6 },
  inputRow: { display: "flex", gap: 10, marginTop: "1rem" },
  input: {
    flex: 1, background: "#0d0d1a", border: "1px solid #1a1a2e",
    borderRadius: 12, padding: "0.75rem 1rem", color: "#e0e0e0",
    fontSize: "0.9rem", resize: "none", outline: "none"
  },
  sendBtn: {
    background: "#7c6af7", border: "none", borderRadius: 12,
    color: "#fff", padding: "0 1.5rem", cursor: "pointer",
    fontWeight: 600, fontSize: "0.9rem"
  }
}