# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from ...i18n import t

if TYPE_CHECKING:
    from ...accuracy import AccuracyReport
    from ...models import UsageSnapshot
    from ...permissions import CapabilityReport
    from ..gtk import Gtk
    from ..window import MainWindow


class Page:
    """One sidebar destination.

    Subclasses set the class attributes, build their widget tree in
    :meth:`build`, and override the ``on_*`` hooks they care about. The window
    calls the hooks; pages never reach into each other directly.
    """

    name: str = ""
    icon: str = ""
    title_key: str = ""
    subtitle_key: str = ""

    def __init__(self, window: MainWindow):
        self.window = window
        self.widget: Gtk.Widget = self.build()

    @property
    def title(self) -> str:
        return t(self.title_key)

    @property
    def subtitle(self) -> str:
        return t(self.subtitle_key)

    @property
    def settings(self):
        return self.window.settings

    def build(self) -> Gtk.Widget:
        raise NotImplementedError

    def on_snapshot(self, snap: UsageSnapshot | None) -> None:
        """Called after every data refresh."""

    def on_live_rates(self, rx_bps: float, tx_bps: float) -> None:
        """Called every second with fresh link rates (bits/s)."""

    def on_diagnostics(self, accuracy: AccuracyReport, perms: CapabilityReport) -> None:
        """Called when diagnostics have been re-scanned."""
