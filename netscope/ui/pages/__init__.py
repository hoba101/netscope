# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar pages. ``PAGES`` defines their order in the navigation."""

from .alerts import AlertsPage
from .base import Page
from .controls import ControlsPage
from .diagnostics import DiagnosticsPage
from .history import HistoryPage
from .lan import LanPage
from .overview import OverviewPage
from .speedtest import SpeedTestPage

PAGES: tuple[type[Page], ...] = (
    OverviewPage,
    HistoryPage,
    ControlsPage,
    SpeedTestPage,
    AlertsPage,
    LanPage,
    DiagnosticsPage,
)

__all__ = ["PAGES", "Page"]
