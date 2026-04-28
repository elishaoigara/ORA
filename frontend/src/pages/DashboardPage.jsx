import { useState, useEffect, useCallback } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api";

/* ───────────── Meter ───────────── */
function Meter({ label, value = 0, unit = "%" }) {
  const v = Math.min(Math.max(Number(value) || 0, 0), 100);
  const color = v > 85 ? "var(--red)" : v > 65 ? "var(--amber)" : "var(--green)";

  return (
    <div className="meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-val" style={{ color }}>{v}{unit}</span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  );
}

/* ───────────── Priority ───────────── */
function TheNumber({ task }) {
  if (!task) return null;

  return (
    <div className="priority-card">
      <div className="priority-header">
        <span className="priority-eyebrow">Today's Priority</span>
      </div>

      <div className="priority-title">{task.title}</div>

      <div className="priority-footer">
        <span className={`badge badge-${task.priority || "medium"}`}>
          {(task.priority || "medium").toUpperCase()}
        </span>

        {task.overdue && (
          <span className="badge badge-overdue">OVERDUE</span>
        )}
      </div>

      {task.reason && (
        <div className="priority-reason">{task.reason}</div>
      )}
    </div>
  );
}

/* ───────────── M-Pesa ───────────── */
function MpesaWidget({ summary }) {
  if (!summary || summary.status === "error") return null;

  const today = summary.today || { total: 0, transactions: 0 };
  const avg = summary.average_daily || 0;
  const ratio = avg > 0 ? today.total / avg : 0;

  const color =
    ratio >= 3 ? "var(--red)" :
    ratio >= 1.5 ? "var(--amber)" :
    "var(--green)";

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-icon">💳</span>
        <span className="card-title">M-PESA Insights</span>
      </div>

      <div className="finance-main">
        <div className="finance-amount" style={{ color }}>
          KES {today.total.toLocaleString()}
        </div>
        <div className="finance-sub">
          {today.transactions} transactions today
        </div>
      </div>

      <div className="meter-track">
        <div
          className="meter-fill"
          style={{ width: `${Math.min(ratio * 40, 100)}%`, background: color }}
        />
      </div>

      {ratio >= 2.5 && (
        <div className="finance-warn badge badge-high">
          ⚠ Spending above average
        </div>
      )}
    </div>
  );
}

/* ───────────── Calendar ───────────── */
function CalendarWidget({ events }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-icon">📅</span>
        <span className="card-title">Today's Schedule</span>
        <span className="card-badge">{events?.length || 0}</span>
      </div>

      {!events?.length ? (
        <div className="empty-center">
          <div className="empty-icon">📆</div>
          <div className="empty-text">No events scheduled</div>
        </div>
      ) : (
        <div className="events-feed">
          {events.slice(0, 5).map((e, i) => (
            <div key={i} className="event-row">
              <div className="event-time-col">
                {e.all_day ? "ALL DAY" : e.start?.slice(11, 16) || "--"}
              </div>
              <div className="event-name">
                {e.title}
                {e.location && (
                  <div className="event-loc">📍 {e.location}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────── Goals ───────────── */
function GoalsWidget({ goals }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-icon">🎯</span>
        <span className="card-title">Active Goals</span>
        <span className="card-badge">{goals?.length || 0}</span>
      </div>

      <div className="goals-feed">
        {goals?.slice(0, 4).map((g, i) => {
          const pct = g.progress || 0;
          const color = pct >= 70 ? "var(--green)" : "var(--amber)";

          return (
            <div key={i} className="goal-row">
              <div className="goal-name">{g.goal}</div>

              <div className="goal-bar-row">
                <div className="goal-bar-track">
                  <div
                    className="goal-bar-fill"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
                <span className="goal-pct">{pct}%</span>
              </div>

              <div className="goal-due">
                {g.due_at ? g.due_at.slice(0, 10) : "No deadline"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ───────────── Agent ───────────── */
function AgentRibbon({ ctx }) {
  if (!ctx) return null;

  return (
    <div className="agent-ribbon">
      <div className="ribbon-indicator">
        <div className="pulse-dot" />
        <span className="ribbon-label">Agent Online</span>
      </div>

      <div className="ribbon-stats">
        <div className="ribbon-stat">
          <div className="ribbon-stat-val">{ctx.tasks || 0}</div>
          <div className="ribbon-stat-label">Tasks</div>
        </div>

        <div className="ribbon-stat">
          <div className="ribbon-stat-val">{ctx.overdue || 0}</div>
          <div className="ribbon-stat-label">Overdue</div>
        </div>

        <div className="ribbon-stat">
          <div className="ribbon-stat-val">{ctx.goals || 0}</div>
          <div className="ribbon-stat-label">Goals</div>
        </div>
      </div>
    </div>
  );
}

/* ───────────── MAIN ───────────── */
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

  const activeAlerts = alerts.filter(a => !a.acknowledged);

  useEffect(() => {
    fetchAll();
    const i = setInterval(fetchAll, 15000);
    return () => clearInterval(i);
  }, [fetchAll]);

  return (
    <div className="page">

      {/* Header */}
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Command Center</h1>
          <div className="dash-sub">Real-time intelligence</div>
        </div>

        <div className="dash-clock">
          {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* Agent */}
      <AgentRibbon ctx={agentCtx} />

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">📋</div>
          <div>
            <div className="stat-number">{tasks.length}</div>
            <div className="stat-label">Tasks</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">⚠️</div>
          <div>
            <div className="stat-number">{activeAlerts.length}</div>
            <div className="stat-label">Alerts</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">⚡</div>
          <div>
            <div className="stat-number">
              {status ? "Online" : "Offline"}
            </div>
            <div className="stat-label">System</div>
          </div>
        </div>
      </div>

      {/* Priority */}
      <TheNumber task={theNumber} />

      {/* Grid */}
      <div className="dashboard-grid">

        <div className="card">
          <div className="card-header">
            <span className="card-icon">⚙️</span>
            <span className="card-title">System</span>
          </div>

          {status ? (
            <>
              <Meter label="CPU" value={status.cpu} />
              <Meter label="RAM" value={status.ram} />
            </>
          ) : (
            <div className="empty-center">Offline</div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-icon">⚠️</span>
            <span className="card-title">Alerts</span>
          </div>

          <div className="alerts-feed">
            {activeAlerts.slice(0, 4).map(a => (
              <div key={a.id} className="alert-row">
                <div className="alert-msg">{a.message}</div>
              </div>
            ))}
          </div>
        </div>

        <MpesaWidget summary={mpesa} />
        <CalendarWidget events={calendar} />
        <GoalsWidget goals={goals} />

      </div>
    </div>
  );
}