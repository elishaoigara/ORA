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
  const statusColor = backendState === "online" ? "#39ff14" : backendState === "cold" ? "#ffa500" : "#718096";

  return (
    <div className="dashboard-container">
      {/* Header */}
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

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Messages</div>
          <div className="stat-value">{messages.length}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label">Responses</div>
          <div className="stat-value magenta">{messages.filter(m => m.role === "assistant" && !m.isError).length}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Actions</div>
          <div className="stat-value lime">{messages.filter(m => m.intent).length}</div>
        </div>
      </div>

      {/* Quick Commands */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">⚡</span>
          <span className="card-title">Quick Commands</span>
          <span className="card-badge">{currentChips.length}</span>
        </div>
        <div className="quick-commands">
          {currentChips.map((chip) => (
            <button
              key={chip.label}
              className="cyber-button"
              onClick={() => send(chip.msg)}
              disabled={loading}
              style={{ padding: "8px 16px", fontSize: "12px" }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">💬</span>
          <span className="card-title">Conversation</span>
          <span className="card-badge">{messages.length}</span>
        </div>
        
        <div className="chat-messages">
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
                className={`message ${isUser ? 'user' : 'assistant'}`}
              >
                <div className="message-bubble" style={{ 
                  background: isUser ? "rgba(255, 0, 110, 0.15)" : "rgba(0, 240, 255, 0.15)",
                  borderColor: isUser ? "rgba(255, 0, 110, 0.3)" : "rgba(0, 240, 255, 0.3)",
                  color: isError ? "#ff006e" : "var(--text-primary)"
                }}>
                  <div style={{ fontWeight: "bold", marginBottom: "8px" }}>
                    {isUser ? "👤 You" : "✨ ORA Assistant"}
                  </div>
                  {msg.action && (
                    <div style={{ fontSize: "11px", color: "#39ff14", marginBottom: "8px", padding: "8px", background: "rgba(57, 255, 20, 0.1)", borderRadius: "4px" }}>
                      ✅ Action: {msg.action.type?.replace(/_/g, " ").toUpperCase()}
                    </div>
                  )}
                  <div style={{ whiteSpace: "pre-wrap", fontSize: "13px" }}>
                    {msg.content}
                  </div>
                  <div className="message-time">
                    {(() => {
                      try {
                        return new Date(msg.timestamp).toLocaleTimeString("en-KE", { hour12: false, hour: "2-digit", minute: "2-digit" });
                      } catch {
                        return "";
                      }
                    })()}
                  </div>
                </div>
                {!isUser && (
                  <button 
                    className="cyber-button" 
                    onClick={() => copyMessage(msg.content, idx)}
                    style={{ padding: "4px 8px", fontSize: "11px", marginTop: "8px" }}
                  >
                    {copiedIdx === idx ? "✓ Copied" : "📋 Copy"}
                  </button>
                )}
              </div>
            );
          })}
          
          {loading && (
            <div className="message assistant">
              <div className="message-bubble" style={{ 
                background: "rgba(0, 240, 255, 0.15)",
                borderColor: "rgba(0, 240, 255, 0.3)"
              }}>
                <div style={{ fontWeight: "bold", marginBottom: "8px" }}>
                  ✨ ORA Assistant
                </div>
                <div style={{ fontSize: "13px", color: "#00f0ff", fontStyle: "italic" }}>
                  {thinkingText}
                </div>
              </div>
            </div>
          )}
          
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="chat-input">
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
          placeholder="Type your message or ask for help..."
          disabled={loading}
          rows="3"
        />
        <div style={{ display: "flex", gap: "8px", flexDirection: "column" }}>
          <button 
            className="cyber-button"
            onClick={() => send()}
            disabled={loading || !input.trim()}
            style={{ padding: "10px 16px" }}
          >
            Send
          </button>
          <button 
            className="cyber-button"
            onClick={toggleVoice}
            disabled={loading}
            style={{ padding: "10px 16px" }}
          >
            {listening ? "🎤 Stop" : "🎤 Voice"}
          </button>
          <button 
            className="cyber-button"
            onClick={clearChat}
            style={{ padding: "10px 16px" }}
          >
            Clear
          </button>
        </div>
      </div>
    </div>
  );
}

const chatStyles = `
.quick-commands {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.chat-messages {
  max-height: 500px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 0;
}

.message {
  display: flex;
  gap: 12px;
  animation: messageSlide 0.3s ease;
}

.message.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid;
  font-size: 13px;
  line-height: 1.5;
}

.message.user .message-bubble {
  background: rgba(255, 0, 110, 0.15);
  border-color: rgba(255, 0, 110, 0.3);
}

.message.assistant .message-bubble {
  background: rgba(0, 240, 255, 0.15);
  border-color: rgba(0, 240, 255, 0.3);
}

.message-time {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.chat-input {
  border-top: 1px solid rgba(0, 240, 255, 0.2);
  padding: 20px;
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.chat-textarea {
  flex: 1;
  background: rgba(26, 31, 58, 0.8);
  border: 1px solid rgba(0, 240, 255, 0.3);
  border-radius: 12px;
  padding: 12px;
  color: var(--text-primary);
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 13px;
  resize: none;
  transition: all 0.2s ease;
}

.chat-textarea:focus {
  outline: none;
  border-color: var(--neon-cyan);
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
}

.chat-textarea::placeholder {
  color: var(--text-tertiary);
}

@keyframes messageSlide {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
`;
