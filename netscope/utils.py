# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import platform
import sys
from datetime import date, datetime
from pathlib import Path

from .i18n import get_language


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def platform_name() -> str:
    return platform.system()


def config_dir() -> Path:
    if is_windows():
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "NetScope"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "netscope"


def data_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "NetScope"
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "netscope"


def cache_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "NetScope" / "Cache"
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "netscope"


def ensure_dirs() -> None:
    for path in (config_dir(), data_dir(), cache_dir()):
        path.mkdir(parents=True, exist_ok=True)


def fmt_bytes(value: float, compact: bool = False, rate: bool = False) -> str:
    value = max(0.0, float(value))
    if rate:
        # bits/sec
        units = [("bit/s", 1), ("kbit/s", 1000), ("Mbit/s", 1_000_000), ("Gbit/s", 1_000_000_000)]
        idx = 0
        while value >= 1000 and idx < len(units) - 1:
            value /= 1000
            idx += 1
        suffix = units[idx][0]
        if idx == 0:
            return f"{value:.0f} {suffix}"
        if value >= 100:
            return f"{value:.0f} {suffix}"
        return f"{value:.1f} {suffix}"

    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if compact:
        compact_units = ["B", "K", "M", "G", "T", "P"]
        suffix = compact_units[idx]
        if idx == 0:
            return f"{value:.0f}{suffix}"
        if value >= 100:
            return f"{value:.0f}{suffix}"
        return f"{value:.1f}{suffix}"
    suffix = units[idx]
    if idx == 0:
        return f"{value:.0f} {suffix}"
    if value >= 100:
        return f"{value:.0f} {suffix}"
    if value >= 10:
        return f"{value:.1f} {suffix}"
    return f"{value:.2f} {suffix}"


def fmt_rate(bits_per_second: float, unit: str = "bits") -> str:
    """Format a link rate in bits/s, or in bytes/s when ``unit == "bytes"``."""
    if unit == "bytes":
        return f"{fmt_bytes(bits_per_second / 8)}/s"
    return fmt_bytes(bits_per_second, rate=True)


AR_MONTHS = [
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
]
AR_MONTHS_SHORT = [
    "ينا",
    "فبر",
    "مار",
    "أبر",
    "ماي",
    "يون",
    "يول",
    "أغس",
    "سبت",
    "أكت",
    "نوف",
    "ديس",
]
EN_MONTHS_SHORT = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def month_name(month: int, short: bool = False) -> str:
    month = max(1, min(12, int(month)))
    if get_language() == "ar":
        return (AR_MONTHS_SHORT if short else AR_MONTHS)[month - 1]
    if short:
        return EN_MONTHS_SHORT[month - 1]
    return date(2000, month, 1).strftime("%B")


def weekday_name(dt: date | datetime) -> str:
    names = AR_DAYS if get_language() == "ar" else EN_DAYS
    return names[dt.weekday()]


def fmt_date(dt: date | datetime, with_year: bool = True) -> str:
    if get_language() == "ar":
        base = f"{dt.day} {AR_MONTHS[dt.month - 1]}"
        return f"{base} {dt.year}" if with_year else base
    if with_year:
        return f"{dt.day} {month_name(dt.month, short=True)} {dt.year}"
    return f"{dt.day} {month_name(dt.month, short=True)}"


def fmt_datetime(dt: datetime) -> str:
    return f"{fmt_date(dt)}, {dt:%H:%M}"


def fmt_clock(hour: int, minute: int = 0) -> str:
    return f"{int(hour):02d}:{int(minute):02d}"
