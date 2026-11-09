# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Permission/capability inspection and elevation helpers.

NetScope requests elevated privileges only for explicit privileged actions
(reading restricted vnStat paths, applying tc/nft/nmcli controls, installing
system services). It never silently escalates.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

from .utils import is_linux, is_windows


@dataclass
class CapabilityReport:
    platform: str
    is_admin: bool = False
    can_read_vnstat_db: bool = False
    has_vnstat: bool = False
    has_vnstatd_service: bool = False
    has_nmcli: bool = False
    has_tc: bool = False
    has_nft: bool = False
    has_iproute: bool = False
    has_pkexec: bool = False
    has_systemctl: bool = False
    has_powershell: bool = False
    has_netsh: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return self.__dict__.copy()


def is_admin() -> bool:
    if is_windows():
        try:
            import ctypes  # type: ignore
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            try:
                out = subprocess.check_output(
                    ["net", "session"], stderr=subprocess.DEVNULL, text=True, timeout=3
                )
                return True
            except Exception:
                return False
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def scan() -> CapabilityReport:
    rep = CapabilityReport(platform="windows" if is_windows() else ("linux" if is_linux() else "other"))
    rep.is_admin = is_admin()
    rep.has_vnstat = shutil.which("vnstat") is not None
    rep.has_nmcli = shutil.which("nmcli") is not None
    rep.has_tc = shutil.which("tc") is not None
    rep.has_nft = shutil.which("nft") is not None
    rep.has_iproute = shutil.which("ip") is not None
    rep.has_pkexec = shutil.which("pkexec") is not None
    rep.has_systemctl = shutil.which("systemctl") is not None
    rep.has_powershell = shutil.which("powershell") is not None or shutil.which("pwsh") is not None
    rep.has_netsh = shutil.which("netsh") is not None
    for path in ("/var/lib/vnstat/vnstat.db", "/var/db/vnstat/vnstat.db"):
        if os.path.exists(path) and os.access(path, os.R_OK):
            rep.can_read_vnstat_db = True
            break
    if is_linux() and rep.has_systemctl:
        try:
            out = subprocess.check_output(["systemctl", "is-enabled", "vnstat"], text=True, stderr=subprocess.DEVNULL, timeout=3).strip()
            rep.has_vnstatd_service = out in ("enabled", "static", "indirect", "alias")
        except Exception:
            pass
    if is_linux() and not rep.has_tc:
        rep.notes.append("iproute-tc is not installed; speed throttling via tc is unavailable until it is installed.")
    if is_linux() and not rep.can_read_vnstat_db and rep.has_vnstat:
        rep.notes.append("vnStat exists but its DB is not directly readable; NetScope uses vnstat JSON and can use a privileged helper for DB recovery.")
    if is_windows() and not rep.is_admin:
        rep.notes.append("Some Windows controls (firewall/adapter actions) require Administrator consent.")
    return rep


def run_privileged(argv: list[str], *, prompt: str = "") -> subprocess.CompletedProcess:
    """Run a NetScope helper command with elevation.

    On Linux uses pkexec when available; on Windows the caller should relaunch
    elevated. This function only executes the bundled netscope helper.
    """
    if not argv:
        raise ValueError("argv required")
    if is_windows():
        return subprocess.run(argv, text=True, capture_output=True)
    if is_admin():
        return subprocess.run(argv, text=True, capture_output=True)
    if shutil.which("pkexec"):
        cmd = ["pkexec", *argv]
        return subprocess.run(cmd, text=True, capture_output=True)
    return subprocess.run(["sudo", *argv], text=True, capture_output=True)
