# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI routing, plus GTK-dependent helpers (skipped when GTK is unavailable)."""

import json

import pytest

from netscope import __main__ as entry
from netscope import cli, lan


def test_lan_command_prints_devices(monkeypatch, capsys):
    monkeypatch.setattr(
        lan, "discover", lambda active=False: [lan.LanDevice(ip="10.0.0.1", is_gateway=active)]
    )
    assert cli.run(["lan", "--active"]) == 0
    (device,) = json.loads(capsys.readouterr().out)
    assert device["ip"] == "10.0.0.1" and device["is_gateway"] is True


def test_lan_is_routed_to_cli_not_gui(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "run", lambda argv: seen.append(argv) or 0)
    monkeypatch.setattr(entry.sys, "argv", ["netscope", "lan"])
    assert entry.main() == 0
    assert seen == [["lan"]]


def test_help_mentions_lan(capsys):
    assert cli.run(["--help"]) == 0
    assert "lan" in capsys.readouterr().out


@pytest.fixture
def widgets():
    pytest.importorskip("gi")
    try:
        from netscope.ui import widgets
    except (ImportError, ValueError) as exc:
        pytest.skip(f"GTK 4 / libadwaita unavailable: {exc}")
    return widgets


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 1.0), (-3, 1.0), (90, 100), (100, 120), (1000, 1200), (4.4, 5)],
)
def test_nice_ceiling(widgets, value, expected):
    assert widgets.nice_ceiling(value) == pytest.approx(expected)
