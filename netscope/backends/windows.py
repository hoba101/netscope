# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows data sources.

Current counters are read via psutil when available, or PowerShell as fallback.
Windows does not expose detailed per-hour history by default; NetScope stores its
own history over time and can display what the OS/API provides.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass

from ..utils import is_windows

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


@dataclass
class CounterSample:
    iface: str
    rx_bytes: int
    tx_bytes: int
    mono: float


_last: dict[str, CounterSample] = {}


def available() -> bool:
    return is_windows()


def list_interfaces() -> list[str]:
    if not is_windows():
        return []
    if psutil is not None:
        try:
            stats = psutil.net_io_counters(pernic=True)
            names = sorted(
                stats.keys(), key=lambda n: (n.lower().startswith("loopback"), n.lower() == "lo", n)
            )
            return names
        except Exception:
            pass
    return _powershell_interfaces()


def _powershell_interfaces() -> list[str]:
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress",
        ]
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=10)
        data = json.loads(raw)
        if isinstance(data, str):
            return [data]
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def read_counters(iface: str | None = None) -> tuple[str, int, int] | None:
    if not is_windows():
        return None
    if psutil is not None:
        try:
            stats = psutil.net_io_counters(pernic=True)
            if iface and iface in stats:
                s = stats[iface]
                return iface, int(s.bytes_recv), int(s.bytes_sent)
            # pick most active non-loopback
            candidates = [
                (n, s) for n, s in stats.items() if "loopback" not in n.lower() and n.lower() != "lo"
            ]
            if not candidates:
                candidates = list(stats.items())
            if candidates:
                n, s = max(candidates, key=lambda item: item[1].bytes_recv + item[1].bytes_sent)
                return n, int(s.bytes_recv), int(s.bytes_sent)
        except Exception:
            pass
    return _powershell_counters(iface)


def _powershell_counters(iface: str | None) -> tuple[str, int, int] | None:
    try:
        name_filter = f"-Name '{iface}'" if iface else ""
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-NetAdapterStatistics {name_filter} | Select-Object Name,ReceivedBytes,SentBytes | ConvertTo-Json -Compress",
        ]
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=10)
        data = json.loads(raw)
        if isinstance(data, list):
            data = data[0] if data else None
        if isinstance(data, dict):
            return (
                str(data.get("Name", iface or "?")),
                int(data.get("ReceivedBytes", 0)),
                int(data.get("SentBytes", 0)),
            )
    except Exception:
        pass
    return None


def read_live_rates(iface: str) -> tuple[float, float] | None:
    sample = read_counters(iface)
    if sample is None:
        return None
    name, rx, tx = sample
    now = time.monotonic()
    prev = _last.get(name)
    _last[name] = CounterSample(name, rx, tx, now)
    if prev is None or now <= prev.mono:
        return None
    dt = now - prev.mono
    drx = rx - prev.rx_bytes
    dtx = tx - prev.tx_bytes
    if drx < 0 or dtx < 0 or dt > 30:
        return None
    return drx * 8.0 / dt, dtx * 8.0 / dt
