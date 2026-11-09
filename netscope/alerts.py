# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import storage
from .quota import evaluate as evaluate_quota
from .utils import fmt_bytes, is_linux, is_windows

# in-process state for sustained conditions
_low_speed_since: dict[str, float] = {}


def _notify(title: str, body: str):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "NetScope", title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def _net_signature(iface: str) -> dict:
    sig = {"iface": iface, "operstate": "", "connection": "", "gateway": "", "ips": []}
    if is_linux():
        try:
            sig["operstate"] = (Path(f"/sys/class/net/{iface}/operstate")).read_text(errors="ignore").strip()
        except Exception:
            pass
        if shutil.which("nmcli"):
            try:
                out = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "dev", "status"], text=True, stderr=subprocess.DEVNULL, timeout=4)
                for line in out.splitlines():
                    p = line.split(":")
                    if p and p[0] == iface:
                        sig["connection"] = p[2] if len(p) > 2 else ""
                        sig["operstate"] = sig["operstate"] or (p[1] if len(p) > 1 else "")
            except Exception:
                pass
            try:
                out = subprocess.check_output(["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL, timeout=3)
                for part in out.split():
                    if part.count(".") == 3: sig["gateway"] = part; break
            except Exception:
                pass
    return sig


def _hour_usage_bytes(snap):
    today = date.today(); now = datetime.now()
    for p in reversed(getattr(snap, "hour", []) or []):
        d = getattr(p.start, "year", None)
        if d and p.start.year == today.year and p.start.month == today.month and p.start.day == today.day and p.start.hour == now.hour:
            return int(p.rx) + int(p.tx)
    return 0


def evaluate(snap, settings, live_rx_bps: float = 0.0, live_tx_bps: float = 0.0, do_notify: bool = True) -> list[dict]:
    if not settings.alerts_enabled or not snap:
        return []
    iface = snap.interface.name
    fired = []
    notify_ok = do_notify and settings.alert_desktop_notify

    def fire(kind, severity, title, message, value="", dedup="", cooldown=0):
        if storage.add_alert(kind, severity, title, message, iface, value, dedup_key=dedup, cooldown_sec=cooldown):
            item = {"kind": kind, "severity": severity, "title": title, "message": message, "interface": iface, "value": value}
            fired.append(item)
            if notify_ok:
                _notify(title, message)

    # Daily quota
    if settings.quota_enabled and settings.alert_daily_enabled:
        q = evaluate_quota(snap, settings)
        if q.exceeded:
            fire("daily_quota", "critical", "Daily quota exceeded", q.message, f"{q.percent:.1f}%", dedup=f"daily-exceeded-{iface}-{date.today()}", cooldown=3600)
        elif q.warn:
            fire("daily_quota", "warning", "Daily quota warning", q.message, f"{q.percent:.1f}%", dedup=f"daily-warn-{iface}-{date.today()}", cooldown=1800)

    # Hourly limit
    if settings.alert_hourly_enabled:
        limit = max(1, int(settings.alert_hourly_mb)) * 1024 * 1024
        used = _hour_usage_bytes(snap)
        pct = used / limit * 100.0
        warn_at = max(1, min(100, int(settings.alert_hourly_warn_percent)))
        hour_key = datetime.now().strftime("%Y%m%d%H")
        if used >= limit:
            fire("hourly_quota", "critical", "Hourly limit exceeded", f"Used {fmt_bytes(used)} ({pct:.1f}%) of {fmt_bytes(limit)} this hour on {iface}.", f"{pct:.1f}%", dedup=f"hourly-exceeded-{iface}-{hour_key}", cooldown=1800)
        elif pct >= warn_at:
            fire("hourly_quota", "warning", "Hourly limit warning", f"Used {fmt_bytes(used)} ({pct:.1f}%) of {fmt_bytes(limit)} this hour on {iface}.", f"{pct:.1f}%", dedup=f"hourly-warn-{iface}-{hour_key}", cooldown=900)

    # Network state / disconnection / change
    sig = _net_signature(iface)
    sig_key = json.dumps(sig, sort_keys=True)
    prev = storage.get_state(f"net:{iface}")
    state = (sig.get("operstate") or "").lower()
    disconnected = state in ("down", "lowerlayerdown", "dormant") or (is_linux() and state == "unknown" and not sig.get("connection") and shutil.which("nmcli") is not None)
    # better: nmcli disconnected state
    if shutil.which("nmcli"):
        try:
            out = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,STATE", "dev", "status"], text=True, stderr=subprocess.DEVNULL, timeout=4)
            for line in out.splitlines():
                if line.startswith(iface+":"):
                    st = line.split(":",1)[1].lower(); disconnected = ("disconnected" in st) or ("unavailable" in st)
        except Exception: pass
    if settings.alert_disconnect_enabled and disconnected:
        fire("disconnect", "critical", "Network disconnected", f"Interface {iface} appears disconnected.", state, dedup=f"disconnect-{iface}", cooldown=120)
    if prev and prev != sig_key and settings.alert_network_change_enabled:
        try:
            old = json.loads(prev)
            changes = []
            for k in ("iface","operstate","connection","gateway"):
                if old.get(k) != sig.get(k): changes.append(f"{k}: {old.get(k,'')} → {sig.get(k,'')}")
            if changes:
                fire("network_change", "info", "Network changed", f"{iface}: " + "; ".join(changes)[:300], ";".join(changes)[:200], dedup=f"netchange-{iface}-{hash(sig_key)}", cooldown=60)
        except Exception:
            fire("network_change", "info", "Network changed", f"Network state changed for {iface}.", sig_key[:200], dedup=f"netchange-{iface}-{hash(sig_key)}", cooldown=60)
    storage.set_state(f"net:{iface}", sig_key)

    # Low speed while supposedly connected
    if settings.alert_low_speed_enabled and not disconnected:
        bps = float(live_rx_bps) + float(live_tx_bps)
        thresh = max(1, int(settings.alert_low_speed_kbps)) * 1000.0
        now = time.monotonic()
        key = iface
        # only evaluate if we have a real measurement; treat 0 as unknown at startup, but sustained 0 while previously active?
        if bps > 0 and bps < thresh:
            _low_speed_since.setdefault(key, now)
            if now - _low_speed_since[key] >= max(3, int(settings.alert_low_speed_seconds)):
                fire("low_speed", "warning", "Low network speed", f"Current speed is about {fmt_bytes(bps, rate=True)} on {iface} (threshold {settings.alert_low_speed_kbps} kbps).", fmt_bytes(bps, rate=True), dedup=f"lowspeed-{iface}", cooldown=300)
                _low_speed_since[key] = now  # avoid immediate repeat after cooldown logic nuance
        else:
            _low_speed_since.pop(key, None)

    return fired
