/** @jsxImportSource react */
import { useState, useEffect, useRef } from "react";
import { health, getAgentStatus, getAlerts } from "../api";

const nav = [
  { id: "dashboard", icon: "📊", label: "Dashboard" },
  { id: "chat", icon: "💬", label: "Chat" },
  { id: "tasks", icon: "✓", label: "Tasks" },
  { id: "alerts", icon: "⚠", label: "Alerts" },
  { id: "knowledge", icon: "📚", label: "Knowledge" },
  { id: "memory", icon: "🧠", label: "Memory" },
  { id: "research", icon: "🔬", label: "Research" },
];

export default function Sidebar({ current, onNavigate }) {
  const [time, setTime] = useState("");
  const [date, setDate] = useState("");
  const [online, setOnline] = useState(false);
  const [latency, setLatency] = useState(null);

  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [agentCtx, setAgentCtx] = useState(null);
  const [cycleFlash, setCycleFlash] = useState(false);

  const pollingRef = useRef(false);

  /* ───────── CLOCK ───────── */
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }));
      setDate(
        now
          .toLocaleDateString("en-KE", {
            weekday: "short",
            day: "2-digit",
            month: "short",
          })
          .toUpperCase()
      );
    };

    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  /* ───────── HEALTH CHECK ───────── */
  useEffect(() => {
    const check = async () => {
      const start = performance.now();

      try {
        const data = await health();
        const end = performance.now();

        setOnline(data?.status === "ok");
        setLatency(Math.round(end - start));
      } catch {
        setOnline(false);
        setLatency(null);
      }
    };

    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  /* ───────── ALERTS ───────── */
  useEffect(() => {
    const check = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;

      try {
        const data = await getAlerts(20);

        if (Array.isArray(data)) {
          setUnreadAlerts(data.filter((a) => !a.acknowledged).length);
        }
      } catch {}

      pollingRef.current = false;
    };

    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, []);

  /* ───────── AGENT STATUS ───────── */
  useEffect(() => {
    const fetch_ = async () => {
      try {
        const data = await getAgentStatus();
        setAgentCtx(data);

        setCycleFlash(true);
        setTimeout(() => setCycleFlash(false), 600);
      } catch {}
    };

    fetch_();
    const t = setInterval(fetch_, 20000);
    return () => clearInterval(t);
  }, []);

  /* ───────── STATUS CONFIGURATION ───────── */
  const getStatusConfig = () => {
    if (!online) return { text: "Offline", color: "var(--error)", dot: "offline" };
    if (latency > 1000) return { text: "Degraded", color: "var(--error)", dot: "warning" };
    if (latency > 300) return { text: "Slow Link", color: "var(--warning)", dot: "warning" };
    return { text: "Operational", color: "var(--success)", dot: "online" };
  };

  const getAgentConfig = () => {
    if (!agentCtx) return { state: "Idle", icon: "💤", color: "var(--text-tertiary)" };
    if (agentCtx.overdue > 0) return { state: "Intervening", icon: "⚡", color: "var(--error)" };
    if (agentCtx.tasks > 0) return { state: "Processing", icon: "🔄", color: "var(--warning)" };
    return { state: "Monitoring", icon: "👁", color: "var(--success)" };
  };

  const status = getStatusConfig();
  const agent = getAgentConfig();

  return (
    <aside className="sidebar">
      {/* LOGO AREA */}
      <div className="sidebar-logo">
        <div className="logo-icon">
          <span>⚡</span>
        </div>
        <div>
          <div className="logo-name">ORA</div>
          <div className="logo-sub">Personal AI Assistant</div>
        </div>
      </div>

      {/* CLOCK DISPLAY */}
      <div className="clock-display">
        <div className="clock-time">{time}</div>
        <div className="clock-date">{date} · EAT</div>
      </div>

      {/* SYSTEM STATUS */}
      <div className="status-panel">
        <div className="status-header">
          <span className="status-label">System</span>
          <span className="status-value" style={{ color: status.color }}>
            {status.text}
          </span>
        </div>
        <div className="status-detail">
          <div className={`status-indicator ${status.dot}`} />
          {latency && <span className="status-latency">{latency}ms</span>}
        </div>
      </div>

      {/* AGENT STATUS */}
      {agentCtx && (
        <div className={`agent-panel ${cycleFlash ? "flash" : ""}`}>
          <div className="agent-header">
            <span className="agent-icon">{agent.icon}</span>
            <span className="agent-state" style={{ color: agent.color }}>
              {agent.state}
            </span>
          </div>
          <div className="agent-stats">
            <div className="stat-item">
              <span className="stat-label">Tasks</span>
              <span className="stat-number">{agentCtx.tasks ?? 0}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Overdue</span>
              <span
                className="stat-number"
                style={{
                  color: agentCtx.overdue > 0 ? "var(--error)" : "var(--text-tertiary)",
                }}
              >
                {agentCtx.overdue ?? 0}
              </span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Goals</span>
              <span className="stat-number">{agentCtx.goals ?? 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* NAVIGATION */}
      <nav className="sidebar-nav">
        {nav.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${current === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>

            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="nav-badge">{unreadAlerts > 9 ? "9+" : unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* FOOTER */}
      <div className="sidebar-footer">
        <div className="footer-version">v0.5 · Nairobi, KE</div>
        <div className="footer-status">
          <span className={`footer-dot ${online ? "active" : "inactive"}`} />
          <span>{online ? "Connected" : "Reconnecting"}</span>
        </div>
      </div>
    </aside>
  );
}