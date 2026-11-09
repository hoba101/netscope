# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date, datetime

import pytest

from netscope import i18n
from netscope.models import InterfaceInfo, UsagePoint, UsageSnapshot


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Never touch the real config/data dirs, and always run in English."""
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    i18n.init("en")
    yield
    i18n.init("en")


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 3, 15, 14, 30)


@pytest.fixture
def snap(now) -> UsageSnapshot:
    """A snapshot with a little history around ``now``."""
    s = UsageSnapshot(interface=InterfaceInfo(name="wlan0"))
    s.hour = [
        UsagePoint(100, 10, datetime(2026, 3, 15, 13)),
        UsagePoint(200, 20, datetime(2026, 3, 15, 14)),
        # Same hour and day-of-month, previous month: must not count as "this hour".
        UsagePoint(999, 999, datetime(2026, 2, 15, 14)),
    ]
    s.day = [
        UsagePoint(1_000, 100, date(2026, 3, 14)),
        UsagePoint(2_000, 200, date(2026, 3, 15)),
    ]
    s.month = [
        UsagePoint(50_000, 5_000, date(2026, 2, 1)),
        UsagePoint(60_000, 6_000, date(2026, 3, 1)),
    ]
    s.year = [UsagePoint(1, 2, date(2026, 1, 1), "2026")]
    s.top = [UsagePoint(5, 5, date(2026, 1, 2), "a"), UsagePoint(50, 50, date(2026, 1, 3), "b")]
    return s
