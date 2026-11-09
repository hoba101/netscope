# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..utils import is_linux


@dataclass
class CounterSample:
    iface: str
    rx_bytes: int
    tx_bytes: int
    mono: float


_last: dict[str, CounterSample] = {}


def default_interface() -> str | None:
    if not is_linux():
        return None
    for cmd in (["ip", "route", "get", "1.1.1.1"], ["ip", "route", "show", "default"]):
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=2)
            m = re.search(r"\bdev\s+(\S+)", out)
            if m:
                return m.group(1)
        except Exception:
            pass
    try:
        for path in sorted(Path("/sys/class/net").iterdir()):
            name = path.name
            if name != "lo" and (path / "operstate").exists():
                state = (path / "operstate").read_text(errors="ignore").strip()
                if state == "up":
                    return name
    except Exception:
        pass
    return None


def list_interfaces() -> list[str]:
    if not is_linux():
        return []
    try:
        names = [p.name for p in Path("/sys/class/net").iterdir() if p.is_dir() or p.is_symlink()]
        names.sort(key=lambda n: (n == "lo", n))
        return names
    except Exception:
        return []


def read_counters(iface: str) -> tuple[int, int] | None:
    base = Path("/sys/class/net") / iface / "statistics"
    try:
        rx = int((base / "rx_bytes").read_text().strip())
        tx = int((base / "tx_bytes").read_text().strip())
        return rx, tx
    except Exception:
        return None


def read_live_rates(iface: str) -> tuple[float, float] | None:
    counters = read_counters(iface)
    if counters is None:
        return None
    rx, tx = counters
    now = time.monotonic()
    prev = _last.get(iface)
    _last[iface] = CounterSample(iface, rx, tx, now)
    if prev is None or now <= prev.mono:
        return None
    dt = now - prev.mono
    drx = rx - prev.rx_bytes
    dtx = tx - prev.tx_bytes
    if drx < 0 or dtx < 0 or dt > 30:
        return None
    return drx * 8.0 / dt, dtx * 8.0 / dt
