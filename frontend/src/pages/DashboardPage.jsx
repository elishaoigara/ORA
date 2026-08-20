import { useState, useEffect, useCallback, useRef } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getPersonalContext, getActions,
  approveAction, rejectAction, executeAction,
} from "../api";

const PRI_COLOR = { high: "#ff4444", medium: "#ff9900", low: "#4488ff" };
const SEV_COLOR = { critical: "#ff4444", high: "#ff6644", medium: "#ff9900", low: "#ffcc00", info: "#4488ff" };

function fmtTs(ts) {
  if (!ts) return "";
  try { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
}

function BarRow({ label, pct, color }) {
  const v = Math.min(Math.max(Number(pct) || 0, 0), 100);
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="bar-pct" style={{ color }}>{Math.round(v)}%</span>
    </div>
  );
}

function MetricCard({ label, value, sub, accent }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: accent } : {}}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

function GoalBar({ goal }) {
  const pct = goal.progress || 0;
  const bar = "█".repeat(Math.floor(pct / 10)) + "░".repeat(10 - Math.floor(pct / 10));
  const overdue = goal.due_at && new Date(goal.due_at) < new Date();
  return (
    <div className="goal-row">
      <div className="goal-text" title={goal.goal}>{goal.goal}</div>
      <div className="goal-bar-row">
        <span className="goal-bar-mono">{bar}</span>
        <span className="goal-pct" style={overdue ? { color: "#ff4444" } : {}}>{pct}%{overdue ? " ⚠" : ""}</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [status,  setStatus]  = useState(null);
  const [alerts,  setAlerts]  = useState([]);
  const [tasks,   setTasks]   = useState([]);
  const [theNum,  setTheNum]  = useState(null);
  const [spend,   setSpend]   = useState(null);
  const [goals,   setGoals]   = useState([]);
  const [context, setContext] = useState(null);
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const loadAll = useCallback(async () => {
    try {
      const [st, al, tk, tn, sp, gl, cx, ac] = await Promise.allSettled([
        getStatus(), getAlerts(5), getTasks(), getTheNumber(), getMpesaSummary(), getGoals("active"),
        getPersonalContext(), getActions("proposed", 5),
      ]);
      if (!mounted.current) return;
      if (st.status === "fulfilled") setStatus(st.value);
      if (al.status === "fulfilled") setAlerts(Array.isArray(al.value) ? al.value : []);
      if (tk.status === "fulfilled") setTasks(Array.isArray(tk.value) ? tk.value : []);
      if (tn.status === "fulfilled") setTheNum(tn.value);
      if (sp.status === "fulfilled") setSpend(sp.value);
      if (gl.status === "fulfilled") setGoals(Array.isArray(gl.value) ? gl.value.slice(0, 3) : []);
      if (cx.status === "fulfilled") setContext(cx.value);
      if (ac.status === "fulfilled") setActions(Array.isArray(ac.value) ? ac.value : []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    mounted.current = true;
    loadAll();
    const id = setInterval(loadAll, 60000);
    return () => { mounted.current = false; clearInterval(id); };
  }, [loadAll]);

  const cpu = status?.cpu ?? 0;
  const ram = status?.ram ?? 0;
  const unread = alerts.filter(a => !a.acknowledged).length;
  const todaySpend = spend?.today ?? null;
  const avgSpend = spend?.average_daily ?? null;

  const theNumOk = theNum && theNum.status !== "empty" && theNum.title;

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">DASHBOARD</div>
          <div className="page-subtitle">SYSTEM OVERVIEW</div>
        </div>
        <button className="btn" onClick={loadAll} title="Refresh">↺ REFRESH</button>
      </div>

      {/* PERSONAL CONTEXT */}
      {context && (
        <div className="card" style={{ borderColor: "rgba(0,255,157,0.35)" }}>
          <div className="card-header">
            <span className="card-title">ORA FOCUS</span>
            <span className="card-badge">{String(context.state || "ready").toUpperCase()}</span>
          </div>
          <div className="card-body">
            <div className="task-title">{context.focus || "No priority selected yet"}</div>
            <div className="text-dimmer mono text-xs" style={{ marginTop: 8 }}>
              {context.summary?.pending_tasks || 0} tasks · {context.summary?.calendar_events || 0} events · {context.summary?.unread_emails || 0} unread emails
            </div>
          </div>
        </div>
      )}

      {/* APPROVAL QUEUE */}
      {actions.length > 0 && (
        <div className="card" style={{ borderColor: "rgba(255,153,0,0.45)" }}>
          <div className="card-header">
            <span className="card-title">ACTION APPROVALS</span>
            <span className="card-badge">{actions.length}</span>
          </div>
          <div className="card-body">
            {actions.map(action => (
              <div key={action.id} className="task-row" style={{ alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div className="task-title">{action.title}</div>
                  <div className="text-dimmer mono text-xs">{action.risk} · {action.source} · ID {action.id}</div>
                  {action.description && <div className="text-dimmer text-xs" style={{ marginTop: 4 }}>{action.description}</div>}
                  {action.expires_at && <div className="text-dimmer mono text-xs" style={{ marginTop: 4 }}>EXPIRES {action.expires_at}</div>}
                </div>
                <button className="btn btn-green" onClick={async () => {
                  const approved = await approveAction(action.id);
                  if (approved?.status === "approved") await executeAction(action.id);
                  loadAll();
                }}>APPROVE & EXECUTE</button>
                <button className="btn btn-red" onClick={async () => { await rejectAction(action.id); loadAll(); }}>REJECT</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* THE NUMBER */}
      {theNumOk && (
        <div className={`the-number ${theNum.overdue ? "overdue" : ""}`}>
          <div className="the-number-label">THE NUMBER</div>
          <div className="the-number-title">{theNum.title}</div>
          <div className="the-number-meta">
            <span className="pri-badge" style={{ color: PRI_COLOR[theNum.priority] || "#fff" }}>
              {theNum.priority?.toUpperCase()}
            </span>
            {theNum.reason && <span className="reason-text">{theNum.reason}</span>}
            {theNum.overdue && <span className="overdue-tag">OVERDUE</span>}
          </div>
        </div>
      )}

      {/* System health */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">SYSTEM</span>
          {status && <span className="card-badge">{status.status?.toUpperCase() || "OK"}</span>}
        </div>
        <div className="card-body">
          <BarRow label="CPU" pct={cpu} color={cpu > 80 ? "#ff4444" : cpu > 50 ? "#ff9900" : "#00ff9d"} />
          <BarRow label="RAM" pct={ram} color={ram > 85 ? "#ff4444" : ram > 65 ? "#ff9900" : "#00ff9d"} />
        </div>
      </div>

      {/* Metrics */}
      <div className="metrics-row">
        <MetricCard
          label="TASKS"
          value={tasks.length}
          sub="pending"
          accent={tasks.length > 5 ? "#ff9900" : "#00ff9d"}
        />
        <MetricCard
          label="ALERTS"
          value={unread}
          sub="unread"
          accent={unread > 0 ? "#ff4444" : "#00ff9d"}
        />
        {todaySpend !== null && (
          <MetricCard
            label="SPEND"
            value={`${(todaySpend / 1000).toFixed(1)}K`}
            sub={avgSpend ? `avg ${(avgSpend / 1000).toFixed(1)}K` : "today"}
            accent={avgSpend && todaySpend > avgSpend * 1.5 ? "#ff4444" : "#00ff9d"}
          />
        )}
      </div>

      {/* Goals */}
      {goals.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">GOALS</span>
            <span className="card-badge">{goals.length}</span>
          </div>
          <div className="card-body">
            {goals.map(g => <GoalBar key={g.id} goal={g} />)}
          </div>
        </div>
      )}

      {/* Pending tasks */}
      {tasks.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">PENDING TASKS</span>
            <span className="card-badge">{tasks.length}</span>
          </div>
          <div className="card-body">
            {tasks.slice(0, 5).map(t => (
              <div key={t.id} className="task-row">
                <div className="task-dot" style={{ background: PRI_COLOR[t.priority] || "#555" }} />
                <span className="task-title">{t.title}</span>
                {t.due_at && <span className="task-due">{t.due_at.slice(5, 10)}</span>}
              </div>
            ))}
            {tasks.length > 5 && (
              <div className="text-dimmer mono text-xs" style={{ marginTop: 8 }}>+{tasks.length - 5} more</div>
            )}
          </div>
        </div>
      )}

      {/* Unread alerts */}
      {unread > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">ALERTS</span>
            <span className="card-badge" style={{ color: "#ff4444" }}>{unread}</span>
          </div>
          <div className="card-body">
            {alerts.filter(a => !a.acknowledged).slice(0, 4).map(a => (
              <div key={a.id} className="task-row">
                <div className="task-dot" style={{ background: SEV_COLOR[a.severity] || "#ff9900" }} />
                <span className="task-title">{a.message}</span>
                <span className="task-due">{fmtTs(a.timestamp)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && tasks.length === 0 && (
        <div className="empty-state">
          <div className="spinner" />
          <div className="empty-body" style={{ marginTop: 12 }}>LOADING...</div>
        </div>
      )}
    </div>
  );
}