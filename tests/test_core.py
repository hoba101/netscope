# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Formatting, settings, quota, storage, i18n and history merging."""

import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from netscope import storage
from netscope.backends.collector import _merge_points
from netscope.backends.vnstat_json import parse_payload
from netscope.models import InterfaceInfo, UsagePoint, UsageSnapshot
from netscope.quota import evaluate
from netscope.settings import Settings
from netscope.utils import fmt_bytes, fmt_rate

LOCALES = Path(__file__).resolve().parents[1] / "netscope" / "data" / "locales"


# -- formatting ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B"),
        (-5, "0 B"),
        (1023, "1023 B"),
        (1024, "1.00 KiB"),
        (15 * 1024**2, "15.0 MiB"),
        (300 * 1024**3, "300 GiB"),
    ],
)
def test_fmt_bytes(value, expected):
    assert fmt_bytes(value) == expected


def test_fmt_bytes_compact_and_rate():
    assert fmt_bytes(1536, compact=True) == "1.5K"
    assert fmt_bytes(999, rate=True) == "999 bit/s"
    assert fmt_bytes(12_500_000, rate=True) == "12.5 Mbit/s"


def test_fmt_rate_units():
    assert fmt_rate(8_000_000) == "8.0 Mbit/s"
    assert fmt_rate(8 * 1024, "bytes") == "1.00 KiB/s"


# -- settings -----------------------------------------------------------------


def test_settings_defaults_when_missing():
    s = Settings.load()
    assert s.refresh_seconds == 60
    assert s.quota_action == "warn"


def test_settings_clamp_and_sanitise_bad_values():
    Settings.path().write_text(
        json.dumps(
            {
                "refresh_seconds": 1,
                "chart_days": 10_000,
                "theme": "neon",
                "quota_action": "explode",
                "alerts_enabled": 0,
            }
        )
    )
    s = Settings.load()
    assert s.refresh_seconds == 15
    assert s.chart_days == 365
    assert s.theme == "system"
    assert s.quota_action == "warn"
    assert s.alerts_enabled is False


def test_settings_survive_corrupt_file():
    Settings.path().write_text("{not json")
    assert Settings.load().language == "system"


def test_settings_round_trip():
    s = Settings.load()
    s.quota_daily_mb = 512
    s.language = "ar"
    s.save()
    loaded = Settings.load()
    assert (loaded.quota_daily_mb, loaded.language) == (512, "ar")


# -- quota --------------------------------------------------------------------


def _snap_with_today(total_bytes: int) -> UsageSnapshot:
    snap = UsageSnapshot(interface=InterfaceInfo(name="eth0"))
    snap.day = [UsagePoint(total_bytes, 0, date.today())]
    return snap


@pytest.mark.parametrize(
    ("used_mb", "warn", "exceeded"),
    [(10, False, False), (80, True, False), (100, True, True)],
)
def test_quota_thresholds(used_mb, warn, exceeded):
    settings = Settings(quota_enabled=True, quota_daily_mb=100, quota_warn_percent=80)
    q = evaluate(_snap_with_today(used_mb * 1024 * 1024), settings)
    assert (q.warn, q.exceeded) == (warn, exceeded)
    assert q.percent == pytest.approx(used_mb)
    assert q.interface == "eth0"


def test_quota_without_snapshot():
    q = evaluate(None, Settings())
    assert q.used_bytes == 0 and not q.exceeded


# -- storage ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("period", "start", "expected"),
    [
        ("fiveminute", datetime(2026, 3, 15, 14, 37, 12), "2026-03-15 14:35:00"),
        ("hour", datetime(2026, 3, 15, 14, 37), "2026-03-15 14:00:00"),
        ("day", datetime(2026, 3, 15, 14, 37), "2026-03-15"),
        ("month", date(2026, 3, 15), "2026-03-01"),
        ("year", date(2026, 3, 15), "2026-01-01"),
        ("day", None, ""),
    ],
)
def test_norm_start(period, start, expected):
    assert storage._norm_start(period, start) == expected


def test_snapshot_round_trip(snap):
    assert storage.import_snapshot(snap) > 0
    loaded = storage.read_snapshot("wlan0")
    assert loaded is not None
    assert [(p.start, p.total) for p in loaded.day] == [(p.start, p.total) for p in snap.day]
    assert loaded.hour[0].start == datetime(2026, 2, 15, 14)
    assert storage.list_interfaces() == ["wlan0"]
    assert storage.read_snapshot("nope") is None


def test_alert_cooldown_suppresses_duplicates():
    assert storage.add_alert("k", "warning", "T", "m", dedup_key="x", cooldown_sec=600)
    assert not storage.add_alert("k", "warning", "T", "m", dedup_key="x", cooldown_sec=600)
    assert storage.add_alert("k", "warning", "T", "m", dedup_key="y", cooldown_sec=600)
    alerts = storage.list_alerts()
    assert len(alerts) == 2 and not any(a["seen"] for a in alerts)
    storage.mark_alerts_seen()
    assert storage.list_alerts(unseen_only=True) == []
    storage.clear_alerts()
    assert storage.list_alerts() == []


# -- history sources ----------------------------------------------------------


def test_merge_points_prefers_larger_value_per_period():
    a = [UsagePoint(10, 0, date(2026, 1, 1)), UsagePoint(5, 0, date(2026, 1, 2))]
    b = [UsagePoint(7, 0, date(2026, 1, 1)), UsagePoint(9, 0, date(2026, 1, 3))]
    merged = _merge_points(a, b, period="day")
    assert [(p.start.day, p.total) for p in merged] == [(1, 10), (2, 5), (3, 9)]


def test_parse_vnstat_payload():
    payload = {
        "interfaces": [
            {
                "name": "eth0",
                "created": {"timestamp": 1_700_000_000},
                "traffic": {
                    "total": {"rx": 300, "tx": 30},
                    "hour": [
                        {
                            "date": {"year": 2026, "month": 3, "day": 15},
                            "time": {"hour": 14},
                            "rx": 1,
                            "tx": 2,
                        }
                    ],
                    "day": [{"date": {"year": 2026, "month": 3, "day": 15}, "rx": 10, "tx": 20}],
                    "month": [{"date": {"year": 2026, "month": 3}, "rx": 100, "tx": 200}],
                    "year": [{"date": {"year": 2026}, "rx": 300, "tx": 30}],
                },
            }
        ]
    }
    (snap,) = parse_payload(payload)
    assert snap.interface.name == "eth0"
    assert snap.interface.total_rx == 300
    assert snap.interface.created is not None
    assert snap.hour[0].start == datetime(2026, 3, 15, 14)
    assert snap.day[0].start == date(2026, 3, 15) and snap.day[0].total == 30
    assert snap.month[0].label == "2026-03"
    assert snap.year[0].label == "2026"
    assert parse_payload(None) == []


# -- translations -------------------------------------------------------------


def _locale(lang: str) -> dict[str, str]:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def test_arabic_covers_every_english_key():
    missing = sorted(set(_locale("en")) - set(_locale("ar")))
    assert missing == []


def test_translations_keep_placeholders():
    en, ar = _locale("en"), _locale("ar")
    for key, text in en.items():
        if key in ar:
            assert set(re.findall(r"{(\w+)}", text)) == set(re.findall(r"{(\w+)}", ar[key])), key
