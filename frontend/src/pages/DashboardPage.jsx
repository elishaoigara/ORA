import { useState, useEffect, useCallback } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api";

// Meter Component
function Meter({ label, value = 0, unit = "%" }) {
  const v = Math.min(Math.max(Number(value) || 0, 0), 100);
  const color = v > 85 ? "#ff006e" : v > 65 ? "#ffa500" : "#39ff14";

  return (
    <div className="modern-meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-value" style={{ color }}>{v}{unit}</span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  );
}

// The Number Component (Today's Priority)
function TheNumber({ task }) {
  if (!task) return null;

  const priorityColors = {
    high: { bg: "rgba(255, 0, 110, 0.2)", color: "#ff006e" },
    medium: { bg: "rgba(255, 165, 0, 0.2)", color: "#ffa500" },
    low: { bg: "rgba(57, 255, 20, 0.2)", color: "#39ff14" }
  };
  const priorityColor = priorityColors[task.priority || 'medium'];

  return (
    <div className="priority-card">
      <div className="priority-header">
        <span className="priority-icon">🎯</span>
        <span className="priority-label">Today's Priority</span>
      </div>
      <div className="priority-title">{task.title}</div>
      <div className="priority-footer">
        <span className="priority-badge-modern" style={{ background: priorityColor.bg, color: priorityColor.color }}>
          {(task.priority || 'MEDIUM').toUpperCase()}
        </span>
        {task.overdue && (
          <span className="overdue-badge-modern">
            ⚠ OVERDUE
          </span>
        )}
      </div>
      {task.reason && <div className="priority-reason">{task.reason}</div>}
    </div>
  );
}

// M-Pesa Widget
function MpesaWidget({ summary }) {
  if (!summary || summary.status === "error") return null;

  const today = summary.today || { total: 0, transactions: 0 };
  const avg = summary.average_daily || 0;
  const ratio = avg > 0 ? today.total / avg : 0;
  const color = ratio >= 3 ? "#ff006e" : ratio >= 1.5 ? "#ffa500" : "#39ff14";
  const bgColor = ratio >= 3 ? "rgba(255, 0, 110, 0.2)" : ratio >= 1.5 ? "rgba(255, 165, 0, 0.2)" : "rgba(57, 255, 20, 0.2)";

  return (
    <div className="finance-card">
      <div className="card-header">
        <span className="card-icon">💳</span>
        <span className="card-title">M-PESA Insights</span>
      </div>
      <div className="finance-stats">
        <div className="finance-main">
          <div className="finance-amount" style={{ color }}>
            KES {(today.total || 0).toLocaleString()}
          </div>
          <div className="finance-sub">spent today • {today.transactions} transactions</div>
        </div>
        <div className="finance-average">
          <div className="average-label">Daily Avg</div>
          <div className="average-value">KES {avg.toLocaleString()}</div>
        </div>
      </div>
      <div className="finance-progress">
        <div className="progress-bar-bg">
          <div className="progress-bar-fill" style={{ width: `${Math.min(ratio * 40, 100)}%`, background: color }} />
        </div>
      </div>
      {ratio >= 2.5 && (
        <div className="finance-alert" style={{ background: bgColor, borderLeftColor: color }}>
          ⚠ Spending {ratio.toFixed(1)}× above average
        </div>
      )}
    </div>
  );
}

// Calendar Widget
function CalendarWidget({ events }) {
  if (!events?.length) {
    return (
      <div className="calendar-card">
        <div className="card-header">
          <span className="card-icon">📅</span>
          <span className="card-title">Today's Schedule</span>
        </div>
        <div className="empty-state">
          <div className="empty-icon">📆</div>
          <div className="empty-text">No events scheduled</div>
          <a href="/api/auth/google" target="_blank" rel="noreferrer" className="connect-link">
            Connect Google Calendar →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="calendar-card">
      <div className="card-header">
        <span className="card-icon">📅</span>
        <span className="card-title">Today's Schedule</span>
        <span className="card-badge">{events.length} events</span>
      </div>
      <div className="events-list">
        {events.slice(0, 5).map((e, i) => (
          <div key={i} className="event-item">
            <div className="event-time">
              {e.all_day ? "ALL DAY" : 
               e.minutes_until != null ? 
                 (e.minutes_until <= 0 ? "NOW" : `${e.minutes_until}m`) : 
                 e.start?.slice(11, 16) || "—"}
            </div>
            <div className="event-details">
              <div className="event-title">{e.title}</div>
              {e.location && <div className="event-location">📍 {e.location}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Goals Widget
function GoalsWidget({ goals }) {
  if (!goals?.length) return null;

  return (
    <div className="goals-widget">
      <div className="card-header">
        <span className="card-icon">🎯</span>
        <span className="card-title">Active Goals</span>
        <span className="card-badge">{goals.length}</span>
      </div>
      <div className="goals-list">
        {goals.slice(0, 4).map((g, i) => {
          const pct = g.progress || 0;
          const overdue = g.due_at && new Date(g.due_at) < new Date();
          const color = overdue ? "#ff006e" : pct >= 70 ? "#39ff14" : "#ffa500";

          return (
            <div key={i} className="goal-item">
              <div className="goal-header">
                <div className="goal-title">{g.goal}</div>
                <span className="goal-progress-text">{pct}%</span>
              </div>
              <div className="goal-progress-bar">
                <div className="goal-progress-fill" style={{ width: `${pct}%`, background: color }} />
              </div>
              <div className="goal-due" style={{ color: overdue ? "#ff006e" : "#718096" }}>
                {overdue ? "⚠ OVERDUE" : g.due_at ? `Due ${g.due_at.slice(0,10)}` : "No deadline"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Agent Status Bar
function AgentRibbon({ ctx }) {
  if (!ctx) return null;

  return (
    <div className="agent-bar">
      <div className="agent-status">
        <div className="status-indicator active" />
        <span>Agent Online</span>
      </div>
      <div className="agent-metrics">
        <div className="metric">
          <span className="metric-label">Tasks</span>
          <span className="metric-value">{ctx.tasks ?? 0}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Overdue</span>
          <span className="metric-value" style={{ color: (ctx.overdue ?? 0) > 0 ? "#ff006e" : "#39ff14" }}>
            {ctx.overdue ?? 0}
          </span>
        </div>
        <div className="metric">
          <span className="metric-label">Goals</span>
          <span className="metric-value">{ctx.goals ?? 0}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Today</span>
          <span className="metric-value">{ctx.calendar_today ?? 0}</span>
        </div>
      </div>
    </div>
  );
}

// Main Dashboard
export default function DashboardPage() {
  const [status, setStatus] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [theNumber, setTheNumber] = useState(null);
  const [mpesa, setMpesa] = useState(null);
  const [goals, setGoals] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [agentCtx, setAgentCtx] = useState(null);

  const fetchAll = useCallback(async () => {
    const results = await Promise.allSettled([
      getStatus(), getAlerts(10), getTasks(), getTheNumber(),
      getMpesaSummary(), getGoals(), getCalendarToday(), getAgentStatus(),
    ]);

    const [s, a, t, n, m, g, c, ag] = results.map(r => 
      r.status === "fulfilled" ? r.value : null
    );

    if (s) setStatus(s);
    if (a) setAlerts(Array.isArray(a) ? a : []);
    if (t) setTasks(Array.isArray(t) ? t : []);
    if (n) setTheNumber(n);
    if (m) setMpesa(m);
    if (g) setGoals(Array.isArray(g) ? g : []);
    if (c) setCalendar(Array.isArray(c) ? c : []);
    if (ag) setAgentCtx(ag);
  }, []);

  const handleAck = async (id) => {
    await ackAlert(id).catch(() => {});
    fetchAll();
  };

  const handleAckAll = async () => {
    await ackAllAlerts().catch(() => {});
    fetchAll();
  };

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 15000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const activeAlerts = alerts.filter(a => !a.acknowledged);
  const isOnline = status && typeof status.cpu === "number";

  return (
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Command Center</h1>
          <p className="dashboard-subtitle">Real-time intelligence · Nairobi, KE</p>
        </div>
        <div className="header-time">
          {new Date().toLocaleTimeString("en-KE", { hour12: false })}
        </div>
      </div>

      {/* Agent Bar */}
      <AgentRibbon ctx={agentCtx} />

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Pending Tasks</div>
          <div className="stat-value">{tasks.length}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label">Active Alerts</div>
          <div className={`stat-value ${activeAlerts.length > 0 ? 'magenta' : 'lime'}`}>
            {activeAlerts.length}
          </div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">System Status</div>
          <div className={`stat-value ${isOnline ? 'lime' : 'magenta'}`}>
            {isOnline ? "ONLINE" : "OFFLINE"}
          </div>
        </div>
      </div>

      {/* Today's Priority */}
      <TheNumber task={theNumber} />

      {/* Main Grid */}
      <div className="dashboard-grid">
        {/* System Monitor */}
        <div className="dashboard-card">
          <div className="card-header">
            <span className="card-icon">⚙️</span>
            <span className="card-title">System Monitor</span>
          </div>
          {isOnline ? (
            <div className="system-content">
              <Meter label="CPU Usage" value={status.cpu} />
              <Meter label="Memory Usage" value={status.ram} />
              <div className="sync-info">
                <span className="sync-label">Last Sync</span>
                <span className="sync-time">{status.time ? new Date(status.time).toLocaleTimeString() : "—"}</span>
              </div>
            </div>
          ) : (
            <div className="offline-message">
              <div className="offline-icon">🔌</div>
              <div>Backend unreachable</div>
            </div>
          )}
        </div>

        {/* Alert Feed */}
        <div className="alert-feed">
          <div className="card-header">
            <span className="card-icon">⚠️</span>
            <span className="card-title">Alert Feed</span>
            {activeAlerts.length > 0 && (
              <button className="cyber-button" onClick={handleAckAll} style={{ padding: "4px 12px", fontSize: "11px" }}>
                Ack All
              </button>
            )}
          </div>
          {activeAlerts.length === 0 ? (
            <div className="empty-success">
              <span className="success-icon">✓</span>
              All systems nominal
            </div>
          ) : (
            <div className="alerts-list">
              {activeAlerts.slice(0, 4).map(a => (
                <div key={a.id} className={`alert-row alert-severity-${a.severity || 'info'}`}>
                  <div className={`alert-severity ${a.severity || 'info'}`}>
                    {(a.severity || 'INFO').toUpperCase()}
                  </div>
                  <div className="alert-content">
                    <div className="alert-title">{a.message}</div>
                    <div className="alert-meta">
                      <span className="alert-time">{a.timestamp?.slice(11, 19)}</span>
                      <span className="alert-rule">{a.rule_name}</span>
                    </div>
                  </div>
                  <button 
                    className="cyber-button" 
                    onClick={() => handleAck(a.id)}
                    style={{ padding: "4px 12px", fontSize: "11px", whiteSpace: "nowrap" }}
                  >
                    Ack
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* M-PESA Widget */}
        <MpesaWidget summary={mpesa} />

        {/* Task Queue */}
        <div className="dashboard-card">
          <div className="card-header">
            <span className="card-icon">📋</span>
            <span className="card-title">Task Queue</span>
            <span className="card-badge">{tasks.length} pending</span>
          </div>
          {tasks.length === 0 ? (
            <div className="empty-state-small">No pending tasks</div>
          ) : (
            <div className="tasks-list">
              {tasks.slice(0, 5).map(t => {
                const priorityColor = t.priority === 'high' ? '#ff006e' : t.priority === 'medium' ? '#ffa500' : '#39ff14';
                const priorityBg = t.priority === 'high' ? 'rgba(255, 0, 110, 0.2)' : t.priority === 'medium' ? 'rgba(255, 165, 0, 0.2)' : 'rgba(57, 255, 20, 0.2)';
                return (
                  <div key={t.id} className="task-item">
                    <div className="task-title">{t.title}</div>
                    <span className="task-priority" style={{ background: priorityBg, color: priorityColor }}>
                      {(t.priority || 'MED').toUpperCase()}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Calendar & Goals */}
        <CalendarWidget events={calendar} />
        <GoalsWidget goals={goals} />
      </div>
    </div>
  );
}

// Additional CSS classes needed
const dashboardGridStyles = `
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 20px;
  margin-top: 28px;
}

.dashboard-card {
  background: rgba(26, 31, 58, 0.8);
  border: 1px solid rgba(0, 240, 255, 0.2);
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.1);
}

.agent-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.1), rgba(179, 0, 255, 0.1));
  border: 1px solid rgba(0, 240, 255, 0.3);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 28px;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  color: var(--neon-cyan);
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--neon-lime);
  box-shadow: 0 0 10px var(--neon-lime);
  animation: pulse 2s infinite;
}

.agent-metrics {
  display: flex;
  gap: 32px;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.metric-label {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: var(--neon-cyan);
  text-shadow: 0 0 5px rgba(0, 240, 255, 0.3);
}

.system-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sync-info {
  display: flex;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 240, 255, 0.1);
}

.sync-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.sync-time {
  font-size: 11px;
  color: var(--neon-cyan);
  font-family: 'JetBrains Mono', monospace;
}

.offline-message {
  text-align: center;
  padding: 32px;
  color: var(--text-tertiary);
}

.offline-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-success {
  text-align: center;
  padding: 32px;
  color: var(--neon-lime);
}

.success-icon {
  font-size: 32px;
  margin-right: 8px;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: rgba(0, 240, 255, 0.05);
  border: 1px solid rgba(0, 240, 255, 0.1);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.task-item:hover {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.3);
}

.task-title {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.task-priority {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  border: 1px solid currentColor;
  border-color: currentColor;
  opacity: 0.7;
}

.empty-state-small {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.goals-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.goal-item {
  padding: 12px;
  background: rgba(57, 255, 20, 0.05);
  border: 1px solid rgba(57, 255, 20, 0.1);
  border-radius: 8px;
}

.goal-due {
  font-size: 10px;
  margin-top: 6px;
}

@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .agent-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .agent-metrics {
    width: 100%;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 12px;
  }
}
`;
