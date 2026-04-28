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

  // Clock - Live time display
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

  // Health check - Backend connectivity
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

  // Alerts polling - Get unread alert count
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

  // Agent status polling - Get agent metrics
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

  return (
    <aside className="modern-sidebar">
      {/* Logo Section */}
      <div className="sidebar-header">
        <div className="logo-wrapper">
          <div className="logo-icon">◆</div>
          <div>
            <div className="logo-name">ORA</div>
            <div className="logo-subtitle">Command Center</div>
          </div>
        </div>
      </div>

      {/* Time Widget */}
      <div className="time-widget">
        <div className="time-display">{time}</div>
        <div className="date-display">{date}</div>
      </div>

      {/* Status Card */}
      <div className="status-card-modern">
        <div className="card-header">
          <span className="card-title">Agent Online</span>
          <div className="status-badge">
            <div className="status-dot"></div>
            ACTIVE
          </div>
        </div>
        <div className="card-stats">
          <div className="stat-row">
            <span className="stat-label">Status</span>
            <span className="stat-value">{online ? "ACTIVE" : "OFFLINE"}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Latency</span>
            <span className="stat-value">{latency || "—"}ms</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Tasks</span>
            <span className="stat-value">{agentCtx?.tasks || 0}</span>
          </div>
        </div>
      </div>

      {/* Agent Card */}
      <div className={`agent-card-modern ${cycleFlash ? "pulse" : ""}`}>
        <div className="agent-badge">
          <div className="status-dot"></div>
          AGENT
        </div>
        <div className="agent-metrics-grid">
          <div className="metric-item">
            <div className="metric-label">Overdue</div>
            <div className="metric-number">{agentCtx?.overdue || 0}</div>
          </div>
          <div className="metric-item">
            <div className="metric-label">Goals</div>
            <div className="metric-number">{agentCtx?.goals || 0}</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`nav-link ${current === item.id ? "active" : ""}`}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="alert-counter">{unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="connection-status">
          <div className={`connection-indicator ${online ? "online" : "offline"}`}></div>
          <span className="connection-text">
            {online ? "Connected" : "Disconnected"}
          </span>
        </div>
        <div className="footer-divider"></div>
        <div className="system-info">
          <span>v2.0</span>
          <span>•</span>
          <span>KE</span>
        </div>
      </div>
    </aside>
  );
}
