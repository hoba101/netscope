# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-source sampling to improve confidence in reported usage/speed."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .utils import is_linux, is_windows

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


@dataclass
class ProbeResult:
    source: str
    available: bool
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    rx_bps: float | None = None
    tx_bps: float | None = None
    link_up: bool | None = None
    speed_mbps: int | None = None
    connection: str = ""
    detail: str = ""
    error: str = ""


@dataclass
class AccuracyReport:
    interface: str
    probes: list[ProbeResult] = field(default_factory=list)
    consensus_rx_bytes: int | None = None
    consensus_tx_bytes: int | None = None
    confidence: str = "low"  # low | medium | high

    def as_dict(self):
        return {
            "interface": self.interface,
            "confidence": self.confidence,
            "consensus_rx_bytes": self.consensus_rx_bytes,
            "consensus_tx_bytes": self.consensus_tx_bytes,
            "probes": [p.__dict__ for p in self.probes],
        }


def _psutil_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="psutil", available=psutil is not None)
    if not pr.available:
        return pr
    try:
        stats = psutil.net_io_counters(pernic=True).get(iface)
        if stats:
            pr.rx_bytes, pr.tx_bytes = int(stats.bytes_recv), int(stats.bytes_sent)
        addrs = psutil.net_if_stats().get(iface)
        if addrs:
            pr.link_up = bool(addrs.isup)
            pr.speed_mbps = int(addrs.speed) if addrs.speed else None
    except Exception as e:
        pr.error = str(e)
    return pr


def _sysfs_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="sysfs", available=is_linux())
    if not pr.available:
        return pr
    base = Path("/sys/class/net") / iface
    try:
        pr.rx_bytes = int((base / "statistics/rx_bytes").read_text().strip())
        pr.tx_bytes = int((base / "statistics/tx_bytes").read_text().strip())
        pr.link_up = (base / "operstate").read_text().strip() == "up"
        try:
            speed = (base / "speed").read_text().strip()
            pr.speed_mbps = int(speed) if speed.lstrip('-').isdigit() and int(speed) > 0 else None
        except Exception:
            pass
    except Exception as e:
        pr.error = str(e)
    return pr


def _procfs_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="procfs", available=is_linux())
    try:
        for line in Path("/proc/net/dev").read_text(errors="ignore").splitlines()[2:]:
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            if name.strip() != iface:
                continue
            parts = rest.split()
            if len(parts) >= 9:
                pr.rx_bytes = int(parts[0]); pr.tx_bytes = int(parts[8])
            break
    except Exception as e:
        pr.error = str(e)
    return pr


def _ip_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="ip -s link", available=is_linux() and shutil.which("ip") is not None)
    if not pr.available:
        return pr
    try:
        out = subprocess.check_output(["ip", "-s", "link", "show", "dev", iface], text=True, stderr=subprocess.DEVNULL, timeout=4)
        nums = []
        for line in out.splitlines():
            s = line.strip()
            if s and (s[0].isdigit() or s.startswith('RX') or s.startswith('TX')):
                nums.extend([int(x) for x in s.replace('RX:','').replace('TX:','').split() if x.lstrip('-').isdigit()])
        # ip -s output has RX bytes packets ... then TX bytes packets ...
        # heuristic: find 'RX:' line and next numeric line, TX similar.
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("RX:"):
                rx = lines[i+1].split(); pr.rx_bytes = int(rx[0]) if rx else pr.rx_bytes
            if line.strip().startswith("TX:"):
                tx = lines[i+1].split(); pr.tx_bytes = int(tx[0]) if tx else pr.tx_bytes
        pr.link_up = "state UP" in out or ",UP" in out
    except Exception as e:
        pr.error = str(e)
    return pr


def _nmcli_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="nmcli", available=shutil.which("nmcli") is not None)
    if not pr.available:
        return pr
    try:
        out = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"], text=True, stderr=subprocess.DEVNULL, timeout=4)
        for line in out.splitlines():
            parts = line.split(":")
            if parts and parts[0] == iface:
                pr.link_up = "connected" in (parts[2] if len(parts)>2 else "")
                pr.connection = parts[3] if len(parts)>3 else ""
                pr.detail = ":".join(parts[1:])
                break
    except Exception as e:
        pr.error = str(e)
    return pr


def _windows_probe(iface: str) -> ProbeResult:
    pr = ProbeResult(source="windows-powershell", available=is_windows() and (shutil.which("powershell") is not None))
    if not pr.available:
        return pr
    try:
        cmd = ["powershell", "-NoProfile", "-Command", f"Get-NetAdapterStatistics -Name '{iface}' | Select-Object ReceivedBytes,SentBytes | ConvertTo-Json -Compress"]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=8)
        data = json.loads(out)
        if isinstance(data, list): data = data[0]
        pr.rx_bytes = int(data.get("ReceivedBytes", 0)); pr.tx_bytes = int(data.get("SentBytes", 0))
    except Exception as e:
        pr.error = str(e)
    return pr


def collect(iface: str) -> AccuracyReport:
    rep = AccuracyReport(interface=iface)
    probes = [_psutil_probe(iface), _sysfs_probe(iface), _procfs_probe(iface), _ip_probe(iface), _nmcli_probe(iface), _windows_probe(iface)]
    rep.probes = [p for p in probes if p.available or p.error]
    rx_vals = [p.rx_bytes for p in rep.probes if isinstance(p.rx_bytes, int) and p.rx_bytes >= 0]
    tx_vals = [p.tx_bytes for p in rep.probes if isinstance(p.tx_bytes, int) and p.tx_bytes >= 0]
    if rx_vals:
        rep.consensus_rx_bytes = max(set(rx_vals), key=rx_vals.count) if len(set(rx_vals)) != len(rx_vals) else int(sum(rx_vals)/len(rx_vals))
    if tx_vals:
        rep.consensus_tx_bytes = max(set(tx_vals), key=tx_vals.count) if len(set(tx_vals)) != len(tx_vals) else int(sum(tx_vals)/len(tx_vals))
    agreeing = sum(1 for p in rep.probes if p.rx_bytes is not None and rep.consensus_rx_bytes is not None and abs(p.rx_bytes-rep.consensus_rx_bytes) <= max(4096, rep.consensus_rx_bytes*0.001))
    if agreeing >= 3: rep.confidence = "high"
    elif agreeing >= 2 or len(rx_vals) >= 2: rep.confidence = "medium"
    return rep
