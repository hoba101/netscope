# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from netscope import netinfo, speedtest


def test_parse_default_route():
    text = "default via 192.168.1.1 dev wlan0 proto dhcp src 192.168.1.50 metric 600\n"
    assert netinfo.parse_default_route(text) == ("192.168.1.1", "wlan0")


def test_parse_default_route_without_gateway():
    assert netinfo.parse_default_route("default dev wg0 scope link\n") == ("", "wg0")
    assert netinfo.parse_default_route("") == ("", "")


def test_parse_inet():
    text = "3: wlan0    inet 192.168.1.50/24 brd 192.168.1.255 scope global dynamic wlan0\n"
    assert netinfo.parse_inet(text) == "192.168.1.50/24"
    assert netinfo.parse_inet("") == ""


def test_link_info_reads_sysfs(tmp_path):
    (tmp_path / "eth0").mkdir()
    (tmp_path / "eth0" / "operstate").write_text("up\n")
    (tmp_path / "eth0" / "speed").write_text("1000\n")
    (tmp_path / "wlan0").mkdir()
    (tmp_path / "wlan0" / "operstate").write_text("dormant\n")

    assert netinfo.link_info("eth0", tmp_path) == {"operstate": "up", "speed": "1000"}
    assert netinfo.link_info("wlan0", tmp_path) == {"operstate": "dormant"}
    assert netinfo.link_info("missing", tmp_path) == {}


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "3 packets transmitted, 3 received, 0% packet loss\nrtt min/avg/max/mdev = 9.1/10.2/11.3/0.8 ms\n",
            "9.1/10.2/11.3/0.8 ms",
        ),
        ("round-trip min/avg/max/stddev = 1.0/2.0/3.0/0.5 ms\n", "1.0/2.0/3.0/0.5 ms"),
        ("3 packets transmitted, 0 received, 100% packet loss\n", None),
    ],
)
def test_parse_ping_summary(output, expected):
    assert speedtest.parse_ping_summary(output) == expected


def test_download_result_rates():
    result = speedtest.DownloadResult(total_bytes=25_000_000, seconds=2.0)
    assert result.mbit_per_s == pytest.approx(100.0)
    assert result.mbyte_per_s == pytest.approx(12.5)
    assert speedtest.DownloadResult(10, 0).mbit_per_s > 0  # no division by zero


def test_ping_targets_put_gateway_first(monkeypatch):
    monkeypatch.setattr(speedtest, "run", lambda cmd, timeout=5: "default via 10.0.0.1 dev eth0\n")
    assert speedtest.ping_targets()[0] == ("gateway", "10.0.0.1")
    monkeypatch.setattr(speedtest, "run", lambda cmd, timeout=5: "")
    assert speedtest.ping_targets() == list(speedtest.PUBLIC_TARGETS)
