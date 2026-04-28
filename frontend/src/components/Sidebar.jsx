import { useState, useEffect, useRef } from "react";
import { health, getAgentStatus, getAlerts } from "../api";

const navItems = [
  { id: "dashboard", icon: "🏠", label: "Home" },
  { id: "chat", icon: "✨", label: "Assistant" },
  { id: "tasks", icon: "📌", label: "Tasks" },
  { id: "alerts", icon: "🔔", label: "Alerts" },
  { id: "knowledge", icon: "📖", label: "Knowledge" },
  { id: "memory", icon: "💭", label: "Memory" },
  { id: "research", icon: "🔍", label: "Research" },
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

  // Clock
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
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  // Health check
  useEffect(() => {
    const checkHealth = async () => {
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

    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  // Alerts
  useEffect(() => {
    const checkAlerts = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;

      try {
        const data = await getAlerts(20);
        if (Array.isArray(data)) {
          const unread = data.filter((item) => !item.acknowledged).length;
          setUnreadAlerts(unread);
        }
      } catch (error) {
        console.error("Failed to fetch alerts:", error);
      }

      pollingRef.current = false;
    };

    checkAlerts();
    const interval = setInterval(checkAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  // Agent status
  useEffect(() => {
    const fetchAgentStatus = async () => {
      try {
        const data = await getAgentStatus();
        setAgentCtx(data);
        setCycleFlash(true);
        setTimeout(() => setCycleFlash(false), 600);
      } catch (error) {
        console.error("Failed to fetch agent status:", error);
      }
    };

    fetchAgentStatus();
    const interval = setInterval(fetchAgentStatus, 20000);
    return () => clearInterval(interval);
  }, []);

  const getStatusConfig = () => {
    if (!online) return { text: "Offline", color: "#ef4444", dot: "offline" };
    if (latency > 1000) return { text: "Degraded", color: "#ef4444", dot: "warning" };
    if (latency > 300) return { text: "Slow", color: "#f59e0b", dot: "warning" };
    return { text: "Online", color: "#4ade80", dot: "online" };
  };

  const getAgentConfig = () => {
    if (!agentCtx) return { state: "Idle", icon: "😴", color: "#64748b" };
    if (agentCtx.overdue > 0) return { state: "Alert", icon: "🚨", color: "#ef4444" };
    if (agentCtx.tasks > 0) return { state: "Working", icon: "⚡", color: "#f59e0b" };
    return { state: "Active", icon: "🎯", color: "#4ade80" };
  };

  const statusConfig = getStatusConfig();
  const agentConfig = getAgentConfig();

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="logo-section">
        <div className="logo-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <div>
          <div className="logo-name">ORA</div>
          <div className="logo-sub">AI Assistant</div>
        </div>
      </div>

      {/* Time */}
      <div className="time-section">
        <div className="time">{time}</div>
        <div className="date">{date}</div>
      </div>

      {/* Status Card */}
      <div className="status-card">
        <div className="status-row">
          <span className="status-label">System</span>
          <div className="status-badge" style={{ background: `${statusConfig.color}15`, color: statusConfig.color }}>
            <span className={`status-dot ${statusConfig.dot}`} />
            {statusConfig.text}
          </div>
        </div>
        {latency && (
          <div className="status-row">
            <span className="status-label">Latency</span>
            <span className="status-value">{latency}ms</span>
          </div>
        )}
      </div>

      {/* Agent Card */}
      {agentCtx && (
        <div className={`agent-card ${cycleFlash ? "pulse" : ""}`}>
          <div className="agent-header">
            <span className="agent-icon">{agentConfig.icon}</span>
            <div>
              <div className="agent-state" style={{ color: agentConfig.color }}>
                {agentConfig.state}
              </div>
              <div className="agent-sub">Active Session</div>
            </div>
          </div>
          <div className="agent-metrics">
            <div className="metric">
              <span className="metric-label">Tasks</span>
              <span className="metric-value">{agentCtx.tasks ?? 0}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Overdue</span>
              <span className="metric-value" style={{ color: agentCtx.overdue > 0 ? "#ef4444" : "#64748b" }}>
                {agentCtx.overdue ?? 0}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Goals</span>
              <span className="metric-value">{agentCtx.goals ?? 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="nav-section">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-btn ${current === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-text">{item.label}</span>
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="alert-badge">{unreadAlerts > 9 ? "9+" : unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="footer">
        <div className="version">v0.5 · KE</div>
        <div className="connection">
          <div className={`connection-dot ${online ? "online" : "offline"}`} />
          <span>{online ? "Connected" : "Disconnected"}</span>
        </div>
      </div>
    </aside>
  );
}