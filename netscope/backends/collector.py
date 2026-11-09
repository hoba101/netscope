# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date, datetime

from ..models import InterfaceInfo, UsagePoint, UsageSnapshot
from ..settings import Settings
from ..utils import is_linux, is_windows
from . import linux_sysfs, vnstat_db, vnstat_json, windows
from .. import storage


def list_interfaces(settings: Settings | None = None) -> list[str]:
    settings = settings or Settings.load()
    names: list[str] = []
    for src in settings.history_sources:
        try:
            if src == "vnstat" and vnstat_json.available():
                for snap in vnstat_json.read_all():
                    names.append(snap.interface.name)
            elif src == "vnstat_db" and is_linux():
                for snap in vnstat_db.read_all():
                    names.append(snap.interface.name)
            elif src == "netscope":
                names.extend(storage.list_interfaces())
        except Exception:
            pass
    if is_linux():
        names.extend(linux_sysfs.list_interfaces())
    if is_windows():
        names.extend(windows.list_interfaces())
    # unique, keep order preference
    seen = set()
    result = []
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    result.sort(key=lambda n: (n == "lo", n))
    return result


def _merge_points(*groups: list[UsagePoint], period: str) -> list[UsagePoint]:
    merged: dict[str, UsagePoint] = {}
    for group in groups:
        for point in group:
            key = storage._norm_start(period, point.start) if point.start else (point.label or "")
            if not key:
                key = point.detail or point.label or str(id(point))
            prev = merged.get(key)
            if prev is None or point.total >= prev.total:
                merged[key] = point
    items = list(merged.items())
    items.sort(key=lambda item: item[0])
    return [item[1] for item in items]


def collect_snapshot(selected: str = "", settings: Settings | None = None) -> UsageSnapshot | None:
    settings = settings or Settings.load()
    selected = selected or settings.selected_interface
    candidates: list[UsageSnapshot] = []

    for src in settings.history_sources:
        try:
            if src == "vnstat" and is_linux() and vnstat_json.available():
                candidates.extend(vnstat_json.read_all())
            elif src == "vnstat_db" and is_linux():
                candidates.extend(vnstat_db.read_all())
            elif src == "netscope":
                for name in storage.list_interfaces():
                    snap = storage.read_snapshot(name)
                    if snap:
                        candidates.append(snap)
        except Exception:
            pass

    snap = _select(candidates, selected)
    if snap is None and is_windows():
        sample = windows.read_counters(selected or None)
        if sample:
            name, rx, tx = sample
            snap = UsageSnapshot(
                interface=InterfaceInfo(name=name, total_rx=rx, total_tx=tx, source="windows"),
                sources=["Windows counters"],
                notes=[
                    "Windows does not keep detailed historical network usage by default. NetScope will build history from now on while it runs or is sampled."
                ],
            )
    if snap is None and is_linux():
        iface = selected or linux_sysfs.default_interface() or "eno1"
        counters = linux_sysfs.read_counters(iface)
        rx, tx = counters if counters else (0, 0)
        snap = UsageSnapshot(
            interface=InterfaceInfo(name=iface, total_rx=rx, total_tx=tx, source="sysfs"),
            sources=["Linux counters"],
            notes=["No vnStat history was found. Install and enable vnstatd for automatic long-term history."],
        )

    if snap is None:
        return None

    # Merge same-interface historical sources.
    same = [s for s in candidates if s.interface.name == snap.interface.name]
    if len(same) > 1:
        merged = UsageSnapshot(interface=snap.interface, sources=[])
        for s in same:
            for note in s.notes:
                if note not in merged.notes:
                    merged.notes.append(note)
            for src in s.sources:
                if src not in merged.sources:
                    merged.sources.append(src)
            if s.interface.created and (not merged.interface.created or s.interface.created < merged.interface.created):
                merged.interface.created = s.interface.created
            if s.interface.updated and (not merged.interface.updated or s.interface.updated > merged.interface.updated):
                merged.interface.updated = s.interface.updated
            merged.interface.total_rx = max(merged.interface.total_rx, s.interface.total_rx)
            merged.interface.total_tx = max(merged.interface.total_tx, s.interface.total_tx)
        merged.fiveminute = _merge_points(*(s.fiveminute for s in same), period="fiveminute")
        merged.hour = _merge_points(*(s.hour for s in same), period="hour")
        merged.day = _merge_points(*(s.day for s in same), period="day")
        merged.month = _merge_points(*(s.month for s in same), period="month")
        merged.year = _merge_points(*(s.year for s in same), period="year")
        merged.top = _merge_points(*(s.top for s in same), period="top")
        snap = merged

    # Live speed.
    try:
        if settings.live_speed:
            if is_linux():
                rates = linux_sysfs.read_live_rates(snap.interface.name)
            elif is_windows():
                rates = windows.read_live_rates(snap.interface.name)
            else:
                rates = None
            if rates:
                snap.live_rx_bps, snap.live_tx_bps = rates
    except Exception:
        pass

    # Persist into NetScope history store for cross-platform continuity/import.
    try:
        storage.import_snapshot(snap)
    except Exception:
        pass

    return snap


def _select(snapshots: list[UsageSnapshot], selected: str) -> UsageSnapshot | None:
    if not snapshots:
        return None
    if selected:
        for snap in snapshots:
            if snap.interface.name == selected:
                return snap
    default = linux_sysfs.default_interface() if is_linux() else None
    if default:
        for snap in snapshots:
            if snap.interface.name == default:
                return snap
    snapshots = sorted(
        snapshots,
        key=lambda s: (s.interface.name == "lo", -(len(s.day) + len(s.month) + len(s.hour)), -s.interface.total_rx - s.interface.total_tx),
    )
    return snapshots[0]
