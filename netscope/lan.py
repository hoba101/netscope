# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local network device discovery.

Important: on a switched LAN, a normal endpoint cannot accurately measure other
devices' internet usage. Per-device internet usage requires monitoring at the
gateway/router, port mirroring, or explicit accounting rules on the device that
forwards traffic. This module only answers "which devices are on my network".
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .netinfo import LocalNetwork, local_network, run
from .utils import is_linux

USAGE_NOTE = "requires gateway/router accounting or port mirroring"
MAX_SWEEP_HOSTS = 254  # larger subnets are narrowed to the /24 around this host

_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC = re.compile(r"\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", re.I)
_STATE = re.compile(r"\b(REACHABLE|STALE|DELAY|PROBE|FAILED|PERMANENT|INCOMPLETE|NOARP)\b")
_DEV = re.compile(r"\b(?:dev|on)\s+(\S+)")
_UNUSABLE_STATES = {"FAILED", "INCOMPLETE"}


@dataclass
class LanDevice:
    ip: str
    mac: str = ""
    hostname: str = ""
    state: str = ""
    interface: str = ""
    is_self: bool = False
    is_gateway: bool = False
    usage_note: str = ""
    last_seen: float = 0.0


def parse_neighbors(text: str) -> list[LanDevice]:
    """Parse ``ip -4 neigh show`` or ``arp -an`` output into devices.

    Loopback addresses and entries that never resolved (FAILED/INCOMPLETE) are dropped.
    """
    devices = []
    for line in text.splitlines():
        ip_m = _IPV4.search(line)
        if not ip_m or ip_m.group(1).startswith("127."):
            continue
        state_m = _STATE.search(line)
        state = state_m.group(1) if state_m else ""
        if state in _UNUSABLE_STATES or "<incomplete>" in line:
            continue
        mac_m = _MAC.search(line)
        dev_m = _DEV.search(line)
        devices.append(
            LanDevice(
                ip=ip_m.group(1),
                mac=mac_m.group(1).lower() if mac_m else "",
                state=state,
                interface=dev_m.group(1) if dev_m else "",
            )
        )
    return devices


def read_neighbors() -> list[LanDevice]:
    out = run(["ip", "-4", "neigh", "show"])
    if not out:
        out = run(["arp", "-an"])
    return parse_neighbors(out)


def sweep_addresses(cidr: str, own_ip: str, limit: int = MAX_SWEEP_HOSTS) -> list[str]:
    """Host addresses to ping for an active scan (never more than ``limit``)."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses - 2 > limit and own_ip:
        net = ipaddress.ip_network(f"{own_ip}/24", strict=False)
    return [str(h) for h in net.hosts() if str(h) != own_ip][:limit]


def _ping_once(ip: str) -> None:
    try:
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        pass  # unreachable hosts are the normal case in a sweep


def ping_sweep(addresses: list[str], workers: int = 64) -> None:
    """Ping every address once so the kernel fills its neighbor table."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_ping_once, addresses))


def resolve_hostnames(ips: list[str], timeout: float = 2.0) -> dict[str, str]:
    """Reverse-DNS lookups in parallel, giving up on stragglers after ``timeout``."""
    names: dict[str, str] = {}

    def lookup(ip: str) -> None:
        try:
            name = socket.gethostbyaddr(ip)[0]
        except OSError:
            return
        if name and name != ip:
            names[ip] = name

    # Daemon threads so a slow resolver can never block interpreter exit.
    threads = [threading.Thread(target=lookup, args=(ip,), daemon=True) for ip in ips]
    for th in threads:
        th.start()
    deadline = time.monotonic() + timeout
    for th in threads:
        th.join(max(0.0, deadline - time.monotonic()))
    return dict(names)


def _sort_key(d: LanDevice):
    rank = 0 if d.is_gateway else 1 if d.is_self else 2
    return (rank, int(ipaddress.ip_address(d.ip)))


def discover(active: bool = False, local: LocalNetwork | None = None) -> list[LanDevice]:
    """List devices on the local network.

    The passive scan only reads the neighbor table. ``active=True`` first pings
    every address in the subnet (Linux only), which finds quiet devices too.
    """
    local = local or local_network()
    if active and local.cidr and is_linux():
        ping_sweep(sweep_addresses(local.cidr, local.ip))

    now = time.time()
    devices: dict[str, LanDevice] = {}
    if local.ip:
        devices[local.ip] = LanDevice(
            ip=local.ip,
            hostname=socket.gethostname(),
            state="local",
            interface=local.iface,
            is_self=True,
            last_seen=now,
        )
    for dev in read_neighbors():
        if dev.ip in devices:
            continue
        dev.last_seen = now
        dev.is_gateway = dev.ip == local.gateway
        dev.usage_note = USAGE_NOTE
        devices[dev.ip] = dev

    names = resolve_hostnames([ip for ip, d in devices.items() if not d.is_self])
    for ip, name in names.items():
        devices[ip].hostname = name
    return sorted(devices.values(), key=_sort_key)
