# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from . import storage
from .i18n import t
from .quota import evaluate as evaluate_quota
from .utils import fmt_bytes, is_linux

# in-process state for sustained conditions
_low_speed_since: dict[str, float] = {}


def _notify(title: str, body: str):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "NetScope", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "dev", "status"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                )
                for line in out.splitlines():
                    p = line.split(":")
                    if p and p[0] == iface:
                        sig["connection"] = p[2] if len(p) > 2 else ""
                        sig["operstate"] = sig["operstate"] or (p[1] if len(p) > 1 else "")
            except Exception:
                pass
            try:
                out = subprocess.check_output(
                    ["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL, timeout=3
                )
                for part in out.split():
                    if part.count(".") == 3:
                        sig["gateway"] = part
                        break
            except Exception:
                pass
    return sig


def _hour_usage_bytes(snap):
    today = date.today()
    now = datetime.now()
    for p in reversed(getattr(snap, "hour", []) or []):
        d = getattr(p.start, "year", None)
        if (
            d
            and p.start.year == today.year
            and p.start.month == today.month
            and p.start.day == today.day
            and p.start.hour == now.hour
        ):
            return int(p.rx) + int(p.tx)
    return 0


def evaluate(
    snap, settings, live_rx_bps: float = 0.0, live_tx_bps: float = 0.0, do_notify: bool = True
) -> list[dict]:
    """Check every alert rule, store new alerts and return them.

    Titles/messages are translated at fire time. ``do_notify`` sends a
    ``notify-send`` notification (the GUI passes False and uses Gio instead).
    """
    if not settings.alerts_enabled or not snap:
        return []
    iface = snap.interface.name
    fired = []
    notify_ok = do_notify and settings.alert_desktop_notify

    def fire(kind, severity, title, message, value="", dedup="", cooldown=0):
        if storage.add_alert(
            kind, severity, title, message, iface, value, dedup_key=dedup, cooldown_sec=cooldown
        ):
            fired.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "title": title,
                    "message": message,
                    "interface": iface,
                    "value": value,
                }
            )
            if notify_ok:
                _notify(title, message)

    today = date.today()
    if settings.quota_enabled and settings.alert_daily_enabled:
        q = evaluate_quota(snap, settings)
        if q.exceeded:
            fire(
                "daily_quota",
                "critical",
                t("alert.daily_exceeded"),
                q.message,
                f"{q.percent:.1f}%",
                dedup=f"daily-exceeded-{iface}-{today}",
                cooldown=3600,
            )
        elif q.warn:
            fire(
                "daily_quota",
                "warning",
                t("alert.daily_warn"),
                q.message,
                f"{q.percent:.1f}%",
                dedup=f"daily-warn-{iface}-{today}",
                cooldown=1800,
            )

    if settings.alert_hourly_enabled:
        limit = max(1, int(settings.alert_hourly_mb)) * 1024 * 1024
        used = _hour_usage_bytes(snap)
        pct = used / limit * 100.0
        hour_key = datetime.now().strftime("%Y%m%d%H")
        message = t(
            "alert.hourly_msg",
            used=fmt_bytes(used),
            percent=f"{pct:.1f}",
            limit=fmt_bytes(limit),
            iface=iface,
        )
        if used >= limit:
            fire(
                "hourly_quota",
                "critical",
                t("alert.hourly_exceeded"),
                message,
                f"{pct:.1f}%",
                dedup=f"hourly-exceeded-{iface}-{hour_key}",
                cooldown=1800,
            )
        elif pct >= max(1, min(100, int(settings.alert_hourly_warn_percent))):
            fire(
                "hourly_quota",
                "warning",
                t("alert.hourly_warn"),
                message,
                f"{pct:.1f}%",
                dedup=f"hourly-warn-{iface}-{hour_key}",
                cooldown=900,
            )

    # Network state / disconnection / change
    sig = _net_signature(iface)
    sig_key = json.dumps(sig, sort_keys=True)
    prev = storage.get_state(f"net:{iface}")
    state = (sig.get("operstate") or "").lower()
    disconnected = state in ("down", "lowerlayerdown", "dormant")
    if shutil.which("nmcli"):
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "DEVICE,STATE", "dev", "status"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            for line in out.splitlines():
                if line.startswith(iface + ":"):
                    st = line.split(":", 1)[1].lower()
                    disconnected = "disconnected" in st or "unavailable" in st
        except (OSError, subprocess.SubprocessError):
            pass
    if settings.alert_disconnect_enabled and disconnected:
        fire(
            "disconnect",
            "critical",
            t("alert.disconnected"),
            t("alert.disconnected_msg", iface=iface),
            state,
            dedup=f"disconnect-{iface}",
            cooldown=120,
        )
    if prev and prev != sig_key and settings.alert_network_change_enabled:
        try:
            old = json.loads(prev)
        except ValueError:
            old = {}
        changes = [
            f"{k}: {old.get(k, '')} → {sig.get(k, '')}"
            for k in ("iface", "operstate", "connection", "gateway")
            if old.get(k) != sig.get(k)
        ]
        if changes:
            fire(
                "network_change",
                "info",
                t("alert.network_changed"),
                f"{iface}: " + "; ".join(changes)[:300],
                ";".join(changes)[:200],
                dedup=f"netchange-{iface}-{hash(sig_key)}",
                cooldown=60,
            )
    storage.set_state(f"net:{iface}", sig_key)

    # Low speed while connected (0 is treated as "no measurement yet").
    if settings.alert_low_speed_enabled and not disconnected:
        bps = float(live_rx_bps) + float(live_tx_bps)
        threshold = max(1, int(settings.alert_low_speed_kbps)) * 1000.0
        now = time.monotonic()
        if 0 < bps < threshold:
            _low_speed_since.setdefault(iface, now)
            if now - _low_speed_since[iface] >= max(3, int(settings.alert_low_speed_seconds)):
                speed = fmt_bytes(bps, rate=True)
                fire(
                    "low_speed",
                    "warning",
                    t("alert.low_speed"),
                    t(
                        "alert.low_speed_msg",
                        speed=speed,
                        iface=iface,
                        threshold=settings.alert_low_speed_kbps,
                    ),
                    speed,
                    dedup=f"lowspeed-{iface}",
                    cooldown=300,
                )
                _low_speed_since[iface] = now
        else:
            _low_speed_since.pop(iface, None)

    return fired
