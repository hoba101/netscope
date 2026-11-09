# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from netscope import lan
from netscope.netinfo import LocalNetwork

IP_NEIGH = """\
192.168.1.1 dev wlan0 lladdr AA:BB:CC:DD:EE:01 REACHABLE
192.168.1.20 dev wlan0 lladdr aa:bb:cc:dd:ee:20 STALE
192.168.1.30 dev wlan0 FAILED
192.168.1.31 dev wlan0 INCOMPLETE
127.0.0.1 dev lo lladdr 00:00:00:00:00:00 NOARP
"""

ARP_AN = """\
? (10.0.0.1) at 11:22:33:44:55:66 [ether] on eth0
? (10.0.0.9) at <incomplete> on eth0
"""


def test_parse_ip_neigh_keeps_only_usable_entries():
    devices = lan.parse_neighbors(IP_NEIGH)
    assert [d.ip for d in devices] == ["192.168.1.1", "192.168.1.20"]
    first = devices[0]
    assert first.mac == "aa:bb:cc:dd:ee:01"  # normalised to lower case
    assert first.state == "REACHABLE"
    assert first.interface == "wlan0"


def test_parse_arp_format():
    (device,) = lan.parse_neighbors(ARP_AN)
    assert device.ip == "10.0.0.1"
    assert device.mac == "11:22:33:44:55:66"
    assert device.interface == "eth0"


def test_sweep_addresses_excludes_self():
    hosts = lan.sweep_addresses("192.168.1.23/24", "192.168.1.23")
    assert len(hosts) == 253
    assert "192.168.1.23" not in hosts
    assert hosts[0] == "192.168.1.1" and hosts[-1] == "192.168.1.254"


def test_sweep_addresses_narrows_large_subnets_to_own_slash24():
    hosts = lan.sweep_addresses("10.20.0.5/16", "10.20.7.5")
    assert len(hosts) == 253
    assert all(h.startswith("10.20.7.") for h in hosts)


def test_discover_marks_gateway_and_self_and_sorts(monkeypatch):
    monkeypatch.setattr(lan, "read_neighbors", lambda: lan.parse_neighbors(IP_NEIGH))
    monkeypatch.setattr(lan, "resolve_hostnames", lambda ips, timeout=2.0: {"192.168.1.20": "printer.lan"})
    monkeypatch.setattr(lan.socket, "gethostname", lambda: "me")
    swept = []
    monkeypatch.setattr(lan, "ping_sweep", lambda addrs: swept.extend(addrs))

    local = LocalNetwork(ip="192.168.1.50", iface="wlan0", cidr="192.168.1.50/24", gateway="192.168.1.1")
    devices = lan.discover(active=False, local=local)

    assert not swept  # passive scans never ping
    assert [d.ip for d in devices] == ["192.168.1.1", "192.168.1.50", "192.168.1.20"]
    gateway, me, printer = devices
    assert gateway.is_gateway and not gateway.is_self
    assert me.is_self and me.hostname == "me"
    assert printer.hostname == "printer.lan"
    assert printer.usage_note == lan.USAGE_NOTE


def test_active_discover_sweeps_subnet(monkeypatch):
    monkeypatch.setattr(lan, "read_neighbors", list)
    monkeypatch.setattr(lan, "resolve_hostnames", lambda ips, timeout=2.0: {})
    monkeypatch.setattr(lan, "is_linux", lambda: True)
    swept = []
    monkeypatch.setattr(lan, "ping_sweep", lambda addrs: swept.extend(addrs))

    lan.discover(active=True, local=LocalNetwork(ip="10.0.0.2", cidr="10.0.0.2/30"))
    assert swept == ["10.0.0.1"]
