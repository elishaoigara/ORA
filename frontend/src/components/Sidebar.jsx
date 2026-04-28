import { useState, useEffect, useRef } from "react";
import { health, getAgentStatus, getAlerts } from "../api";

const navItems = [
  { id: "dashboard", icon: "🏠", label: "Dashboard" },
  { id: "chat", icon: "💬", label: "Chat" },
  { id: "tasks", icon: "✅", label: "Tasks" },
  { id: "alerts", icon: "⚠️", label: "Alerts" },
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

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }));
      setDate(
        now.toLocaleDateString("en-KE", {
          weekday: "short",
          day: "2-digit",
          month: "short",
        })
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
    if (!online) return { text: "Offline", color: "#ef4444", bg: "rgba(239, 68, 68, 0.1)", dot: "#ef4444" };
    if (latency > 1000) return { text: "Degraded", color: "#f97316", bg: "rgba(249, 115, 22, 0.1)", dot: "#f97316" };
    if (latency > 300) return { text: "Slow", color: "#eab308", bg: "rgba(234, 179, 8, 0.1)", dot: "#eab308" };
    return { text: "Online", color: "#10b981", bg: "rgba(16, 185, 129, 0.1)", dot: "#10b981" };
  };

  const getAgentConfig = () => {
    if (!agentCtx) return { state: "Idle", icon: "💤", color: "#71717a", bg: "rgba(113, 113, 122, 0.1)" };
    if (agentCtx.overdue > 0) return { state: "Critical", icon: "🚨", color: "#ef4444", bg: "rgba(239, 68, 68, 0.1)" };
    if (agentCtx.tasks > 0) return { state: "Active", icon: "⚡", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.1)" };
    return { state: "Monitoring", icon: "👁️", color: "#10b981", bg: "rgba(16, 185, 129, 0.1)" };
  };

  const status = getStatusConfig();
  const agent = getAgentConfig();

  return (
    <aside className="modern-sidebar">
      {/* Header with Logo - Fixed at top */}
      <div className="sidebar-header">
        <div className="logo-wrapper">
          <div className="logo-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#10b981" strokeWidth="1.5" fill="#10b981" fillOpacity="0.15"/>
              <path d="M2 17L12 22L22 17" stroke="#10b981" strokeWidth="1.5" fill="none"/>
              <path d="M2 12L12 17L22 12" stroke="#10b981" strokeWidth="1.5" fill="none"/>
              <circle cx="12" cy="12" r="2" fill="#10b981"/>
            </svg>
          </div>
          <div className="logo-text">
            <div className="logo-name">ORA</div>
            <div className="logo-subtitle">AI Assistant</div>
          </div>
        </div>
      </div>

      {/* Time Widget - Fixed */}
      <div className="time-widget">
        <div className="time-display">{time}</div>
        <div className="date-display">{date}</div>
      </div>

      {/* System Status Card - Fixed */}
      <div className="status-card-modern">
        <div className="card-header">
          <span className="card-title">System</span>
          <span className="status-badge" style={{ background: status.bg, color: status.color }}>
            <span className="status-dot" style={{ background: status.dot }} />
            {status.text}
          </span>
        </div>
        <div className="card-stats">
          {latency && (
            <div className="stat-row">
              <span className="stat-label">Latency</span>
              <span className="stat-value">{latency}ms</span>
            </div>
          )}
          <div className="stat-row">
            <span className="stat-label">Connection</span>
            <span className="stat-value">{online ? "Stable" : "Lost"}</span>
          </div>
        </div>
      </div>

      {/* Agent Status Card - Fixed */}
      {agentCtx && (
        <div className={`agent-card-modern ${cycleFlash ? "pulse" : ""}`}>
          <div className="card-header">
            <span className="card-title">Agent</span>
            <span className="agent-badge" style={{ background: agent.bg, color: agent.color }}>
              {agent.icon} {agent.state}
            </span>
          </div>
          <div className="agent-metrics-grid">
            <div className="metric-item">
              <div className="metric-label">Tasks</div>
              <div className="metric-number">{agentCtx.tasks ?? 0}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Overdue</div>
              <div className="metric-number" style={{ color: agentCtx.overdue > 0 ? "#ef4444" : "#71717a" }}>
                {agentCtx.overdue ?? 0}
              </div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Goals</div>
              <div className="metric-number">{agentCtx.goals ?? 0}</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation - THIS NEEDS TO BE SCROLLABLE */}
      <nav className="navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-link ${current === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="alert-counter">{unreadAlerts > 9 ? "9+" : unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer - Fixed at bottom */}
      <div className="sidebar-footer">
        <div className="connection-status">
          <div className={`connection-indicator ${online ? "online" : "offline"}`} />
          <span className="connection-text">{online ? "Connected" : "Disconnected"}</span>
        </div>
        <div className="footer-divider" />
        <div className="system-info">
          <span>KE</span>
          <span>•</span>
          <span>v2.0</span>
        </div>
      </div>
    </aside>
  );
}