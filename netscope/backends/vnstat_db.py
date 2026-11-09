# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read historical data directly from vnStat's SQLite database.

This recovers old stored data that may exist on the system, including all
interfaces and all periods (5-minute, hourly, daily, monthly, yearly, top days).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..models import InterfaceInfo, UsagePoint, UsageSnapshot

DB_CANDIDATES = [
    "/var/lib/vnstat/vnstat.db",
    "/var/db/vnstat/vnstat.db",
    "/var/local/lib/vnstat/vnstat.db",
]


def find_db() -> Path | None:
    for raw in DB_CANDIDATES:
        path = Path(raw)
        if path.exists() and os.access(path, os.R_OK):
            return path
    return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                return parsed
            return parsed
        except Exception:
            pass
    return None


def _parse_day(value: str | None) -> date | None:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _point(start, rx, tx, label: str, detail: str) -> UsagePoint:
    return UsagePoint(rx=int(rx or 0), tx=int(tx or 0), start=start, label=label, detail=detail)


def read_all(db_path: Path | None = None) -> list[UsageSnapshot]:
    db_path = db_path or find_db()
    if not db_path:
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            return []
    conn.row_factory = sqlite3.Row
    try:
        ifaces = conn.execute(
            "SELECT id, name, alias, active, created, updated, rxtotal, txtotal FROM interface ORDER BY active DESC, name"
        ).fetchall()
        snapshots: list[UsageSnapshot] = []
        for row in ifaces:
            iface_id = row["id"]
            info = InterfaceInfo(
                name=str(row["name"] or "?"),
                alias=str(row["alias"] or ""),
                active=bool(row["active"]),
                created=_parse_dt(row["created"]),
                updated=_parse_dt(row["updated"]),
                total_rx=int(row["rxtotal"] or 0),
                total_tx=int(row["txtotal"] or 0),
                source="vnstat-db",
            )
            snap = UsageSnapshot(interface=info, sources=[f"vnStat DB: {db_path}"])

            for r in conn.execute(
                "SELECT date, rx, tx FROM fiveminute WHERE interface=? ORDER BY date", (iface_id,)
            ):
                dt = _parse_dt(r["date"])
                label = dt.strftime("%H:%M") if dt else str(r["date"])
                detail = dt.strftime("%Y-%m-%d %H:%M") if dt else label
                snap.fiveminute.append(_point(dt, r["rx"], r["tx"], label, detail))

            for r in conn.execute(
                "SELECT date, rx, tx FROM hour WHERE interface=? ORDER BY date", (iface_id,)
            ):
                dt = _parse_dt(r["date"])
                label = dt.strftime("%H:00") if dt else str(r["date"])
                detail = dt.strftime("%Y-%m-%d %H:00") if dt else label
                snap.hour.append(_point(dt, r["rx"], r["tx"], label, detail))

            for r in conn.execute(
                "SELECT date, rx, tx FROM day WHERE interface=? ORDER BY date", (iface_id,)
            ):
                day = _parse_day(r["date"])
                label = day.strftime("%Y-%m-%d") if day else str(r["date"])
                snap.day.append(_point(day, r["rx"], r["tx"], label, label))

            for r in conn.execute(
                "SELECT date, rx, tx FROM month WHERE interface=? ORDER BY date", (iface_id,)
            ):
                day = _parse_day(r["date"])
                label = day.strftime("%Y-%m") if day else str(r["date"])
                snap.month.append(_point(day, r["rx"], r["tx"], label, label))

            for r in conn.execute(
                "SELECT date, rx, tx FROM year WHERE interface=? ORDER BY date", (iface_id,)
            ):
                day = _parse_day(r["date"])
                label = day.strftime("%Y") if day else str(r["date"])
                snap.year.append(_point(day, r["rx"], r["tx"], label, label))

            for r in conn.execute(
                "SELECT date, rx, tx FROM top WHERE interface=? ORDER BY rx+tx DESC, date DESC", (iface_id,)
            ):
                day = _parse_day(r["date"])
                label = day.strftime("%Y-%m-%d") if day else str(r["date"])
                snap.top.append(_point(day, r["rx"], r["tx"], label, label))

            snapshots.append(snap)
        return snapshots
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
