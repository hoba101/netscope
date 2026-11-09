# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import date, datetime

import pytest

from netscope import series
from netscope.models import UsageSnapshot


def test_hour_points_are_zero_filled_and_end_now(snap, now):
    points = series.hour_points(snap, 4, now)
    assert [p.start for p in points] == [
        datetime(2026, 3, 15, 11),
        datetime(2026, 3, 15, 12),
        datetime(2026, 3, 15, 13),
        datetime(2026, 3, 15, 14),
    ]
    assert [p.total for p in points] == [0, 0, 110, 220]
    assert points[-1].label == "14:00"


def test_day_points_cross_month_boundary(snap):
    points = series.day_points(snap, 3, date(2026, 3, 1))
    assert [p.start for p in points] == [date(2026, 2, 27), date(2026, 2, 28), date(2026, 3, 1)]


def test_month_points_cross_year_boundary(snap):
    points = series.month_points(snap, 4, date(2026, 2, 10))
    assert [p.start for p in points] == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert points[-1].total == 55_000
    assert points[-1].detail == "February 2026"


def test_current_period_lookups(snap, now):
    assert series.usage_today(snap, now.date()).total == 2_200
    assert series.usage_this_month(snap, now.date()).total == 66_000
    # Only the 14:00 entry from *this* month counts, not 15 Feb 14:00.
    assert series.usage_this_hour(snap, now).total == 220


def test_lookups_handle_missing_snapshot_and_data(now):
    assert series.usage_today(None) is None
    empty = UsageSnapshot(interface=snap_iface())
    assert series.usage_this_hour(empty, now) is None
    assert series.usage_this_month(empty, now.date()) is None


@pytest.mark.parametrize(
    ("period", "expected_len", "step"),
    [("hour", 24, 4), ("day", 30, 5), ("month", 12, 2), ("year", 1, 1), ("top", 2, 1), ("fiveminute", 0, 8)],
)
def test_history_points_shapes(snap, now, period, expected_len, step):
    points, got_step = series.history_points(snap, period, now=now)
    assert len(points) == expected_len
    assert got_step == step


def test_history_top_is_sorted_descending(snap, now):
    points, _ = series.history_points(snap, "top", now=now)
    assert [p.label for p in points] == ["b", "a"]


def test_history_rejects_unknown_period(snap):
    with pytest.raises(ValueError):
        series.history_points(snap, "weekly")


def test_raw_points_fill_missing_labels():
    from netscope.models import UsagePoint

    (p,) = series.raw_points([UsagePoint(1, 1, date(2026, 1, 1))])
    assert p.label == "2026-01-01"
    assert p.detail == "2026-01-01"


def snap_iface():
    from netscope.models import InterfaceInfo

    return InterfaceInfo(name="eth0")
