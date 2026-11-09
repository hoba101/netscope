# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers for reading this machine's routing/address info on Linux."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_ROUTE = re.compile(r"^default\s+via\s+(\d{1,3}(?:\.\d{1,3}){3})(?:.*?\bdev\s+(\S+))?", re.M)
_DEV = re.compile(r"\bdev\s+(\S+)")
_INET = re.compile(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})")


@dataclass
class LocalNetwork:
    ip: str = ""
    iface: str = ""
    cidr: str = ""  # e.g. "192.168.1.23/24"
    gateway: str = ""


def run(cmd: list[str], timeout: float = 5) -> str:
    """Run a command and return stdout, or "" if it is missing or fails."""
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("command %s failed: %s", cmd, exc)
        return ""


def parse_default_route(text: str) -> tuple[str, str]:
    """Return ``(gateway, iface)`` from ``ip -4 route show default`` output."""
    m = _DEFAULT_ROUTE.search(text)
    if m:
        return m.group(1), m.group(2) or ""
    m = _DEV.search(text)
    return "", m.group(1) if m else ""


def parse_inet(text: str) -> str:
    """Return the first IPv4 address with prefix from ``ip -4 -o addr`` output."""
    m = _INET.search(text)
    return m.group(1) if m else ""


def local_network() -> LocalNetwork:
    info = LocalNetwork()
    info.gateway, info.iface = parse_default_route(run(["ip", "-4", "route", "show", "default"]))
    if info.iface:
        info.cidr = parse_inet(run(["ip", "-4", "-o", "addr", "show", "dev", info.iface]))
        info.ip = info.cidr.split("/")[0]
    return info


def link_info(iface: str, sys_net: Path = Path("/sys/class/net")) -> dict[str, str]:
    """Operational state and link speed (Mbps) from sysfs, when available."""
    base = sys_net / iface
    info: dict[str, str] = {}
    for key, name in (("operstate", "operstate"), ("speed", "speed")):
        try:
            info[key] = (base / name).read_text().strip()
        except OSError:
            pass  # missing on virtual/wireless links or non-Linux
    return info
