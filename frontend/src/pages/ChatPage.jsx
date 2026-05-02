import { useState, useEffect, useRef, useCallback } from "react";
import { sendMessage, getConversations } from "../api";
import BASE_URL from "../api";

let _id = 0;
const uid = () => String(++_id);
const ts  = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
function fmtTs(raw) {
  if (!raw) return ts();
  try { return new Date(raw).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
}

const CHIP_SETS = {
  morning: [
    { label: "☀️ Brief",    msg: "give me my morning briefing" },
    { label: "📅 Calendar", msg: "what's on my calendar today" },
    { label: "🎯 Goals",    msg: "check my goal progress" },
    { label: "🔮 Focus",    msg: "what should I prioritize today" },
    { label: "💳 Spend",    msg: "how much have I spent today" },
  ],
  default: [
    { label: "📋 Tasks",    msg: "show my pending tasks" },
    { label: "💳 Spend",    msg: "how much have I spent today" },
    { label: "🎯 Goals",    msg: "what are my active goals" },
    { label: "📊 Briefing", msg: "give me a briefing" },
    { label: "⚡ Alerts",   msg: "any active alerts" },
    { label: "🔮 Focus",    msg: "what should I focus on right now" },
    { label: "📅 Calendar", msg: "what's on my calendar today" },
    { label: "🌤 Weather",  msg: "what's the weather like" },
  ],
  task: [
    { label: "✅ Done",     msg: "mark the last task complete" },
    { label: "📋 All",      msg: "show all my tasks" },
    { label: "⚡ High",     msg: "show high priority tasks" },
    { label: "🎯 Goals",    msg: "check my goal progress" },
    { label: "📊 Brief",    msg: "give me a briefing" },
  ],
};

const THINKING_STATES = [
  "Querying memory...", "Checking context...", "Scanning knowledge base...",
  "Cross-referencing data...", "Formulating response...", "Pulling your profile...", "Running inference...",
];

const INTENT_LABELS = {
  add_task: "TASK ADDED", remind: "REMINDER SET", complete_task: "TASK COMPLETE",
  delete_task: "TASK DELETED", search_docs: "FROM DOCS", spend_summary: "SPEND DATA",
  set_goal: "GOAL SET", goal_progress: "GOAL STATUS", check_tasks: "TASK LIST",
  briefing: "BRIEFING", calendar: "CALENDAR", github: "GITHUB", weather: "WEATHER",
};

function getGreeting() {
  const h = new Date().getHours();
  if (h < 5)  return { title: "Night session.",        sub: "ORA is always on." };
  if (h < 12) return { title: "Good morning, Elisha.", sub: "Let's see what today looks like." };
  if (h < 17) return { title: "Afternoon, Elisha.",    sub: "What do you need?" };
  if (h < 21) return { title: "Evening, Elisha.",      sub: "Winding down or pushing through?" };
  return           { title: "Late night session.",      sub: "Noted." };
}

function RenderMd({ text, isUser }) {
  if (!text) return null;
  const lines = text.split("\n");
  return (
    <div>
      {lines.map((line, i) => {
        if (line.trim() === "") return <div key={i} style={{ height: 6 }} />;
        if (line.match(/^[-•*]\s/))
          return (
            <div key={i} className="md-bullet-row">
              <span className={`md-bullet-dot ${isUser ? "user-text" : ""}`}>•</span>
              <span className={`md-text ${isUser ? "user-text" : ""}`}>{renderInline(line.slice(2), isUser)}</span>
            </div>
          );
        if (line.match(/^\d+\.\s/)) {
          const num  = line.match(/^(\d+)/)[1];
          const rest = line.replace(/^\d+\.\s/, "");
          return (
            <div key={i} className="md-bullet-row">
              <span className={`md-bullet-dot ${isUser ? "user-text" : ""}`}>{num}.</span>
              <span className={`md-text ${isUser ? "user-text" : ""}`}>{renderInline(rest, isUser)}</span>
            </div>
          );
        }
        if (line.startsWith("```")) return null;
        if (line.startsWith("    ")) return <code key={i} className="md-code-block">{line.slice(4)}</code>;
        return <div key={i} className={`md-text ${isUser ? "user-text" : ""}`}>{renderInline(line, isUser)}</div>;
      })}
    </div>
  );
}

function renderInline(text, isUser) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**"))
      return <strong key={i} className={`md-bold ${isUser ? "user-text" : ""}`}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`"))
      return <code key={i} className="md-inline-code">{p.slice(1, -1)}</code>;
    return p;
  });
}

function Message({ item, onCopy }) {
  const isUser     = item.role === "user";
  const intentLabel = item.intent ? INTENT_LABELS[item.intent] : null;
  return (
    <div className={`msg-row ${isUser ? "user" : ""}`}>
      {!isUser && <div className="msg-avatar">◉</div>}
      <div className={`msg-bubble ${isUser ? "user-msg" : item.isError ? "error" : "ora"}`}>
        {!isUser && (
          <div className={`msg-label ${item.isError ? "error-lbl" : ""}`}>
            {item.isError ? "ORA // ERROR" : intentLabel ? `ORA // ${intentLabel}` : "ORA // RESPONSE"}
          </div>
        )}
        {intentLabel && !isUser && (
          <div className="action-badge"><span className="action-badge-text">⚡ ACTION EXECUTED</span></div>
        )}
        {item.thinking ? (
          <div className="thinking-row">
            <span className="thinking-dots">⋯</span>
            <span className="thinking-label">{item.thinkingText || "Processing..."}</span>
          </div>
        ) : (
          <RenderMd text={item.content} isUser={isUser} />
        )}
        <div className={`msg-ts ${isUser ? "user-ts" : ""}`}>{item.ts}</div>
      </div>
      {!isUser && !item.thinking && (
        <button className="btn btn-sm" style={{ marginTop: 4 }} onClick={() => onCopy(item.content)} title="Copy">⎘</button>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [messages,     setMessages]     = useState([]);
  const [input,        setInput]        = useState("");
  const [loading,      setLoading]      = useState(false);
  const [chipSet,      setChipSet]      = useState("default");
  const [toast,        setToast]        = useState(null);
  const [voiceActive,  setVoiceActive]  = useState(false);
  const [voiceStatus,  setVoiceStatus]  = useState("");
  const [rows,         setRows]         = useState(1); // textarea auto-grow

  const mediaRecorderRef = useRef(null);
  const audioChunksRef   = useRef([]);
  const listRef          = useRef(null);
  const inputRef         = useRef("");
  const textareaRef      = useRef(null);
  const thinkId          = useRef(null);
  const thinkTimer       = useRef(null);
  const thinkIdx         = useRef(0);

  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 2500);
  };

  useEffect(() => {
    const h = new Date().getHours();
    if (h >= 6 && h < 10) setChipSet("morning");
  }, []);

  useEffect(() => {
    getConversations(40)
      .then(data => {
        if (!Array.isArray(data) || !data.length) return;
        setMessages(data.map(m => ({ ...m, id: uid(), ts: fmtTs(m.timestamp) })));
      })
      .catch(() => {});
  }, []);

  const scrollBottom = useCallback(() => {
    setTimeout(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }), 60);
  }, []);

  const startThinking = useCallback((id) => {
    thinkIdx.current = 0;
    thinkTimer.current = setInterval(() => {
      thinkIdx.current = (thinkIdx.current + 1) % THINKING_STATES.length;
      setMessages(prev => prev.map(m =>
        m.id === id ? { ...m, thinkingText: THINKING_STATES[thinkIdx.current] } : m
      ));
    }, 1400);
  }, []);

  const stopThinking = useCallback(() => {
    if (thinkTimer.current) { clearInterval(thinkTimer.current); thinkTimer.current = null; }
  }, []);

  const handleCopy = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => showToast("Copied", "success"));
  }, []);

  // Auto-grow textarea
  const handleInputChange = (e) => {
    const val = e.target.value;
    setInput(val);
    inputRef.current = val;
    // Compute rows: max 6
    const lineCount = (val.match(/\n/g) || []).length + 1;
    setRows(Math.min(lineCount, 6));
  };

  const send = useCallback(async (textOverride) => {
    const text = (textOverride ?? inputRef.current).trim();
    if (!text || loading) return;

    const tId = uid();
    thinkId.current = tId;

    const userMsg  = { id: uid(), role: "user",      content: text, ts: ts() };
    const thinkMsg = { id: tId,   role: "assistant", content: "", ts: "", thinking: true, thinkingText: THINKING_STATES[0] };

    setMessages(prev => [...prev, userMsg, thinkMsg]);
    setInput(""); inputRef.current = ""; setRows(1);
    setLoading(true);
    scrollBottom();
    startThinking(tId);

    try {
      const res   = await sendMessage(text);
      const reply = res?.reply || "No response";
      const intent = res?.intent || null;
      stopThinking();
      setMessages(prev => prev.map(m =>
        m.id === tId ? { ...m, content: reply, ts: ts(), thinking: false, intent } : m
      ));
      if (intent?.includes("task") || intent?.includes("remind")) {
        setChipSet("task");
        setTimeout(() => setChipSet("default"), 30000);
      }
    } catch {
      stopThinking();
      setMessages(prev => prev.map(m =>
        m.id === tId ? {
          ...m,
          content: "ORA unreachable — backend may be spinning up. Wait 30s and retry.",
          ts: ts(), thinking: false, isError: true,
        } : m
      ));
    } finally {
      setLoading(false);
      scrollBottom();
    }
  }, [loading, scrollBottom, startThinking, stopThinking]);

  const startVoice = useCallback(async () => {
    if (voiceActive) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      recorder.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        setVoiceStatus("transcribing");
        try {
          const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
          const form = new FormData();
          form.append("file", blob, "voice.webm");
          const res = await fetch(`${BASE_URL}/api/voice/transcribe`, { method: "POST", body: form });
          if (!res.ok) throw new Error("fail");
          const data = await res.json();
          if (data.transcript) {
            setMessages(prev => [...prev,
              { id: uid(), role: "user",      content: `🎙️ ${data.transcript}`, ts: ts() },
              { id: uid(), role: "assistant", content: data.reply || "Got it.", ts: ts() },
            ]);
            scrollBottom();
          } else {
            showToast("Couldn't understand audio", "error");
          }
        } catch { showToast("Voice transcription failed", "error"); }
        finally { setVoiceActive(false); setVoiceStatus(""); }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setVoiceActive(true);
      setVoiceStatus("recording");
    } catch { showToast("Microphone access denied", "error"); }
  }, [voiceActive, scrollBottom]);

  const stopVoice = useCallback(() => {
    if (mediaRecorderRef.current?.state !== "inactive") mediaRecorderRef.current.stop();
  }, []);

  const chips    = CHIP_SETS[chipSet] || CHIP_SETS.default;
  const greeting = getGreeting();

  const voicePlaceholder =
    voiceStatus === "recording"    ? "🔴 Recording — tap mic to stop..." :
    voiceStatus === "transcribing" ? "Transcribing..." :
    "Message ORA...";

  return (
    <div className="chat-page">
      {/* Messages */}
      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">◉</div>
            <div className="chat-empty-title">{greeting.title}</div>
            <div className="chat-empty-sub">{greeting.sub}</div>
            <div className="chat-empty-sub" style={{ marginTop: 8, color: "var(--text-5)" }}>
              All systems nominal · Neural link active
            </div>
          </div>
        )}
        {messages.map(item => (
          <Message key={item.id} item={item} onCopy={handleCopy} />
        ))}
      </div>

      {/* Quick chips */}
      <div className="chips-bar">
        {chips.map(c => (
          <button key={c.label} className="chip" onClick={() => send(c.msg)} disabled={loading}>
            {c.label}
          </button>
        ))}
      </div>

      <div className="chat-note">FREE TIER · COLD START MAY TAKE ~30s</div>

      {/* ── Input bar — works on both mobile and desktop ── */}
      <div className="chat-input-bar">
        {/* Voice button */}
        <button
          className="chat-voice-btn"
          title={voiceActive ? "Stop recording" : "Voice input"}
          onClick={voiceActive ? stopVoice : startVoice}
          disabled={loading || voiceStatus === "transcribing"}
          style={{
            background:   voiceActive ? "rgba(255,68,68,0.15)" : "transparent",
            border:       voiceActive ? "1px solid rgba(255,68,68,0.5)" : "1px solid var(--border-2)",
            color:        voiceActive ? "#ff4444" : "var(--text-3)",
            animation:    voiceActive ? "pulse 1.2s ease-in-out infinite" : "none",
          }}
          aria-label="Voice input"
        >
          {voiceStatus === "transcribing" ? "⋯" : "🎙"}
        </button>

        {/* Auto-growing textarea */}
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder={voicePlaceholder}
          value={input}
          rows={rows}
          onChange={handleInputChange}
          onKeyDown={e => {
            // Desktop: Enter sends, Shift+Enter newline
            // Mobile: always newline (virtual keyboard Enter)
            if (e.key === "Enter" && !e.shiftKey && window.innerWidth >= 768) {
              e.preventDefault();
              send();
            }
          }}
          disabled={loading || voiceActive}
          aria-label="Message input"
        />

        {/* Send button */}
        <button
          className="chat-send-btn"
          onClick={() => send()}
          disabled={!input.trim() || loading}
          aria-label="Send message"
        >
          {loading ? "⋯" : "▶"}
        </button>
      </div>

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
    </div>
  );
}
