# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn snapshot history into chart series and "current period" lookups.

Everything here is GTK-free so the GUI, CLI and tests share one implementation.
Functions that depend on the clock take an optional ``now``/``today`` argument.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from .models import UsagePoint, UsageSnapshot
from .utils import fmt_clock, month_name, weekday_name

HISTORY_PERIODS = ("fiveminute", "hour", "day", "month", "year", "top")


def date_key(value):
    """Return the calendar day of a point start (datetimes are truncated)."""
    if isinstance(value, datetime):
        return value.date()
    return value


def hour_key(value) -> tuple[int, int, int, int] | None:
    if isinstance(value, datetime):
        return (value.year, value.month, value.day, value.hour)
    return None


def _filled(src: UsagePoint | None, start, label: str, detail: str) -> UsagePoint:
    return UsagePoint(src.rx if src else 0, src.tx if src else 0, start, label, detail)


def hour_points(snap: UsageSnapshot, count: int, now: datetime | None = None) -> list[UsagePoint]:
    """The last ``count`` hours ending with the current one, zero-filled."""
    now = (now or datetime.now()).replace(minute=0, second=0, microsecond=0)
    by_hour = {hour_key(p.start): p for p in snap.hour if hour_key(p.start)}
    points = []
    for offset in range(count - 1, -1, -1):
        dt = now - timedelta(hours=offset)
        detail = f"{weekday_name(dt)} {dt:%Y-%m-%d %H:00}"
        points.append(_filled(by_hour.get(hour_key(dt)), dt, fmt_clock(dt.hour), detail))
    return points


def day_points(snap: UsageSnapshot, count: int, today: date | None = None) -> list[UsagePoint]:
    """The last ``count`` days ending today, zero-filled."""
    today = today or date.today()
    by_day = {date_key(p.start): p for p in snap.day if date_key(p.start)}
    points = []
    for offset in range(count - 1, -1, -1):
        d = today - timedelta(days=offset)
        points.append(_filled(by_day.get(d), d, str(d.day), f"{weekday_name(d)} {d.isoformat()}"))
    return points


def month_points(snap: UsageSnapshot, count: int, today: date | None = None) -> list[UsagePoint]:
    """The last ``count`` calendar months ending with the current one, zero-filled."""
    today = today or date.today()
    by_month = {}
    for p in snap.month:
        d = date_key(p.start)
        if isinstance(d, date):
            by_month[(d.year, d.month)] = p
    current = today.year * 12 + (today.month - 1)
    points = []
    for offset in range(count - 1, -1, -1):
        year, month0 = divmod(current - offset, 12)
        month = month0 + 1
        start = date(year, month, 1)
        detail = f"{month_name(month)} {year}"
        points.append(_filled(by_month.get((year, month)), start, month_name(month, True), detail))
    return points


def raw_points(points: list[UsagePoint]) -> list[UsagePoint]:
    """Copy points as-is, making sure label and detail are never empty."""
    out = []
    for p in points:
        label = p.label or str(p.start)
        out.append(UsagePoint(p.rx, p.tx, p.start, label, p.detail or label))
    return out


# Default number of points per period, and the choices offered in the UI.
DEFAULT_COUNTS = {"fiveminute": 96, "hour": 24, "day": 30, "month": 12, "year": 0, "top": 15}
RANGE_CHOICES = {
    "fiveminute": (48, 96, 288),
    "hour": (24, 48, 168),
    "day": (7, 30, 90, 365),
    "month": (6, 12, 24, 60),
    "year": (),
    "top": (),
}
_STEPS = {"fiveminute": 8, "hour": 4, "day": 5, "month": 2, "year": 1, "top": 1}


def history_points(
    snap: UsageSnapshot,
    period: str,
    count: int | None = None,
    now: datetime | None = None,
) -> tuple[list[UsagePoint], int]:
    """Points for the history view plus the x-axis label step to use."""
    if period not in DEFAULT_COUNTS:
        raise ValueError(f"unknown history period: {period!r}")
    now = now or datetime.now()
    count = count or DEFAULT_COUNTS[period]
    step = _STEPS[period]
    if period == "fiveminute":
        return raw_points(snap.fiveminute[-count:]), step
    if period == "hour":
        return hour_points(snap, count, now), max(step, count // 6)
    if period == "day":
        return day_points(snap, count, now.date()), max(step, count // 6)
    if period == "month":
        return month_points(snap, count, now.date()), max(step, count // 12)
    if period == "year":
        return raw_points(snap.year), step
    return raw_points(sorted(snap.top, key=lambda p: p.total, reverse=True)[:count]), step


def compare_periods(
    snap: UsageSnapshot, period: str, count: int, now: datetime | None = None
) -> tuple[int, int] | None:
    """Total of the last ``count`` hours/days/months and of the ``count`` before them."""
    builders = {"hour": hour_points, "day": day_points, "month": month_points}
    if period not in builders:
        return None
    now = now or datetime.now()
    anchor = now if period == "hour" else now.date()
    points = builders[period](snap, count * 2, anchor)
    previous, current = points[:count], points[count:]
    return sum(p.total for p in current), sum(p.total for p in previous)


def to_csv(points: list[UsagePoint]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["start", "label", "rx_bytes", "tx_bytes", "total_bytes"])
    for p in points:
        start = p.start.isoformat() if hasattr(p.start, "isoformat") else str(p.start or "")
        writer.writerow([start, p.label, p.rx, p.tx, p.total])
    return out.getvalue()


def usage_today(snap: UsageSnapshot | None, today: date | None = None) -> UsagePoint | None:
    if not snap:
        return None
    today = today or date.today()
    return next((p for p in reversed(snap.day) if date_key(p.start) == today), None)


def usage_this_month(snap: UsageSnapshot | None, today: date | None = None) -> UsagePoint | None:
    if not snap:
        return None
    today = today or date.today()
    for p in reversed(snap.month):
        d = date_key(p.start)
        if isinstance(d, date) and (d.year, d.month) == (today.year, today.month):
            return p
    return None


def usage_this_hour(snap: UsageSnapshot | None, now: datetime | None = None) -> UsagePoint | None:
    if not snap:
        return None
    key = hour_key(now or datetime.now())
    return next((p for p in reversed(snap.hour) if hour_key(p.start) == key), None)
