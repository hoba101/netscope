# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ... import storage
from ...i18n import t
from ..gtk import Adw, Gtk
from ..widgets import boxed_list, button, button_row, card, clear, compact_status, page_scroller, pill
from .base import Page

_SEVERITY_ICON = {"warning": "dialog-warning-symbolic", "critical": "dialog-error-symbolic"}


class AlertsPage(Page):
    name = "alerts"
    icon = "preferences-system-notifications-symbolic"
    title_key = "page.alerts"
    subtitle_key = "alerts.subtitle"

    def build(self):
        scroller, column = page_scroller()
        log_card = card(t("alerts.log"))
        log_card.append(
            button_row(
                button(t("alerts.mark_read"), self.mark_read),
                button(t("alerts.clear"), self.clear_log),
                Gtk.Box(hexpand=True),
                button(t("alerts.settings"), lambda: self.window.open_preferences("alerts")),
            )
        )
        self.log = boxed_list()
        self.empty = compact_status(
            "preferences-system-notifications-symbolic", t("alerts.empty"), t("alerts.empty_hint")
        )
        log_card.append(self.empty)
        log_card.append(self.log)
        column.append(log_card)
        self.reload()
        return scroller

    def reload(self):
        clear(self.log)
        rows = storage.list_alerts(120)
        self.empty.set_visible(not rows)
        self.log.set_visible(bool(rows))
        for alert in rows:
            severity = alert.get("severity", "info")
            row = Adw.ActionRow(
                title=alert.get("title", ""),
                subtitle=f"{alert.get('ts', '').replace('T', ' ')} • {alert.get('interface', '')} • {alert.get('message', '')}",
            )
            row.add_prefix(
                Gtk.Image.new_from_icon_name(_SEVERITY_ICON.get(severity, "dialog-information-symbolic"))
            )
            css = {"critical": "bad", "warning": "warn"}.get(severity, "")
            row.add_suffix(pill(t(f"alerts.sev.{severity}", default=severity), css))
            if not alert.get("seen"):
                row.add_suffix(pill(t("alerts.fired"), "bad" if severity == "critical" else "warn"))
            self.log.append(row)

    def mark_read(self):
        storage.mark_alerts_seen()
        self.reload()

    def clear_log(self):
        storage.clear_alerts()
        self.reload()
