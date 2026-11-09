# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .utils import config_dir, ensure_dirs

DEFAULTS = {
    "language": "system",
    "theme": "system",  # system | light | dark
    "refresh_seconds": 60,
    "live_speed": True,
    "selected_interface": "",
    "show_fiveminute": True,
    "show_hour": True,
    "show_day": True,
    "show_month": True,
    "show_top_days": True,
    "chart_days": 30,
    "chart_months": 12,
    "chart_hours": 24,
    "compact_numbers": False,
    "rate_unit": "bits",  # bits | bytes
    "history_sources": ["vnstat", "vnstat_db", "netscope", "sysfs", "procfs", "nmcli", "psutil"],
    "start_minimized": False,
    # Quota / controls
    "quota_enabled": False,
    "quota_daily_mb": 2048,
    "quota_warn_percent": 80,
    "quota_action": "warn",  # warn | disconnect | disable_interface | throttle
    "quota_throttle_kbit": 512,
    "quota_reset_hour": 0,
    "quota_interface": "",
    "monitor_enabled": False,
    "control_interface": "",
    # Alerts
    "alert_daily_enabled": True,
    "alert_hourly_enabled": True,
    "alert_hourly_mb": 1024,
    "alert_hourly_warn_percent": 80,
    "alert_low_speed_enabled": True,
    "alert_low_speed_kbps": 256,
    "alert_low_speed_seconds": 20,
    "alert_disconnect_enabled": True,
    "alert_network_change_enabled": True,
    "alerts_enabled": True,
    "alert_desktop_notify": True,
}


@dataclass
class Settings:
    language: str = DEFAULTS["language"]
    theme: str = DEFAULTS["theme"]
    refresh_seconds: int = DEFAULTS["refresh_seconds"]
    live_speed: bool = DEFAULTS["live_speed"]
    selected_interface: str = DEFAULTS["selected_interface"]
    show_fiveminute: bool = DEFAULTS["show_fiveminute"]
    show_hour: bool = DEFAULTS["show_hour"]
    show_day: bool = DEFAULTS["show_day"]
    show_month: bool = DEFAULTS["show_month"]
    show_top_days: bool = DEFAULTS["show_top_days"]
    chart_days: int = DEFAULTS["chart_days"]
    chart_months: int = DEFAULTS["chart_months"]
    chart_hours: int = DEFAULTS["chart_hours"]
    compact_numbers: bool = DEFAULTS["compact_numbers"]
    rate_unit: str = DEFAULTS["rate_unit"]
    history_sources: list[str] = field(default_factory=lambda: list(DEFAULTS["history_sources"]))
    start_minimized: bool = DEFAULTS["start_minimized"]
    quota_enabled: bool = DEFAULTS["quota_enabled"]
    quota_daily_mb: int = DEFAULTS["quota_daily_mb"]
    quota_warn_percent: int = DEFAULTS["quota_warn_percent"]
    quota_action: str = DEFAULTS["quota_action"]
    quota_throttle_kbit: int = DEFAULTS["quota_throttle_kbit"]
    quota_reset_hour: int = DEFAULTS["quota_reset_hour"]
    quota_interface: str = DEFAULTS["quota_interface"]
    monitor_enabled: bool = DEFAULTS["monitor_enabled"]
    control_interface: str = DEFAULTS["control_interface"]
    alert_daily_enabled: bool = DEFAULTS["alert_daily_enabled"]
    alert_hourly_enabled: bool = DEFAULTS["alert_hourly_enabled"]
    alert_hourly_mb: int = DEFAULTS["alert_hourly_mb"]
    alert_hourly_warn_percent: int = DEFAULTS["alert_hourly_warn_percent"]
    alert_low_speed_enabled: bool = DEFAULTS["alert_low_speed_enabled"]
    alert_low_speed_kbps: int = DEFAULTS["alert_low_speed_kbps"]
    alert_low_speed_seconds: int = DEFAULTS["alert_low_speed_seconds"]
    alert_disconnect_enabled: bool = DEFAULTS["alert_disconnect_enabled"]
    alert_network_change_enabled: bool = DEFAULTS["alert_network_change_enabled"]
    alerts_enabled: bool = DEFAULTS["alerts_enabled"]
    alert_desktop_notify: bool = DEFAULTS["alert_desktop_notify"]

    @classmethod
    def path(cls) -> Path:
        ensure_dirs()
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        path = cls.path()
        data = dict(DEFAULTS)
        try:
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
        data["refresh_seconds"] = max(15, min(3600, int(data.get("refresh_seconds", 60))))
        data["chart_hours"] = max(6, min(168, int(data.get("chart_hours", 24))))
        data["chart_days"] = max(7, min(365, int(data.get("chart_days", 30))))
        data["chart_months"] = max(3, min(60, int(data.get("chart_months", 12))))
        if data.get("theme") not in ("system", "light", "dark"):
            data["theme"] = "system"
        if data.get("language") not in ("system", "en", "ar"):
            data["language"] = "system"
        if data.get("rate_unit") not in ("bits", "bytes"):
            data["rate_unit"] = "bits"
        sources = data.get("history_sources")
        if not isinstance(sources, list):
            sources = list(DEFAULTS["history_sources"])
        data["history_sources"] = [str(s) for s in sources]
        data["quota_daily_mb"] = max(1, min(10_000_000, int(data.get("quota_daily_mb", 2048))))
        data["quota_warn_percent"] = max(1, min(100, int(data.get("quota_warn_percent", 80))))
        data["quota_throttle_kbit"] = max(16, min(10_000_000, int(data.get("quota_throttle_kbit", 512))))
        data["quota_reset_hour"] = max(0, min(23, int(data.get("quota_reset_hour", 0))))
        if data.get("quota_action") not in ("warn", "disconnect", "disable_interface", "throttle"):
            data["quota_action"] = "warn"
        data["alert_hourly_mb"] = max(1, min(10_000_000, int(data.get("alert_hourly_mb", 1024))))
        data["alert_hourly_warn_percent"] = max(1, min(100, int(data.get("alert_hourly_warn_percent", 80))))
        data["alert_low_speed_kbps"] = max(1, min(10_000_000, int(data.get("alert_low_speed_kbps", 256))))
        data["alert_low_speed_seconds"] = max(3, min(3600, int(data.get("alert_low_speed_seconds", 20))))
        for b in ("alert_daily_enabled","alert_hourly_enabled","alert_low_speed_enabled","alert_disconnect_enabled","alert_network_change_enabled","alerts_enabled","alert_desktop_notify"):
            data[b] = bool(data.get(b, DEFAULTS[b]))
        return cls(**{k: data.get(k, v) for k, v in DEFAULTS.items()})

    def save(self) -> None:
        path = self.path()
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
