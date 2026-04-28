import { useState, useEffect, useCallback } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api";

// Meter Component
function Meter({ label, value = 0, unit = "%" }) {
  const v = Math.min(Math.max(Number(value) || 0, 0), 100);
  const color = v > 85 ? "#ef4444" : v > 65 ? "#eab308" : "#22c55e";

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
    high: { bg: "#7f1d1d", color: "#ef4444" },
    medium: { bg: "#713f12", color: "#eab308" },
    low: { bg: "#14532d", color: "#22c55e" }
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
  const color = ratio >= 3 ? "#ef4444" : ratio >= 1.5 ? "#eab308" : "#22c55e";
  const bgColor = ratio >= 3 ? "#7f1d1d" : ratio >= 1.5 ? "#713f12" : "#14532d";

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
    <div className="goals-card">
      <div className="card-header">
        <span className="card-icon">🎯</span>
        <span className="card-title">Active Goals</span>
        <span className="card-badge">{goals.length}</span>
      </div>
      <div className="goals-list">
        {goals.slice(0, 4).map((g, i) => {
          const pct = g.progress || 0;
          const overdue = g.due_at && new Date(g.due_at) < new Date();
          const color = overdue ? "#ef4444" : pct >= 70 ? "#22c55e" : "#eab308";
          const bgColor = overdue ? "#7f1d1d" : pct >= 70 ? "#14532d" : "#713f12";

          return (
            <div key={i} className="goal-item">
              <div className="goal-title">{g.goal}</div>
              <div className="goal-progress-wrapper">
                <div className="goal-progress-bar">
                  <div className="goal-progress-fill" style={{ width: `${pct}%`, background: color }} />
                </div>
                <span className="goal-percentage">{pct}%</span>
              </div>
              <div className="goal-due" style={{ color: overdue ? "#ef4444" : "#6b7280" }}>
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
          <span className="metric-value" style={{ color: (ctx.overdue ?? 0) > 0 ? "#ef4444" : "#22c55e" }}>
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
          <div className="stat-icon">📋</div>
          <div className="stat-content">
            <div className="stat-number">{tasks.length}</div>
            <div className="stat-label">Pending Tasks</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">⚠️</div>
          <div className="stat-content">
            <div className="stat-number" style={{ color: activeAlerts.length > 0 ? "#ef4444" : "#22c55e" }}>
              {activeAlerts.length}
            </div>
            <div className="stat-label">Active Alerts</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🔌</div>
          <div className="stat-content">
            <div className="stat-number" style={{ color: isOnline ? "#22c55e" : "#ef4444" }}>
              {isOnline ? "Online" : "Offline"}
            </div>
            <div className="stat-label">System Status</div>
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
        <div className="dashboard-card">
          <div className="card-header">
            <span className="card-icon">⚠️</span>
            <span className="card-title">Alert Feed</span>
            {activeAlerts.length > 0 && (
              <button className="ack-all-btn" onClick={handleAckAll}>
                Acknowledge All
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
                <div key={a.id} className={`alert-item severity-${a.severity || 'info'}`}>
                  <div className="alert-content">
                    <div className="alert-message">{a.message}</div>
                    <div className="alert-meta">
                      <span className="alert-time">{a.timestamp?.slice(11, 19)}</span>
                      <span className="alert-rule">{a.rule_name}</span>
                    </div>
                  </div>
                  <button className="ack-btn" onClick={() => handleAck(a.id)}>
                    Acknowledge
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
                const priorityColor = t.priority === 'high' ? '#ef4444' : t.priority === 'medium' ? '#eab308' : '#22c55e';
                const priorityBg = t.priority === 'high' ? '#7f1d1d' : t.priority === 'medium' ? '#713f12' : '#14532d';
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