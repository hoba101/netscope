# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Network control actions (throttle, restore, disconnect, adapter state).

Privileged actions are executed through explicit helper commands and should be
confirmed by the user/UI.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

from .utils import is_linux, is_windows


@dataclass
class ActionResult:
    ok: bool
    action: str
    message: str = ""
    output: str = ""
    needs_privilege: bool = False
    capability_missing: str = ""


def capabilities() -> dict:
    return {
        "linux": is_linux(), "windows": is_windows(),
        "tc": shutil.which("tc") is not None,
        "nft": shutil.which("nft") is not None,
        "nmcli": shutil.which("nmcli") is not None,
        "ip": shutil.which("ip") is not None,
        "netsh": shutil.which("netsh") is not None,
        "powershell": shutil.which("powershell") is not None,
    }


def _run(cmd: list[str], timeout=15) -> ActionResult:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return ActionResult(ok=p.returncode == 0, action=" ".join(cmd), message=out.strip()[:2000], output=out)
    except Exception as e:
        return ActionResult(ok=False, action=" ".join(cmd), message=str(e))


def restore_linux(iface: str) -> ActionResult:
    if not is_linux():
        return ActionResult(False, "restore", "Linux only")
    if shutil.which("tc"):
        r = _run(["tc", "qdisc", "del", "dev", iface, "root"])
        # del may fail if no qdisc; treat as restored if common error
        if r.ok or "Cannot delete qdisc with handle of zero" in r.output or "RTNETLINK answers: No such file or directory" in r.output:
            return ActionResult(True, "restore", f"Throttle removed from {iface}.", r.output)
        r.needs_privilege = "Operation not permitted" in r.output or "Permission denied" in r.output
        return r
    return ActionResult(False, "restore", "tc is not installed; no tc throttle to remove.", capability_missing="tc")


def throttle_linux(iface: str, kbit: int) -> ActionResult:
    if not is_linux():
        return ActionResult(False, "throttle", "Linux only")
    if not shutil.which("tc"):
        return ActionResult(False, "throttle", "iproute-tc is not installed. Install it to enable throttling (Fedora: iproute-tc).", capability_missing="tc")
    kbit = max(16, int(kbit))
    # simple root tbf; idempotent by replace attempt
    cmds = [
        ["tc", "qdisc", "replace", "dev", iface, "root", "tbf", "rate", f"{kbit}kbit", "burst", "32kbit", "latency", "400ms"],
    ]
    last = None
    for cmd in cmds:
        last = _run(cmd)
        if not last.ok:
            last.needs_privilege = "Operation not permitted" in last.output or "Permission denied" in last.output
            return last
    return ActionResult(True, "throttle", f"Applied {kbit} kbit/s limit to {iface}.", last.output if last else "")


def disconnect_linux(iface: str = "") -> ActionResult:
    if not is_linux():
        return ActionResult(False, "disconnect", "Linux only")
    if shutil.which("nmcli"):
        if iface:
            r = _run(["nmcli", "device", "disconnect", iface])
        else:
            r = _run(["nmcli", "networking", "off"])
        r.needs_privilege = (not r.ok) and ("not authorized" in r.output.lower() or "permission" in r.output.lower())
        if r.ok:
            r.message = f"Disconnected {'device '+iface if iface else 'networking'} via NetworkManager."
        return r
    return ActionResult(False, "disconnect", "nmcli not available", capability_missing="nmcli")


def connect_linux(iface: str = "") -> ActionResult:
    if not is_linux():
        return ActionResult(False, "connect", "Linux only")
    if shutil.which("nmcli"):
        if iface:
            r = _run(["nmcli", "device", "connect", iface])
        else:
            r = _run(["nmcli", "networking", "on"])
        r.needs_privilege = (not r.ok) and ("not authorized" in r.output.lower() or "permission" in r.output.lower())
        return r
    return ActionResult(False, "connect", "nmcli not available", capability_missing="nmcli")


def status_linux(iface: str) -> dict:
    info = {"interface": iface, "throttled": False, "qdisc": "", "nm_state": ""}
    if shutil.which("tc"):
        r = _run(["tc", "qdisc", "show", "dev", iface])
        info["qdisc"] = r.output.strip()
        info["throttled"] = "tbf" in r.output or "htb" in r.output or "netem" in r.output
    if shutil.which("nmcli"):
        r = _run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "dev", "status"])
        for line in r.output.splitlines():
            if line.startswith(iface + ":"):
                info["nm_state"] = line
    return info


# Windows best-effort (netsh interface set interface is disruptive; firewall rules are broad)
def windows_disable_adapter(iface: str) -> ActionResult:
    if not is_windows() or not shutil.which("powershell"):
        return ActionResult(False, "disable", "Windows PowerShell unavailable")
    r = _run(["powershell", "-NoProfile", "-Command", f"Disable-NetAdapter -Name '{iface}' -Confirm:$false"])
    r.needs_privilege = (not r.ok)
    return r


def windows_enable_adapter(iface: str) -> ActionResult:
    if not is_windows() or not shutil.which("powershell"):
        return ActionResult(False, "enable", "Windows PowerShell unavailable")
    return _run(["powershell", "-NoProfile", "-Command", f"Enable-NetAdapter -Name '{iface}' -Confirm:$false"])
