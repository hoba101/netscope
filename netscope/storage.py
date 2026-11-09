# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""NetScope's own SQLite history store.

Used on platforms without vnstat history and as a merged/imported history cache.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime

from .models import InterfaceInfo, UsagePoint, UsageSnapshot
from .utils import data_dir, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS interfaces (
  name TEXT PRIMARY KEY,
  alias TEXT DEFAULT '',
  created TEXT,
  updated TEXT,
  source TEXT DEFAULT 'netscope'
);
CREATE TABLE IF NOT EXISTS usage (
  interface TEXT NOT NULL,
  period TEXT NOT NULL,
  start TEXT NOT NULL,
  rx INTEGER NOT NULL DEFAULT 0,
  tx INTEGER NOT NULL DEFAULT 0,
  source TEXT DEFAULT 'netscope',
  PRIMARY KEY(interface, period, start, source)
);
CREATE INDEX IF NOT EXISTS idx_usage_iface_period ON usage(interface, period, start);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  interface TEXT DEFAULT '',
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  value TEXT DEFAULT '',
  seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts DESC);
CREATE TABLE IF NOT EXISTS speedtests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  interface TEXT DEFAULT '',
  ping_ms REAL,
  down_mbps REAL,
  up_mbps REAL
);
CREATE TABLE IF NOT EXISTS alert_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def db_path():
    ensure_dirs()
    return data_dir() / "history.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _norm_start(period: str, start) -> str:
    if start is None:
        return ""
    if isinstance(start, datetime):
        if period == "fiveminute":
            minute = (start.minute // 5) * 5
            return start.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        if period == "hour":
            return start.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00:00")
        start = start.date()
    if isinstance(start, date):
        if period == "month":
            return start.replace(day=1).isoformat()
        if period == "year":
            return start.replace(month=1, day=1).isoformat()
        return start.isoformat()
    return str(start)


def import_snapshot(snapshot: UsageSnapshot) -> int:
    rows = 0
    with closing(connect()) as conn:
        info = snapshot.interface
        conn.execute(
            "INSERT INTO interfaces(name, alias, created, updated, source) VALUES(?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET alias=excluded.alias, updated=COALESCE(excluded.updated, interfaces.updated), source=excluded.source",
            (
                info.name,
                info.alias,
                info.created.isoformat(sep=" ", timespec="seconds") if info.created else None,
                info.updated.isoformat(sep=" ", timespec="seconds") if info.updated else None,
                info.source or "netscope",
            ),
        )
        for period, points in (
            ("fiveminute", snapshot.fiveminute),
            ("hour", snapshot.hour),
            ("day", snapshot.day),
            ("month", snapshot.month),
            ("year", snapshot.year),
            ("top", snapshot.top),
        ):
            for point in points:
                start = _norm_start(period, point.start)
                if not start:
                    continue
                conn.execute(
                    "INSERT INTO usage(interface, period, start, rx, tx, source) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(interface, period, start, source) DO UPDATE SET rx=excluded.rx, tx=excluded.tx",
                    (info.name, period, start, int(point.rx), int(point.tx), info.source or "netscope"),
                )
                rows += 1
        conn.commit()
    return rows


def read_snapshot(iface: str) -> UsageSnapshot | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM interfaces WHERE name=?", (iface,)).fetchone()
        if not row:
            return None
        created = None
        updated = None
        try:
            created = datetime.fromisoformat(row["created"]) if row["created"] else None
        except Exception:
            pass
        try:
            updated = datetime.fromisoformat(row["updated"]) if row["updated"] else None
        except Exception:
            pass
        info = InterfaceInfo(
            name=row["name"],
            alias=row["alias"] or "",
            created=created,
            updated=updated,
            source=row["source"] or "netscope",
        )
        snap = UsageSnapshot(interface=info, sources=["NetScope history"])
        for period, attr in (
            ("fiveminute", "fiveminute"),
            ("hour", "hour"),
            ("day", "day"),
            ("month", "month"),
            ("year", "year"),
            ("top", "top"),
        ):
            rows = conn.execute(
                "SELECT start, SUM(rx) rx, SUM(tx) tx FROM usage WHERE interface=? AND period=? GROUP BY start ORDER BY start",
                (iface, period),
            ).fetchall()
            for r in rows:
                start = _parse_start(period, r["start"])
                getattr(snap, attr).append(
                    UsagePoint(
                        rx=int(r["rx"] or 0),
                        tx=int(r["tx"] or 0),
                        start=start,
                        label=str(r["start"]),
                        detail=str(r["start"]),
                    )
                )
        return snap


def list_interfaces() -> list[str]:
    with closing(connect()) as conn:
        return [r[0] for r in conn.execute("SELECT name FROM interfaces ORDER BY name").fetchall()]


def _parse_start(period: str, value: str):
    try:
        if period in ("fiveminute", "hour"):
            return datetime.fromisoformat(value.replace(" ", "T"))
        return date.fromisoformat(value[:10])
    except Exception:
        return value


def add_alert(
    kind: str,
    severity: str,
    title: str,
    message: str,
    interface: str = "",
    value: str = "",
    dedup_key: str = "",
    cooldown_sec: int = 0,
) -> bool:
    """Insert alert unless dedup/cooldown suppresses it. Returns True if inserted."""
    now = datetime.now().isoformat(timespec="seconds")
    with closing(connect()) as conn:
        if dedup_key and cooldown_sec > 0:
            row = conn.execute(
                "SELECT value FROM alert_state WHERE key=?", (f"cooldown:{dedup_key}",)
            ).fetchone()
            if row:
                try:
                    last = datetime.fromisoformat(row[0])
                    if (datetime.now() - last).total_seconds() < cooldown_sec:
                        return False
                except Exception:
                    pass
        conn.execute(
            "INSERT INTO alerts(ts,kind,severity,interface,title,message,value,seen) VALUES(?,?,?,?,?,?,?,0)",
            (now, kind, severity, interface, title, message, value),
        )
        if dedup_key:
            conn.execute(
                "INSERT INTO alert_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"cooldown:{dedup_key}", now),
            )
            conn.execute(
                "INSERT INTO alert_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"last:{dedup_key}", value or message),
            )
        conn.commit()
    return True


def list_alerts(limit: int = 200, unseen_only: bool = False):
    with closing(connect()) as conn:
        q = "SELECT id,ts,kind,severity,interface,title,message,value,seen FROM alerts"
        args = []
        if unseen_only:
            q += " WHERE seen=0"
        q += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(2000, int(limit))))
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def mark_alerts_seen(ids=None):
    with closing(connect()) as conn:
        if ids is None:
            conn.execute("UPDATE alerts SET seen=1 WHERE seen=0")
        else:
            conn.executemany("UPDATE alerts SET seen=1 WHERE id=?", [(int(i),) for i in ids])
        conn.commit()


def clear_alerts():
    with closing(connect()) as conn:
        conn.execute("DELETE FROM alerts")
        conn.commit()


def get_state(key: str):
    with closing(connect()) as conn:
        r = conn.execute("SELECT value FROM alert_state WHERE key=?", (key,)).fetchone()
        return r[0] if r else None


def set_state(key: str, value: str):
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO alert_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()


def add_speedtest(
    interface: str, ping_ms: float | None, down_mbps: float | None, up_mbps: float | None
) -> None:
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO speedtests(ts, interface, ping_ms, down_mbps, up_mbps) VALUES(?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), interface, ping_ms, down_mbps, up_mbps),
        )
        conn.commit()


def list_speedtests(limit: int = 20) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT ts, interface, ping_ms, down_mbps, up_mbps FROM speedtests ORDER BY id DESC LIMIT ?",
            (max(1, min(500, int(limit))),),
        ).fetchall()
        return [dict(r) for r in rows]
