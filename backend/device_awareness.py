"""Consent-first awareness records for paired ORA Companion devices.

The phone may only submit an awareness event after the device-scoped credential
and the matching server-side consent record are both active. Named-zone events
store no raw coordinate history. Continuous location samples are stored only
while that separate consent is enabled and are pruned by the selected retention
window.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database import close_conn, get_conn


CAPABILITIES = {
    "push_alerts",
    "zone_routines",
    "continuous_location",
    "notification_access",
    "selected_contacts",
    "device_health",
}
DEFAULT_RETENTION_HOURS = 24
DEFAULT_NOTIFICATION_RETENTION_HOURS = 72
DEFAULT_HEALTH_RETENTION_HOURS = 24
MAX_RETENTION_HOURS = 24 * 7
MAX_ZONES = 5
_ZONE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class AwarenessError(ValueError):
    """A safe, user-actionable awareness configuration error."""


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_active_device(device_id: str) -> dict[str, Any]:
    from device_registry import get_device

    init_awareness_tables()
    device = get_device(device_id)
    if not device or device.get("status") != "active":
        raise AwarenessError("This device is unavailable. Pair it again before enabling awareness.")
    return device


def init_awareness_tables() -> None:
    conn = get_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_awareness_consents (
                device_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                retention_hours INTEGER NOT NULL DEFAULT 0,
                policy_version TEXT NOT NULL DEFAULT 'ora-awareness-v1',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (device_id, capability)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_push_tokens (
                device_id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL DEFAULT 'expo',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_zones (
                device_id TEXT NOT NULL,
                zone_id TEXT NOT NULL,
                label TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_m INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (device_id, zone_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_awareness_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                data_json TEXT NOT NULL,
                retention_hours INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_device_awareness_events_device_time "
            "ON ora_device_awareness_events(device_id, occurred_at DESC)"
        )
        conn.commit()
    finally:
        close_conn()


def _consent_rows(device_id: str) -> dict[str, dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT capability, enabled, retention_hours, policy_version, updated_at "
            "FROM ora_device_awareness_consents WHERE device_id=?",
            (device_id,),
        ).fetchall()
    finally:
        close_conn()

    state = {
        capability: {
            "capability": capability,
            "enabled": False,
            "retention_hours": (
                DEFAULT_NOTIFICATION_RETENTION_HOURS
                if capability == "notification_access"
                else DEFAULT_HEALTH_RETENTION_HOURS if capability == "device_health"
                else DEFAULT_RETENTION_HOURS if capability == "continuous_location" else 0
            ),
            "policy_version": "ora-awareness-v1",
            "updated_at": None,
        }
        for capability in sorted(CAPABILITIES)
    }
    for capability, enabled, retention_hours, policy_version, updated_at in rows:
        state[capability] = {
            "capability": capability,
            "enabled": bool(enabled),
            "retention_hours": int(retention_hours),
            "policy_version": policy_version,
            "updated_at": updated_at,
        }
    return state


def _require_enabled(device_id: str, capability: str) -> dict[str, Any]:
    consent = _consent_rows(device_id).get(capability)
    if not consent or not consent["enabled"]:
        raise AwarenessError(f"Enable {capability.replace('_', ' ')} before sending this event.")
    return consent


def _cleanup_location_samples(device_id: str, retention_hours: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM ora_device_awareness_events "
            "WHERE device_id=? AND event_type='location_sample' AND occurred_at < ?",
            (device_id, cutoff),
        )
        conn.commit()
    finally:
        close_conn()


def get_awareness_state(device_id: str) -> dict[str, Any]:
    _require_active_device(device_id)
    consents = _consent_rows(device_id)
    conn = get_conn()
    try:
        zones = conn.execute(
            "SELECT zone_id, label, latitude, longitude, radius_m, enabled, updated_at "
            "FROM ora_device_zones WHERE device_id=? ORDER BY label COLLATE NOCASE",
            (device_id,),
        ).fetchall()
        token = conn.execute(
            "SELECT provider, created_at, last_seen_at FROM ora_device_push_tokens WHERE device_id=?",
            (device_id,),
        ).fetchone()
    finally:
        close_conn()
    return {
        "consents": list(consents.values()),
        "zones": [
            {
                "id": zone_id,
                "label": label,
                "latitude": latitude,
                "longitude": longitude,
                "radius_m": radius_m,
                "enabled": bool(enabled),
                "updated_at": updated_at,
            }
            for zone_id, label, latitude, longitude, radius_m, enabled, updated_at in zones
        ],
        "push": {
            "registered": bool(token),
            "provider": token[0] if token else None,
            "created_at": token[1] if token else None,
            "last_seen_at": token[2] if token else None,
        },
    }


def set_awareness_consent(
    device_id: str,
    capability: str,
    enabled: bool,
    retention_hours: int | None = None,
) -> dict[str, Any]:
    _require_active_device(device_id)
    if capability not in CAPABILITIES:
        raise AwarenessError("Unknown awareness capability.")

    if capability in {"continuous_location", "notification_access", "device_health"}:
        default_retention = (
            DEFAULT_NOTIFICATION_RETENTION_HOURS
            if capability == "notification_access"
            else DEFAULT_HEALTH_RETENTION_HOURS if capability == "device_health" else DEFAULT_RETENTION_HOURS
        )
        selected_retention = retention_hours if retention_hours is not None else default_retention
        if not isinstance(selected_retention, int) or not 1 <= selected_retention <= MAX_RETENTION_HOURS:
            raise AwarenessError(f"{capability.replace('_', ' ').capitalize()} retention must be between 1 and {MAX_RETENTION_HOURS} hours.")
    else:
        selected_retention = 0

    now = _iso()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO ora_device_awareness_consents
               (device_id, capability, enabled, retention_hours, policy_version, updated_at)
               VALUES (?, ?, ?, ?, 'ora-awareness-v1', ?)
               ON CONFLICT(device_id, capability) DO UPDATE SET
                 enabled=excluded.enabled,
                 retention_hours=excluded.retention_hours,
                 policy_version=excluded.policy_version,
                 updated_at=excluded.updated_at""",
            (device_id, capability, int(enabled), selected_retention, now),
        )
        if capability == "push_alerts" and not enabled:
            token = conn.execute(
                "SELECT token FROM ora_device_push_tokens WHERE device_id=?", (device_id,)
            ).fetchone()
            conn.execute("DELETE FROM ora_device_push_tokens WHERE device_id=?", (device_id,))
            if token:
                try:
                    from fcm import remove_token

                    remove_token(token[0])
                except Exception:
                    pass
        if capability == "zone_routines" and not enabled:
            conn.execute("DELETE FROM ora_device_zones WHERE device_id=?", (device_id,))
        if capability == "selected_contacts" and not enabled:
            conn.execute("DELETE FROM ora_device_contacts WHERE device_id=?", (device_id,))
        conn.commit()
    finally:
        close_conn()

    if capability == "continuous_location":
        _cleanup_location_samples(device_id, selected_retention)
    return get_awareness_state(device_id)


def replace_zones(device_id: str, zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _require_active_device(device_id)
    _require_enabled(device_id, "zone_routines")
    if len(zones) > MAX_ZONES:
        raise AwarenessError(f"Use at most {MAX_ZONES} named zones.")

    normalized: list[tuple[str, str, float, float, int]] = []
    seen: set[str] = set()
    for zone in zones:
        zone_id = str(zone.get("id", "")).strip().lower()
        label = str(zone.get("label", "")).strip()
        if not _ZONE_ID.match(zone_id) or zone_id in seen:
            raise AwarenessError("Each zone needs a unique lowercase ID using letters, numbers, hyphens, or underscores.")
        if not 1 <= len(label) <= 40:
            raise AwarenessError("Each zone needs a label of up to 40 characters.")
        try:
            latitude = float(zone.get("latitude"))
            longitude = float(zone.get("longitude"))
            radius_m = int(zone.get("radius_m", 200))
        except (TypeError, ValueError) as exc:
            raise AwarenessError("Each zone needs valid latitude, longitude, and radius values.") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or not 75 <= radius_m <= 1000:
            raise AwarenessError("Zone coordinates or radius are outside the safe supported range.")
        normalized.append((zone_id, label, latitude, longitude, radius_m))
        seen.add(zone_id)

    now = _iso()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_zones WHERE device_id=?", (device_id,))
        conn.executemany(
            """INSERT INTO ora_device_zones
               (device_id, zone_id, label, latitude, longitude, radius_m, enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            [(device_id, *zone, now) for zone in normalized],
        )
        conn.commit()
    finally:
        close_conn()
    return get_awareness_state(device_id)["zones"]


def register_push_token(device_id: str, token: str, provider: str = "expo") -> dict[str, Any]:
    _require_active_device(device_id)
    _require_enabled(device_id, "push_alerts")
    cleaned = token.strip()
    if not 20 <= len(cleaned) <= 4096:
        raise AwarenessError("The push token is not valid.")
    if provider != "expo":
        raise AwarenessError("Only Expo push tokens are supported by this ORA deployment.")

    now = _iso()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_push_tokens WHERE token=? AND device_id<>?", (cleaned, device_id))
        conn.execute(
            """INSERT INTO ora_device_push_tokens (device_id, token, provider, created_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(device_id) DO UPDATE SET
                 token=excluded.token, provider=excluded.provider, last_seen_at=excluded.last_seen_at""",
            (device_id, cleaned, provider, now, now),
        )
        conn.commit()
    finally:
        close_conn()
    try:
        from fcm import save_token

        save_token(cleaned, provider)
    except Exception:
        pass
    return get_awareness_state(device_id)["push"]


def get_push_token(device_id: str) -> str | None:
    _require_active_device(device_id)
    _require_enabled(device_id, "push_alerts")
    conn = get_conn()
    try:
        row = conn.execute("SELECT token FROM ora_device_push_tokens WHERE device_id=?", (device_id,)).fetchone()
    finally:
        close_conn()
    return row[0] if row else None


def record_awareness_event(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _require_active_device(device_id)
    event_type = str(payload.get("event_type", "")).strip()
    now = _iso()
    data: dict[str, Any]
    retention_hours = 0

    if event_type in {"zone_enter", "zone_exit"}:
        _require_enabled(device_id, "zone_routines")
        zone_id = str(payload.get("zone_id", "")).strip().lower()
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT label FROM ora_device_zones WHERE device_id=? AND zone_id=? AND enabled=1",
                (device_id, zone_id),
            ).fetchone()
        finally:
            close_conn()
        if not row:
            raise AwarenessError("The named zone is not enabled for this device.")
        data = {"zone_id": zone_id, "label": row[0], "transition": "entered" if event_type == "zone_enter" else "exited"}
        try:
            from memory.profile import update_profile

            update_profile("current_location", row[0] if event_type == "zone_enter" else "away")
            update_profile("last_location_event", f"{event_type}:{row[0]}")
        except Exception:
            pass
    elif event_type == "location_sample":
        consent = _require_enabled(device_id, "continuous_location")
        try:
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
            accuracy_m = float(payload.get("accuracy_m", 0))
        except (TypeError, ValueError) as exc:
            raise AwarenessError("A location sample needs valid latitude and longitude values.") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or accuracy_m < 0:
            raise AwarenessError("The location sample is outside the safe supported range.")
        data = {"latitude": latitude, "longitude": longitude, "accuracy_m": min(round(accuracy_m, 1), 10000)}
        retention_hours = int(consent["retention_hours"])
    elif event_type == "awareness_heartbeat":
        data = {"mode": str(payload.get("mode", "active"))[:24]}
    else:
        raise AwarenessError("Unsupported device awareness event.")

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO ora_device_awareness_events
               (device_id, event_type, occurred_at, data_json, retention_hours)
               VALUES (?, ?, ?, ?, ?)""",
            (device_id, event_type, now, json.dumps(data, separators=(",", ":")), retention_hours),
        )
        conn.execute("UPDATE ora_devices SET last_seen_at=? WHERE id=?", (now, device_id))
        conn.commit()
    finally:
        close_conn()

    if event_type == "location_sample":
        _cleanup_location_samples(device_id, retention_hours)
    return {"event_type": event_type, "occurred_at": now, "retention_hours": retention_hours}


def list_awareness_events(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
    _require_active_device(device_id)
    bounded_limit = max(1, min(int(limit), 100))
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT event_type, occurred_at, data_json, retention_hours
               FROM ora_device_awareness_events WHERE device_id=?
               ORDER BY id DESC LIMIT ?""",
            (device_id, bounded_limit),
        ).fetchall()
    finally:
        close_conn()

    events: list[dict[str, Any]] = []
    for event_type, occurred_at, data_json, retention_hours in rows:
        detail = json.loads(data_json)
        if event_type == "location_sample":
            detail = {"summary": "Precise location sample retained"}
        events.append(
            {
                "event_type": event_type,
                "occurred_at": occurred_at,
                "detail": detail,
                "retention_hours": retention_hours,
            }
        )
    return events


def delete_location_history(device_id: str) -> int:
    _require_active_device(device_id)
    conn = get_conn()
    try:
        result = conn.execute(
            "DELETE FROM ora_device_awareness_events WHERE device_id=? AND event_type='location_sample'",
            (device_id,),
        )
        conn.commit()
        return max(result.rowcount, 0)
    finally:
        close_conn()
