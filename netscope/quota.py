# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass

from .i18n import t
from .series import usage_today
from .settings import Settings


@dataclass
class QuotaStatus:
    enabled: bool
    interface: str
    used_bytes: int
    limit_bytes: int
    percent: float
    warn: bool
    exceeded: bool
    action: str
    message: str


def today_usage_bytes(snap) -> int:
    point = usage_today(snap)
    return int(point.rx) + int(point.tx) if point else 0


def evaluate(snap, settings: Settings) -> QuotaStatus:
    iface = settings.quota_interface or (snap.interface.name if snap else "")
    limit = max(1, int(settings.quota_daily_mb)) * 1024 * 1024
    used = today_usage_bytes(snap) if snap else 0
    pct = (used / limit) * 100.0 if limit else 0.0
    warn_at = max(1, min(100, int(settings.quota_warn_percent)))
    warn = pct >= warn_at
    exceeded = used >= limit
    msg = ""
    if exceeded or warn:
        key = "quota.msg_exceeded" if exceeded else "quota.msg_warn"
        msg = t(key, percent=f"{pct:.1f}", limit=settings.quota_daily_mb, iface=iface)
    return QuotaStatus(
        bool(settings.quota_enabled), iface, used, limit, pct, warn, exceeded, settings.quota_action, msg
    )
