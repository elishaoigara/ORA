import { useState, useEffect, useCallback } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api";

function Meter({ label, value = 0, unit = "%" }) {
  const v = Math.min(Math.max(Number(value) || 0, 0), 100);
  const color = v > 85 ? "var(--red)" : v > 65 ? "var(--amber)" : "var(--green)";

  return (
    <div className="meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-value" style={{ color }}>
          {v}{unit}
        </span>
      </div>
      <div className="meter-track">
        <div 
          className="meter-bar" 
          style={{ width: `${v}%`, background: color }} 
        />
      </div>
    </div>
  );
}

function TheNumber({ task }) {
  if (!task) return null;

  return (
    <div className="the-number-card">
      <div className="the-number-header">
        ◈ TODAY'S TOP PRIORITY
      </div>
      <div className="the-number-title">{task.title}</div>
      
      <div className="the-number-meta">
        <span 
          className={`priority-badge ${task.priority || 'medium'}`}
        >
          {(task.priority || 'MEDIUM').toUpperCase()}
        </span>
        
        {task.overdue && <span className="overdue-badge">⚠ OVERDUE</span>}
        
        {task.reason && <span className="the-number-reason">{task.reason}</span>}
        
        {task.score && (
          <span className="score">
            SCORE <span className="score-value">{task.score}</span>
          </span>
        )}
      </div>
    </div>
  );
}

function MpesaWidget({ summary }) {
  if (!summary || summary.status === "error") return null;

  const today = summary.today || { total: 0, transactions: 0 };
  const avg = summary.average_daily || 0;
  const ratio = avg > 0 ? today.total / avg : 0;
  const color = ratio >= 3 ? "var(--red)" : ratio >= 1.5 ? "var(--amber)" : "var(--green)";

  return (
    <div className="card mpesa-card">
      <div className="card-title">// M-Pesa Financial Snapshot</div>
      
      <div className="mpesa-main">
        <div>
          <div className="mpesa-amount" style={{ color }}>
            KES {(today.total || 0).toLocaleString()}
          </div>
          <div className="mpesa-sub">
            spent today • {today.transactions} transactions
          </div>
        </div>

        <div className="mpesa-avg">
          <div className="mpesa-avg-label">Daily Average</div>
          <div className="mpesa-avg-value">KES {avg.toLocaleString()}</div>
        </div>
      </div>

      <div className="mpesa-bar-container">
        <div 
          className="mpesa-bar" 
          style={{ 
            width: `${Math.min(ratio * 40, 100)}%`, 
            background: color 
          }} 
        />
      </div>

      {ratio >= 2.5 && (
        <div className="mpesa-alert">
          ⚠ Spending is {ratio.toFixed(1)}× above daily average
        </div>
      )}
    </div>
  );
}

function CalendarWidget({ events }) {
  if (!events?.length) {
    return (
      <div className="card">
        <div className="card-title">// Today's Calendar</div>
        <div className="empty">
          <div className="empty-icon">📅</div>
          <span>No events today</span>
          <a 
            href="/api/auth/google" 
            target="_blank" 
            rel="noreferrer"
            className="connect-link"
          >
            Connect Google Calendar →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-title">
        // Today's Calendar • {events.length} event{events.length > 1 ? "s" : ""}
      </div>
      {events.slice(0, 5).map((e, i) => {
        const isImminent = e.minutes_until != null && 
                          e.minutes_until >= 0 && 
                          e.minutes_until <= 30;
        
        return (
          <div key={i} className={`calendar-event ${isImminent ? 'imminent' : ''}`}>
            <div className="cal-time">
              {e.all_day ? "ALL DAY" : 
               e.minutes_until != null ? 
                 (e.minutes_until <= 0 ? "NOW" : `${e.minutes_until}m`) : 
                 e.start?.slice(11, 16) || "—"}
            </div>
            <div className="cal-content">
              <div className="cal-title">{e.title}</div>
              {e.location && <div className="cal-location">📍 {e.location}</div>}
              {isImminent && <div className="cal-imminent">● STARTING SOON</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function GoalsWidget({ goals }) {
  if (!goals?.length) return null;

  return (
    <div className="card">
      <div className="card-title">// Active Goals ({goals.length})</div>
      {goals.slice(0, 4).map((g, i) => {
        const pct = g.progress || 0;
        const overdue = g.due_at && new Date(g.due_at) < new Date();
        const color = overdue ? "var(--red)" : pct >= 70 ? "var(--green)" : "var(--amber)";

        return (
          <div key={i} className="goal-row">
            <div className="goal-title">{g.goal}</div>
            <div className="goal-bar-track">
              <div 
                className="goal-bar-fill" 
                style={{ width: `${pct}%`, background: color }} 
              />
            </div>
            <div className="goal-meta">
              <span>{pct}% complete</span>
              <span style={{ color: overdue ? "var(--red)" : "var(--text3)" }}>
                {overdue ? "⚠ OVERDUE" : g.due_at ? `due ${g.due_at.slice(0,10)}` : "no deadline"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AgentRibbon({ ctx }) {
  if (!ctx) return null;

  return (
    <div className="agent-ribbon">
      <div className="agent-ribbon-item">
        <div className="agent-dot" />
        <span>AGENT CYCLE</span>
      </div>
      <div className="agent-ribbon-item">
        TASKS <span className="agent-ribbon-val">{ctx.tasks ?? 0}</span>
      </div>
      <div className="agent-ribbon-item">
        OVERDUE <span 
          className="agent-ribbon-val" 
          style={{ color: (ctx.overdue ?? 0) > 0 ? "var(--red)" : "var(--green)" }}
        >
          {ctx.overdue ?? 0}
        </span>
      </div>
      <div className="agent-ribbon-item">
        GOALS <span className="agent-ribbon-val">{ctx.goals ?? 0}</span>
      </div>
      <div className="agent-ribbon-item">
        CALENDAR <span className="agent-ribbon-val" style={{ color: "var(--cyan)" }}>
          {ctx.calendar_today ?? 0}
        </span>
      </div>
      {ctx.pending_actions?.length > 0 && (
        <div className="agent-ribbon-item pending-actions">
          {ctx.pending_actions.length} pending action{ctx.pending_actions.length > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// MAIN DASHBOARD COMPONENT
// ─────────────────────────────────────────────────────────────

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
      getStatus(),
      getAlerts(10),
      getTasks(),
      getTheNumber(),
      getMpesaSummary(),
      getGoals(),
      getCalendarToday(),
      getAgentStatus(),
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
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Command Center</div>
        <div className="page-sub">Real-time intelligence • Nairobi, KE • EAT</div>
      </div>

      <AgentRibbon ctx={agentCtx} />

      {/* Quick Stats Row */}
      <div className="grid-3" style={{ marginBottom: "1.25rem" }}>
        <div className="stat-box">
          <div className="stat-num">{tasks.length}</div>
          <div className="stat-label">Pending Tasks</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: activeAlerts.length > 0 ? "var(--red)" : "var(--green)" }}>
            {activeAlerts.length}
          </div>
          <div className="stat-label">Active Alerts</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: isOnline ? "var(--green)" : "var(--red)" }}>
            {isOnline ? "ONLINE" : "OFFLINE"}
          </div>
          <div className="stat-label">System Status</div>
        </div>
      </div>

      {/* The Number */}
      <TheNumber task={theNumber} />

      <div className="grid-2">
        {/* System Monitor */}
        <div className="card">
          <div className="card-title">// System Monitor</div>
          {isOnline ? (
            <>
              <Meter label="CPU LOAD" value={status.cpu} />
              <Meter label="RAM USED" value={status.ram} />
              <div className="sync-time">
                SYNC: {status.time ? new Date(status.time).toLocaleTimeString() : "—"}
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="empty-icon">⌛</div>
              {status === null ? "Connecting to ORA..." : "Backend unreachable"}
            </div>
          )}
        </div>

        {/* Alerts Feed */}
        <div className="card">
          <div className="card-header-with-action">
            <div className="card-title">// Alert Feed</div>
            {activeAlerts.length > 0 && (
              <button className="btn btn-ghost small" onClick={handleAckAll}>
                ACK ALL
              </button>
            )}
          </div>

          {activeAlerts.length === 0 ? (
            <div className="empty">
              <div className="empty-icon" style={{ color: "var(--green)" }}>◉</div>
              All systems nominal
            </div>
          ) : (
            activeAlerts.slice(0, 4).map(a => (
              <div key={a.id} className={`alert-row ${a.severity}`}>
                <div className="alert-header">
                  <div className="alert-severity">
                    {a.severity?.toUpperCase()}
                  </div>
                  <button 
                    className="btn btn-ghost tiny" 
                    onClick={() => handleAck(a.id)}
                  >
                    ACK
                  </button>
                </div>
                <div className="alert-msg">{a.message}</div>
                <div className="alert-time">
                  {a.timestamp?.slice(11, 19)} • {a.rule_name}
                </div>
              </div>
            ))
          )}
        </div>

        {/* M-Pesa */}
        <MpesaWidget summary={mpesa} />

        {/* Task Queue */}
        <div className="card">
          <div className="card-title">// Task Queue • {tasks.length} pending</div>
          {tasks.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">◆</div>
              Queue empty — Add tasks via chat or Telegram
            </div>
          ) : (
            tasks.slice(0, 5).map(t => (
              <div key={t.id} className="task-row">
                <div className="task-info">
                  <div className="task-title">{t.title}</div>
                  <div className="task-meta">
                    #{t.id} • {t.created_at?.slice(0, 10)}
                    {t.due_at && ` • DUE ${t.due_at.slice(11, 16)}`}
                  </div>
                </div>
                <div className={`priority-badge ${t.priority || 'medium'}`}>
                  {(t.priority || 'MEDIUM').toUpperCase()}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Calendar */}
        <CalendarWidget events={calendar} />

        {/* Goals */}
        <GoalsWidget goals={goals} />
      </div>
    </div>
  );
}