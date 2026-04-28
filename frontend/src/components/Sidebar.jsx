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
            <div className="logo-subtitle">v2.0</div>
          </div>
        </div>
      </div>

      {/* Time Widget - Compact */}
      <div className="time-widget" style={{ padding: "12px", margin: "8px" }}>
        <div className="time-display" style={{ fontSize: "20px" }}>{time}</div>
        <div className="date-display">{date}</div>
      </div>

      {/* Navigation - MAIN FOCUS */}
      <nav className="navigation" style={{ flex: 1, padding: "8px" }}>
        <div style={{ fontSize: "10px", fontWeight: "600", color: "var(--text-tertiary)", padding: "8px 12px", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px" }}>Navigation</div>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`nav-link ${current === item.id ? "active" : ""}`}
            style={{ marginBottom: "4px" }}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="alert-counter">{unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Status Card - Compact */}
      <div className="status-card-modern" style={{ margin: "8px", padding: "12px" }}>
        <div className="card-header">
          <span className="card-title">Status</span>
          <div className="status-badge" style={{ fontSize: "9px", padding: "2px 6px" }}>
            <div className="status-dot" style={{ width: "4px", height: "4px" }}></div>
            OK
          </div>
        </div>
        <div className="card-stats" style={{ gap: "6px" }}>
          <div className="stat-row" style={{ fontSize: "11px" }}>
            <span className="stat-label">Latency</span>
            <span className="stat-value">{latency || "—"}ms</span>
          </div>
          <div className="stat-row" style={{ fontSize: "11px" }}>
            <span className="stat-label">Tasks</span>
            <span className="stat-value">{agentCtx?.tasks || 0}</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="connection-status">
          <div className={`connection-indicator ${online ? "online" : "offline"}`}></div>
          <span className="connection-text" style={{ fontSize: "10px" }}>
            {online ? "Connected" : "Offline"}
          </span>
        </div>
      </div>
    </aside>
  );
}
