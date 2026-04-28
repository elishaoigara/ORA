import { useState, useEffect, useRef, useCallback } from "react";
import { sendMessage, getConversations } from "../api";
import BASE from "../api";

// Quick action sets
const QUICK_SETS = {
  default: [
    { label: "📋 Tasks", msg: "show my pending tasks" },
    { label: "🎯 Goals", msg: "what are my active goals" },
    { label: "💳 Spend", msg: "how much have I spent today" },
    { label: "📊 Briefing", msg: "give me a full briefing" },
    { label: "⚡ Alerts", msg: "any active alerts" },
    { label: "📅 Calendar", msg: "what's on my calendar today" },
    { label: "🔮 Focus", msg: "what should I focus on right now" },
  ],
  task: [
    { label: "✅ Complete", msg: "mark the last task as complete" },
    { label: "📋 All Tasks", msg: "show all my tasks" },
    { label: "⚡ High Priority", msg: "show high priority tasks" },
    { label: "➕ Add Task", msg: "add task " },
  ],
  morning: [
    { label: "☀️ Briefing", msg: "give me my morning briefing" },
    { label: "📅 Today", msg: "what's on my calendar today" },
    { label: "🎯 Goals", msg: "check my goal progress" },
    { label: "🔮 Focus", msg: "what should I prioritize today" },
  ],
};

// Thinking states
const THINKING_STATES = [
  "Analyzing context...",
  "Searching memory...",
  "Processing request...",
  "Formulating response...",
  "Checking knowledge base...",
];

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendState, setBackendState] = useState("connecting");
  const [thinkingText, setThinkingText] = useState(THINKING_STATES[0]);
  const [quickSet, setQuickSet] = useState("default");
  const [listening, setListening] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState(null);

  const bottomRef = useRef(null);
  const thinkRef = useRef(null);
  const recognRef = useRef(null);
  const textareaRef = useRef(null);

  // Health check
  useEffect(() => {
    fetch(`${BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendState(d?.status === "ok" ? "online" : "cold"))
      .catch(() => setBackendState("cold"));
  }, []);

  // Load history
  useEffect(() => {
    getConversations(40)
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  // Auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Thinking cycle
  useEffect(() => {
    if (loading) {
      let i = 0;
      thinkRef.current = setInterval(() => {
        i = (i + 1) % THINKING_STATES.length;
        setThinkingText(THINKING_STATES[i]);
      }, 1500);
    } else {
      clearInterval(thinkRef.current);
    }
    return () => clearInterval(thinkRef.current);
  }, [loading]);

  // Context-aware quick actions
  useEffect(() => {
    const hour = new Date().getHours();
    if (hour >= 6 && hour < 10) setQuickSet("morning");
    else setQuickSet("default");
  }, []);

  // Send message
  const send = useCallback(async (textOverride) => {
    const text = (textOverride ?? input).trim();
    if (!text || loading) return;

    if (textOverride?.endsWith(" ")) {
      setInput(textOverride);
      textareaRef.current?.focus();
      return;
    }

    setInput("");
    setLoading(true);

    setMessages(prev => [...prev, {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    }]);

    try {
      const res = await sendMessage(text);

      setMessages(prev => [...prev, {
        role: "assistant",
        content: res?.reply || "No response received.",
        model: res?.model,
        cached: res?.cached,
        intent: res?.intent,
        timestamp: new Date().toISOString(),
        type: "response",
        action: res?.intent ? { type: res.intent, reply: res.reply } : null,
      }]);
      setBackendState("online");

      if (res?.intent?.includes("task") || res?.intent?.includes("remind")) {
        setQuickSet("task");
        setTimeout(() => setQuickSet("default"), 30000);
      }

    } catch (error) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Unable to reach ORA. The system may be starting up. Please try again in a moment.",
        isError: true,
        timestamp: new Date().toISOString(),
        type: "error",
      }]);
      setBackendState("cold");
    }

    setLoading(false);
  }, [input, loading]);

  // Voice input
  const toggleVoice = useCallback(() => {
    if (!("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      alert("Voice input is not supported in this browser.");
      return;
    }
    
    if (listening) {
      recognRef.current?.stop();
      setListening(false);
      return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = "en-KE";
    recognition.interimResults = false;
    
    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setInput(transcript);
      setListening(false);
    };
    
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognition.start();
    
    recognRef.current = recognition;
    setListening(true);
  }, [listening]);

  // Copy to clipboard
  const copyMessage = useCallback((text, idx) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    });
  }, []);

  // Clear chat
  const clearChat = useCallback(() => {
    if (window.confirm("Clear your conversation history?")) {
      setMessages([]);
    }
  }, []);

  const currentChips = QUICK_SETS[quickSet] || QUICK_SETS.default;
  const statusColor = backendState === "online" ? "#22c55e" : backendState === "cold" ? "#eab308" : "#64748b";

  return (
    <div className="dashboard-container">
      {/* Header - Same as Dashboard */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Neural Link</h1>
          <p className="dashboard-subtitle">Conversational AI Assistant</p>
        </div>
        <div className="header-time" style={{ color: statusColor }}>
          <span className="status-dot" style={{ background: statusColor }}></span>
          {backendState === "online" ? "ONLINE" : backendState === "cold" ? "STARTING" : "CONNECTING"}
        </div>
      </div>

      {/* Stats Cards - Same as Dashboard */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">💬</div>
          <div className="stat-content">
            <div className="stat-number">{messages.length}</div>
            <div className="stat-label">Messages</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">⚡</div>
          <div className="stat-content">
            <div className="stat-number">{messages.filter(m => m.role === "assistant" && !m.isError).length}</div>
            <div className="stat-label">Responses</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🎯</div>
          <div className="stat-content">
            <div className="stat-number">{messages.filter(m => m.intent).length}</div>
            <div className="stat-label">Actions</div>
          </div>
        </div>
      </div>

      {/* Quick Actions - Styled like Dashboard cards */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">⚡</span>
          <span className="card-title">Quick Commands</span>
          <span className="card-badge">{currentChips.length}</span>
        </div>
        <div className="tasks-list" style={{ gap: "10px", flexDirection: "row", flexWrap: "wrap" }}>
          {currentChips.map((chip) => (
            <button
              key={chip.label}
              className="ack-btn"
              onClick={() => send(chip.msg)}
              disabled={loading}
              style={{ padding: "8px 16px", fontSize: "12px" }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Messages - Styled like Dashboard alerts */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">💬</span>
          <span className="card-title">Conversation</span>
          <span className="card-badge">{messages.length}</span>
        </div>
        
        <div className="alerts-list" style={{ maxHeight: "500px", overflowY: "auto" }}>
          {messages.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">✨</div>
              <div className="empty-text">No messages yet</div>
              <div className="connect-link" style={{ cursor: "default" }}>
                Start a conversation below
              </div>
            </div>
          )}
          
          {messages.map((msg, idx) => {
            const isUser = msg.role === "user";
            const isError = msg.isError;
            return (
              <div 
                key={idx} 
                className="alert-item" 
                style={{ 
                  borderLeftColor: isUser ? "var(--green-primary)" : "var(--info)",
                  background: isUser ? "rgba(34, 197, 94, 0.05)" : "var(--bg-primary)",
                  flexDirection: "column",
                  alignItems: "flex-start"
                }}
              >
                <div className="alert-message" style={{ fontWeight: "bold", marginBottom: "8px" }}>
                  {isUser ? "👤 You" : "✨ ORA Assistant"}
                  <span className="alert-time" style={{ marginLeft: "12px" }}>
                    {(() => {
                      try {
                        return new Date(msg.timestamp).toLocaleTimeString("en-KE", { hour12: false, hour: "2-digit", minute: "2-digit" });
                      } catch {
                        return "";
                      }
                    })()}
                  </span>
                </div>
                
                {msg.action && (
                  <div className="finance-alert" style={{ marginBottom: "8px", width: "100%" }}>
                    ✅ Action Executed: {msg.action.type?.replace(/_/g, " ").toUpperCase()}
                  </div>
                )}
                
                <div className="alert-message" style={{ color: isError ? "var(--error)" : "var(--text-primary)", whiteSpace: "pre-wrap" }}>
                  {msg.content}
                </div>
                
                {!isUser && !isError && (
                  <button 
                    className="ack-btn" 
                    onClick={() => copyMessage(msg.content, idx)}
                    style={{ marginTop: "8px", alignSelf: "flex-end" }}
                  >
                    {copiedIdx === idx ? "✓ Copied!" : "📋 Copy"}
                  </button>
                )}
              </div>
            );
          })}
          
          {loading && (
            <div className="alert-item" style={{ borderLeftColor: "var(--warning)" }}>
              <div className="alert-message">
                <span className="typing-dots" style={{ display: "inline-flex", gap: "4px", marginRight: "8px" }}>
                  <span style={{ width: "6px", height: "6px", background: "var(--green-primary)", borderRadius: "50%", animation: "pulse 1.4s infinite" }}></span>
                  <span style={{ width: "6px", height: "6px", background: "var(--green-primary)", borderRadius: "50%", animation: "pulse 1.4s infinite 0.2s" }}></span>
                  <span style={{ width: "6px", height: "6px", background: "var(--green-primary)", borderRadius: "50%", animation: "pulse 1.4s infinite 0.4s" }}></span>
                </span>
                {thinkingText}
              </div>
            </div>
          )}
          
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input Area - Styled like Dashboard cards */}
      <div className="dashboard-card" style={{ marginBottom: 0 }}>
        <div className="card-header">
          <span className="card-icon">📝</span>
          <span className="card-title">Message Input</span>
          <button 
            className="ack-btn" 
            onClick={toggleVoice}
            style={{ background: listening ? "rgba(239, 68, 68, 0.1)" : "transparent", borderColor: listening ? "var(--error)" : "var(--border-light)" }}
          >
            {listening ? "⏹️ Stop" : "🎙️ Voice"}
          </button>
        </div>
        
        <textarea
          ref={textareaRef}
          className="chat-textarea-modern"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={listening ? "🎙 Listening..." : "Type your message... (Enter to send)"}
          disabled={loading}
          style={{
            width: "100%",
            padding: "12px",
            background: "var(--bg-primary)",
            border: `1px solid ${listening ? "var(--error)" : "var(--border)"}`,
            borderRadius: "var(--radius-md)",
            color: "var(--text-primary)",
            fontFamily: "inherit",
            fontSize: "13px",
            resize: "vertical",
            marginBottom: "12px"
          }}
        />
        
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <div className="alert-meta" style={{ fontSize: "10px" }}>
            <span>⏎ Enter to send</span>
            <span>⇧ Enter for new line</span>
          </div>
          <button 
            className="ack-all-btn" 
            onClick={() => send()}
            disabled={loading || !input.trim()}
            style={{ background: "var(--green-primary)", color: "var(--bg-primary)" }}
          >
            {loading ? "⏳ Sending..." : "📤 Send Message"}
          </button>
        </div>
        
        <div className="sync-info" style={{ marginTop: "12px" }}>
          <span className="sync-label">Free Tier</span>
          <span className="sync-time">Cold start may take 30 seconds</span>
        </div>
      </div>
    </div>
  );
}