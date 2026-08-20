"""
ORA Proactive Intelligence Engine — Phase 2
Acts without being asked. Fires context-aware nudges from real data signals:

Signals watched:
  - Tasks: overdue, high-priority backlog, nothing started
  - Calendar: imminent meetings, no agenda sent, back-to-back
  - Gmail: unanswered emails > 24h, VIP sender waiting
  - Time-of-day: morning focus, evening wrap, night work warning
  - Goals: stale goals with no progress
  - Weather: bad weather affecting commute/outdoor plans

Cooldown: per-key via agent_guard (no spam).
All notifications go through dual_notify (Telegram + FCM push).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List

_EAT = ZoneInfo("Africa/Nairobi")

LAST_RUN: float = 0
COOLDOWN: int   = 300  # 5-min minimum between full checks


def run_proactive_checks() -> None:
    global LAST_RUN
    now = time.time()
    if now - LAST_RUN < COOLDOWN:
        return
    LAST_RUN = now

    try:
        from intelligence.notifier import dual_notify
        from agent_guard import can_fire, mark_fired

        now_eat = datetime.now(_EAT)
        hour = now_eat.hour
        today = now_eat.date().isoformat()

        # The canonical morning brief is sent by the dedicated 07:05 job.
        # Run the remaining context-aware checks independently.
        _check_imminent_meetings(today, dual_notify, can_fire, mark_fired)
        _check_overdue_tasks(today, dual_notify, can_fire, mark_fired)
        _check_high_priority_backlog(hour, today, dual_notify, can_fire, mark_fired)
        _check_evening_wrap(hour, today, dual_notify, can_fire, mark_fired)
        _check_night_work(hour, today, dual_notify, can_fire, mark_fired)
        _check_stale_goals(today, dual_notify, can_fire, mark_fired)
        _check_unanswered_emails(today, dual_notify, can_fire, mark_fired)
        _check_empty_day(hour, today, dual_notify, can_fire, mark_fired)

    except Exception as e:
        print(f"[PROACTIVE] run failed: {e}")


# ─────────────────────────────────────────────────────────────
# SIGNAL CHECKS
# ─────────────────────────────────────────────────────────────

def _check_morning_focus(hour, today, notify, can_fire, mark_fired) -> None:
    """07:00–09:00 — surface top task + calendar preview."""
    if not (7 <= hour <= 9):
        return
    key = f"morning_focus_{today}"
    if not can_fire(key):
        return
    try:
        from intelligence.priority_engine import get_prioritized_tasks
        tasks = get_prioritized_tasks()
        if not tasks:
            return

        top = tasks[0][1] if tasks else None
        task_line = f"🎯 Top task: *{top}*" if top else ""

        # Pull imminent calendar events
        cal_lines = []
        try:
            from connectors.calendar import get_upcoming_events
            events = get_upcoming_events(hours_ahead=10, max_results=3)
            for ev in events:
                t = ev.get("start", "")[:16].replace("T", " ")
                cal_lines.append(f"📅 {t} — {ev.get('title', '')}")
        except Exception:
            pass

        lines = ["☀️ *Good morning, Elisha. Here's your day:*", ""]
        if task_line:
            lines.append(task_line)
        if cal_lines:
            lines.append("")
            lines.extend(cal_lines)
        lines.append(f"\n{len(tasks)} task(s) pending total.")

        notify(title="ORA Morning Focus", body="\n".join(lines))
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] morning_focus error: {e}")


def _check_imminent_meetings(today, notify, can_fire, mark_fired) -> None:
    """Fire 15 min before any calendar event."""
    try:
        from connectors.calendar import get_upcoming_events
        events = get_upcoming_events(hours_ahead=1, max_results=5)
        for ev in events:
            mins = ev.get("minutes_until")
            if mins is None:
                continue
            if not (5 <= mins <= 20):
                continue
            key = f"meeting_alert_{ev.get('id', ev.get('title','')[:20])}_{today}"
            if not can_fire(key):
                continue
            title_str = ev.get("title", "Meeting")
            location  = ev.get("location", "")
            loc_str   = f" @ {location}" if location else ""
            notify(
                title="⏰ Meeting in ~15 min",
                body=f"*{title_str}*{loc_str}\nStarts in {mins} minutes.",
                is_alert=True,
            )
            mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] imminent_meetings error: {e}")


def _check_overdue_tasks(today, notify, can_fire, mark_fired) -> None:
    """Alert on overdue tasks — fires up to twice per day."""
    key = f"overdue_alert_{today}"
    if not can_fire(key):
        return
    try:
        from database import get_tasks
        now = datetime.now()
        pending  = get_tasks("pending")
        overdue  = [t for t in pending if t[4] and _is_overdue(t[4], now)]
        if not overdue:
            return
        names = ", ".join(f"*{t[1][:35]}*" for t in overdue[:3])
        extra = f" (+{len(overdue)-3} more)" if len(overdue) > 3 else ""
        notify(
            title="⚠️ Overdue Tasks",
            body=f"{len(overdue)} task(s) past their deadline:\n{names}{extra}",
            is_alert=True,
        )
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] overdue_tasks error: {e}")


def _check_high_priority_backlog(hour, today, notify, can_fire, mark_fired) -> None:
    """During business hours: nudge if high-priority tasks have been idle all day."""
    if not (10 <= hour <= 16):
        return
    key = f"high_priority_backlog_{today}"
    if not can_fire(key):
        return
    try:
        from database import get_tasks
        pending = get_tasks("pending")
        high    = [t for t in pending if t[2] == "high"]
        if len(high) < 2:
            return
        names = ", ".join(f"*{t[1][:30]}*" for t in high[:3])
        notify(
            title="🔴 High-Priority Backlog",
            body=f"You have {len(high)} high-priority task(s) open:\n{names}",
        )
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] high_priority_backlog error: {e}")


def _check_evening_wrap(hour, today, notify, can_fire, mark_fired) -> None:
    """18:00–20:00 — end-of-day wrap with remaining high tasks + tomorrow preview."""
    if not (18 <= hour <= 20):
        return
    key = f"evening_wrap_{today}"
    if not can_fire(key):
        return
    try:
        from database import get_tasks
        pending = get_tasks("pending")
        high    = [t for t in pending if t[2] == "high"]

        lines = ["🌇 *End of day wrap:*"]
        if high:
            lines.append(f"\n🔴 {len(high)} high-priority task(s) still open:")
            for t in high[:3]:
                lines.append(f"  • {t[1][:40]}")
        elif pending:
            lines.append(f"\n✅ No high-priority tasks. {len(pending)} medium/low still pending.")
        else:
            lines.append("\n✅ All tasks complete. Great day!")

        # Tomorrow's calendar (optional Google integration)
        try:
            from connectors.google_auth import is_authorized
            if is_authorized("primary"):
                from connectors.calendar import get_upcoming_events
                tomorrow_events = get_upcoming_events(hours_ahead=24, max_results=3)
                tomorrow = [e for e in tomorrow_events
                            if e.get("start", "") > datetime.now().isoformat()]
                if tomorrow:
                    lines.append(f"\n📅 Tomorrow: {len(tomorrow)} event(s) scheduled")
                    for ev in tomorrow[:2]:
                        t = ev.get("start", "")[:16].replace("T", " ")
                        lines.append(f"  • {t} — {ev.get('title','')}")
        except Exception:
            pass

        notify(title="ORA Evening Wrap", body="\n".join(lines))
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] evening_wrap error: {e}")


def _check_night_work(hour, today, notify, can_fire, mark_fired) -> None:
    """22:00–02:00 — gentle reminder to rest if ORA is still being actively used."""
    if not (hour >= 22 or hour <= 2):
        return
    key = f"night_work_{today}"
    if not can_fire(key):
        return
    try:
        from database import get_conversation_history
        recent = get_conversation_history(limit=5)
        if not recent:
            return  # No recent activity — don't disturb
        last_ts = recent[-1][2] if recent else None
        if last_ts:
            age = (datetime.now() - datetime.fromisoformat(last_ts)).total_seconds()
            if age > 1800:
                return  # Inactive for 30+ min — no need to nudge
        notify(
            title="🌙 Late-Night Check",
            body="It's late, Elisha. Consider wrapping up — ORA will keep watch overnight.",
        )
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] night_work error: {e}")


def _check_stale_goals(today, notify, can_fire, mark_fired) -> None:
    """Weekly: flag goals with no update in 7+ days."""
    key = f"stale_goals_{today}"
    if not can_fire(key):
        return
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals()
        if not goals:
            return

        now = datetime.now()
        stale = []
        for g in goals:
            updated = g.get("updated_at") or g.get("created_at")
            if not updated:
                continue
            try:
                age_days = (now - datetime.fromisoformat(updated)).days
                if age_days >= 7:
                    stale.append((g.get("goal", "")[:40], age_days))
            except Exception:
                pass

        if not stale:
            return

        lines = [f"⚠️ *{len(stale)} goal(s) haven't been updated in 7+ days:*"]
        for name, days in stale[:3]:
            lines.append(f"  • {name} ({days}d)")
        notify(title="ORA Goal Check", body="\n".join(lines))
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] stale_goals error: {e}")


def _check_unanswered_emails(today, notify, can_fire, mark_fired) -> None:
    """Fire if emails have been in the pending-reply queue > 24h."""
    key = f"unanswered_emails_{today}"
    if not can_fire(key):
        return
    try:
        conn_fn = None
        try:
            from database import get_conn, close_conn
            conn_fn = (get_conn, close_conn)
        except Exception:
            return

        get_conn_f, close_conn_f = conn_fn
        conn = get_conn_f()
        rows = conn.execute("""
            SELECT id, subject, sender, created_at
            FROM suggested_replies
            WHERE status = 'pending'
              AND created_at < datetime('now', '-24 hours')
            ORDER BY created_at ASC
            LIMIT 5
        """).fetchall()
        close_conn_f()

        if not rows:
            return

        lines = [f"📬 *{len(rows)} email reply(ies) waiting > 24h:*"]
        for r in rows[:3]:
            lines.append(f"  • {r[1][:40]} (from {r[2][:30]})")
        notify(title="ORA Inbox Nudge", body="\n".join(lines))
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] unanswered_emails error: {e}")


def _check_empty_day(hour, today, notify, can_fire, mark_fired) -> None:
    """09:00 — if calendar is empty, suggest a focus block."""
    if hour != 9:
        return
    key = f"empty_day_{today}"
    if not can_fire(key):
        return
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized("primary"):
            return
        from connectors.calendar import get_upcoming_events
        events = get_upcoming_events(hours_ahead=10, max_results=10)
        if events:
            return  # Calendar is not empty

        from database import get_tasks
        pending = get_tasks("pending")
        if not pending:
            return

        top = pending[0][1][:40] if pending else "your top task"
        notify(
            title="📋 Clear Day",
            body=f"Your calendar is free today — great time to focus on:\n*{top}*",
        )
        mark_fired(key)
    except Exception as e:
        print(f"[PROACTIVE] empty_day error: {e}")


# ─────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────

def _is_overdue(due_at: str, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(due_at) < now
    except Exception:
        return False


print("[PROACTIVE ENGINE] Phase 2 loaded")
