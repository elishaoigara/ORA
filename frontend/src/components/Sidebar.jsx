import { useState, useEffect } from "react";
import { health, getAlerts } from "../api";
import BASE_URL from "../api";

const navItems = [
  { id: "dashboard", icon: "◈", label: "DASHBOARD" },
  { id: "chat",      icon: "◉", label: "CHAT" },
  { id: "inbox",     icon: "✉", label: "INBOX" },
  { id: "tasks",     icon: "◻", label: "TASKS" },
  { id: "alerts",    icon: "△", label: "ALERTS" },
  { id: "knowledge", icon: "◆", label: "KNOWLEDGE" },
  { id: "memory",    icon: "◌", label: "MEMORY" },
  { id: "research",  icon: "⊕", label: "RESEARCH" },
  { id: "content",   icon: "✍️", label: "CONTENT" },     // ← Content Studio
  { id: "code",      icon: "⌥",  label: "CODE" },          // ← Code Agent
];

function fmtTime(d) {
  return d.toLocaleTimeString("en-KE", { hour12: false });
}
function fmtDate(d) {
  return d.toLocaleDateString("en-KE", { weekday: "short", day: "2-digit", month: "short" }).toUpperCase();
}

export default function Sidebar({ current, onNavigate }) {
  const [time, setTime] = useState(fmtTime(new Date()));
  const [date, setDate] = useState(fmtDate(new Date()));
  const [online, setOnline] = useState(false);
  const [latency, setLatency] = useState(null);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [unreadEmails, setUnreadEmails] = useState(0);

  useEffect(() => {
    const tick = () => { 
      const n = new Date(); 
      setTime(fmtTime(n)); 
      setDate(fmtDate(n)); 
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      const t0 = performance.now();
      try {
        const d = await health();
        setOnline(d?.status === "ok");
        setLatency(Math.round(performance.now() - t0));
      } catch { 
        setOnline(false); 
        setLatency(null); 
      }
    };
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await getAlerts(20);
        if (Array.isArray(data)) setUnreadAlerts(data.filter(a => !a.acknowledged).length);
      } catch {}
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const checkGmail = async () => {
      try {
        const res = await fetch(BASE_URL + "/api/gmail/summary");
        if (res.ok) {
          const data = await res.json();
          setUnreadEmails(data?.unread_count || 0);
        }
      } catch {}
    };
    checkGmail();
    const id = setInterval(checkGmail, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-title">ORA</div>
        <div className="sidebar-logo-sub">AUTONOMOUS AGENT</div>
      </div>

      <div className="sidebar-time">
        <div className="sidebar-clock">{time}</div>
        <div className="sidebar-date">{date}</div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">NAVIGATION</div>
        {navItems.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`nav-item ${current === item.id ? "active" : ""}`}
          >
            <span className="nav-item-icon">{item.icon}</span>
            <span>{item.label}</span>
            
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="nav-badge">{unreadAlerts}</span>
            )}
            {item.id === "inbox" && unreadEmails > 0 && (
              <span className="nav-badge" style={{ background: "#ff9900" }}>{unreadEmails}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="status-row">
          <div className={`status-dot ${online ? "online" : "offline"}`} />
          <span className="status-text">{online ? "CONNECTED" : "OFFLINE"}</span>
          {latency && <span className="status-latency">{latency}ms</span>}
        </div>
      </div>
    </aside>
  );
}