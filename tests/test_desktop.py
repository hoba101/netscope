# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Logic behind the desktop features: history ranges, CSV, speed tests, autostart, i18n."""

import csv
import io
import json
import re
from datetime import date
from pathlib import Path

import pytest

from netscope import alerts, autostart, i18n, series, speedtest, storage
from netscope.models import InterfaceInfo, UsagePoint, UsageSnapshot
from netscope.quota import evaluate
from netscope.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_history_custom_range(snap, now):
    points, step = series.history_points(snap, "day", 90, now)
    assert len(points) == 90 and step == 15
    assert series.history_points(snap, "top", 1, now)[0][0].label == "b"


def test_compare_periods(snap, now):
    # Today (2200) vs yesterday (1100) for a one-day window.
    assert series.compare_periods(snap, "day", 1, now) == (2_200, 1_100)
    assert series.compare_periods(snap, "month", 1, now) == (66_000, 55_000)
    assert series.compare_periods(snap, "year", 1, now) is None


def test_to_csv_round_trips(snap):
    text = series.to_csv(snap.day)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["start", "label", "rx_bytes", "tx_bytes", "total_bytes"]
    assert rows[2] == ["2026-03-15", "", "2000", "200", "2200"]


@pytest.mark.parametrize(
    ("summary", "expected"),
    [("9.1/10.2/11.3/0.8 ms", 10.2), ("no reply", None), (None, None)],
)
def test_parse_ping_avg(summary, expected):
    assert speedtest.parse_ping_avg(summary) == expected


def test_speedtest_history():
    storage.add_speedtest("eth0", 12.5, 94.2, 20.1)
    storage.add_speedtest("eth0", None, 50.0, None)
    latest, first = storage.list_speedtests()
    assert latest["down_mbps"] == 50.0 and latest["ping_ms"] is None
    assert first["ping_ms"] == 12.5


def test_autostart_toggle():
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    entry = autostart.autostart_path().read_text()
    assert "--background" in entry and "Exec=" in entry
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)  # idempotent


def test_new_settings_are_sanitised():
    Settings.path().write_text(json.dumps({"window_width": 5, "run_in_background": 0, "last_page": ""}))
    s = Settings.load()
    assert s.window_width == 360
    assert s.run_in_background is False
    assert s.last_page == "overview"


def test_quota_message_is_translated():
    snap = UsageSnapshot(
        interface=InterfaceInfo(name="eth0"), day=[UsagePoint(200 * 1024 * 1024, 0, date.today())]
    )
    i18n.init("ar")
    q = evaluate(snap, Settings(quota_enabled=True, quota_daily_mb=100))
    assert "تم تجاوز" in q.message and "eth0" in q.message


def test_alert_titles_follow_language(monkeypatch):
    monkeypatch.setattr(alerts, "_net_signature", lambda iface: {"iface": iface, "operstate": "down"})
    monkeypatch.setattr(alerts.shutil, "which", lambda name: None)
    i18n.init("ar")
    snap = UsageSnapshot(interface=InterfaceInfo(name="eth0"))
    fired = alerts.evaluate(snap, Settings(), do_notify=False)
    assert [a["title"] for a in fired] == ["انقطع الاتصال بالشبكة"]


def test_every_translation_key_used_in_code_exists():
    en = json.loads((ROOT / "netscope/data/locales/en.json").read_text(encoding="utf-8"))
    used = set()
    for path in (ROOT / "netscope").rglob("*.py"):
        used |= set(re.findall(r'\bt\(\s*"([a-z_][\w.]*)"', path.read_text(encoding="utf-8")))
    assert sorted(k for k in used if k not in en) == []
