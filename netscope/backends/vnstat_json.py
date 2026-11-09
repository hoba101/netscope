# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read data from the vnstat CLI (JSON)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date, datetime

from ..models import InterfaceInfo, UsagePoint, UsageSnapshot


def available() -> bool:
    return shutil.which("vnstat") is not None


def _run_json(*args: str) -> dict | None:
    cmd = ["vnstat", "--json", *args]
    try:
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=15)
        return json.loads(raw)
    except Exception:
        return None


def _ts(entry: dict) -> datetime | None:
    value = entry.get("timestamp")
    try:
        return datetime.fromtimestamp(int(value)) if value else None
    except Exception:
        return None


def _point(rx, tx, start, label: str, detail: str = "") -> UsagePoint:
    return UsagePoint(rx=int(rx or 0), tx=int(tx or 0), start=start, label=label, detail=detail or label)


def read_all() -> list[UsageSnapshot]:
    payload = _run_json()
    if not payload:
        return []
    snapshots: list[UsageSnapshot] = []
    for iface in payload.get("interfaces") or []:
        traffic = iface.get("traffic") or {}
        total = traffic.get("total") or {}
        created = _ts(iface.get("created") or {})
        updated = _ts(iface.get("updated") or {})
        info = InterfaceInfo(
            name=str(iface.get("name", "?")),
            alias=str(iface.get("alias") or ""),
            created=created,
            updated=updated,
            total_rx=int(total.get("rx", 0)),
            total_tx=int(total.get("tx", 0)),
            source="vnstat-json",
        )
        snap = UsageSnapshot(interface=info, sources=["vnStat CLI"])

        for e in traffic.get("fiveminute") or []:
            d = e.get("date") or {}
            t = e.get("time") or {}
            try:
                dt = datetime(int(d["year"]), int(d["month"]), int(d["day"]), int(t.get("hour", 0)), int(t.get("minute", 0)))
            except Exception:
                dt = _ts(e)
            label = dt.strftime("%H:%M") if dt else "?"
            snap.fiveminute.append(_point(e.get("rx"), e.get("tx"), dt, label, dt.strftime("%Y-%m-%d %H:%M") if dt else label))

        for e in traffic.get("hour") or []:
            d = e.get("date") or {}
            t = e.get("time") or {}
            try:
                dt = datetime(int(d["year"]), int(d["month"]), int(d["day"]), int(t.get("hour", 0)))
            except Exception:
                dt = _ts(e)
            label = dt.strftime("%H:00") if dt else "?"
            snap.hour.append(_point(e.get("rx"), e.get("tx"), dt, label, dt.strftime("%Y-%m-%d %H:00") if dt else label))

        for e in traffic.get("day") or []:
            d = e.get("date") or {}
            try:
                day = date(int(d["year"]), int(d["month"]), int(d["day"]))
            except Exception:
                ts = _ts(e)
                day = ts.date() if ts else None
            label = day.isoformat() if day else "?"
            snap.day.append(_point(e.get("rx"), e.get("tx"), day, label))

        for e in traffic.get("month") or []:
            d = e.get("date") or {}
            try:
                day = date(int(d["year"]), int(d["month"]), 1)
                label = f"{day.year}-{day.month:02d}"
            except Exception:
                ts = _ts(e)
                day = ts.date().replace(day=1) if ts else None
                label = day.strftime("%Y-%m") if day else "?"
            snap.month.append(_point(e.get("rx"), e.get("tx"), day, label))

        for e in traffic.get("year") or []:
            d = e.get("date") or {}
            try:
                day = date(int(d["year"]), 1, 1)
                label = str(day.year)
            except Exception:
                day = None
                label = "?"
            snap.year.append(_point(e.get("rx"), e.get("tx"), day, label))

        for e in traffic.get("top") or []:
            d = e.get("date") or {}
            try:
                day = date(int(d["year"]), int(d["month"]), int(d["day"]))
            except Exception:
                ts = _ts(e)
                day = ts.date() if ts else None
            label = day.isoformat() if day else "?"
            snap.top.append(_point(e.get("rx"), e.get("tx"), day, label))

        snapshots.append(snap)
    return snapshots
