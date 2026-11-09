# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Period = Literal["fiveminute", "hour", "day", "month", "year", "top"]


@dataclass(slots=True)
class UsagePoint:
    rx: int
    tx: int
    start: datetime | date | None = None
    label: str = ""
    detail: str = ""

    @property
    def total(self) -> int:
        return self.rx + self.tx


@dataclass(slots=True)
class InterfaceInfo:
    name: str
    alias: str = ""
    active: bool = True
    created: datetime | None = None
    updated: datetime | None = None
    total_rx: int = 0
    total_tx: int = 0
    source: str = ""


@dataclass(slots=True)
class UsageSnapshot:
    interface: InterfaceInfo
    fiveminute: list[UsagePoint] = field(default_factory=list)
    hour: list[UsagePoint] = field(default_factory=list)
    day: list[UsagePoint] = field(default_factory=list)
    month: list[UsagePoint] = field(default_factory=list)
    year: list[UsagePoint] = field(default_factory=list)
    top: list[UsagePoint] = field(default_factory=list)
    live_rx_bps: float = 0.0
    live_tx_bps: float = 0.0
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)