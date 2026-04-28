/** @jsxImportSource react */
import { useState, useEffect, useRef, useCallback, forwardRef } from "react";
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
  const statusText = backendState === "online" ? "Online" : backendState === "cold" ? "Starting" : "Connecting";

  return (
    <div className="chat-container-modern">
      {/* Header */}
      <div className="chat-header-modern">
        <div className="chat-title-section">
          <span className="chat-icon">💬</span>
          <div>
            <h2 className="chat-title">Neural Link</h2>
            <p className="chat-subtitle">Conversational AI Assistant</p>
          </div>
        </div>
        <div className="chat-actions">
          <div className="status-badge-modern" style={{ color: statusColor }}>
            <span className="status-icon">{backendState === "online" ? "●" : backendState === "cold" ? "◐" : "○"}</span>
            <span className="status-label">{statusText}</span>
          </div>
          <button className="clear-btn" onClick={clearChat} title="Clear history">🗑️</button>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions-modern">
        {currentChips.map((chip) => (
          <button key={chip.label} className="action-chip" onClick={() => send(chip.msg)} disabled={loading}>
            {chip.label}
          </button>
        ))}
      </div>

      {/* Messages Area */}
      <div className="messages-area">
        {messages.length === 0 && (
          <div className="welcome-modern">
            <div className="welcome-icon">✨</div>
            <h3 className="welcome-title">Welcome back, Elisha.</h3>
            <p className="welcome-text">ORA is standing by. Ask me about tasks, goals, spending, or anything you need assistance with.</p>
            <div className="welcome-hint">Try: "Show my pending tasks" or "What should I focus on?"</div>
          </div>
        )}
        
        {messages.map((msg, idx) => {
          const isUser = msg.role === "user";
          const isError = msg.isError;
          return (
            <div key={idx} className={`message-item ${isUser ? "user-message" : "assistant-message"} fade-in`}>
              <div className="message-avatar-modern">{isUser ? "👤" : "✨"}</div>
              <div className="message-bubble-modern">
                {!isUser && (
                  <div className="message-meta">
                    <span className="message-sender">ORA Assistant</span>
                    {msg.cached && <span className="message-badge">Cached</span>}
                    {msg.intent && <span className="message-badge">{msg.intent.replace(/_/g, " ")}</span>}
                  </div>
                )}
                
                {msg.action && (
                  <div className="action-card-modern">
                    <span className="action-icon">✅</span>
                    <span className="action-text">Action Executed: {msg.action.type?.replace(/_/g, " ").toUpperCase()}</span>
                  </div>
                )}
                
                <div className="message-content-modern" style={{ color: isError ? "#ef4444" : "#e2e8f0" }}>
                  {msg.content}
                </div>
                
                <div className="message-footer">
                  <span className="message-time">
                    {(() => {
                      try {
                        return new Date(msg.timestamp).toLocaleTimeString("en-KE", { hour12: false, hour: "2-digit", minute: "2-digit" });
                      } catch {
                        return "";
                      }
                    })()}
                  </span>
                  {!isUser && !isError && (
                    <button className="copy-btn" onClick={() => copyMessage(msg.content, idx)}>
                      {copiedIdx === idx ? "✓ Copied" : "📋 Copy"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        
        {loading && (
          <div className="typing-indicator-modern">
            <div className="typing-avatar">✨</div>
            <div className="typing-bubble">
              <div className="typing-dots"><span></span><span></span><span></span></div>
              <div className="typing-text">{thinkingText}</div>
            </div>
          </div>
        )}
        
        <div ref={bottomRef} />
      </div>

      {/* Input Area */}
      <div className="input-area-modern">
        <div className="input-wrapper">
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
            style={listening ? { borderColor: "#ef4444", boxShadow: "0 0 0 2px rgba(239, 68, 68, 0.2)" } : {}}
          />
          <div className="input-buttons">
            <button className="voice-btn" onClick={toggleVoice} style={listening ? { borderColor: "#ef4444", background: "rgba(239, 68, 68, 0.1)" } : {}}>
              {listening ? "⏹️" : "🎙️"}
            </button>
            <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
              {loading ? "⏳" : "📤"}
            </button>
          </div>
        </div>
        <div className="input-note">
          <span>🔌 Render free tier — cold start may take 30 seconds</span>
          <span>⏎ Enter to send · ⇧ Enter for new line</span>
        </div>
      </div>
    </div>
  );
}