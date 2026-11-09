# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime

from ...i18n import t
from ...lan import LanDevice, discover
from ...series import usage_today
from ...utils import fmt_bytes
from ..gtk import Adw, Gtk
from ..tasks import run_async
from ..widgets import boxed_list, button, button_row, card, clear, compact_status, hint, page_scroller
from .base import Page


class LanPage(Page):
    name = "lan"
    icon = "network-workgroup-symbolic"
    title_key = "page.lan"
    subtitle_key = "lan.subtitle"

    def build(self):
        self.devices: list[LanDevice] = []
        self.scanning = False
        scroller, column = page_scroller()
        column.append(card(t("lan.note"), t("lan.usage_hint")))

        controls = card()
        self.scan_btn = button(t("lan.scan"), lambda: self.scan(active=False), "suggested-action")
        self.active_btn = button(t("lan.scan_active"), lambda: self.scan(active=True))
        self.status = hint()
        controls.append(button_row(self.scan_btn, self.active_btn))
        controls.append(self.status)
        column.append(controls)

        devices = card(t("lan.devices"))
        self.list = boxed_list()
        devices.append(self.list)
        column.append(devices)
        self.render()
        self.scan(active=False)
        return scroller

    def on_snapshot(self, snap):
        self.render()  # this device's "today" figure comes from the snapshot

    def scan(self, active: bool):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.set_sensitive(False)
        self.active_btn.set_sensitive(False)
        self.status.set_text(t("toast.action_started"))
        run_async(lambda: discover(active=active), self._scan_done)

    def _scan_done(self, devices, error):
        self.scanning = False
        self.scan_btn.set_sensitive(True)
        self.active_btn.set_sensitive(True)
        if error:
            self.status.set_text(str(error))
            return
        self.devices = devices
        self.status.set_text(f"{t('lan.last_scan')}: {datetime.now():%H:%M:%S} • {len(devices)}")
        self.render()

    def render(self):
        clear(self.list)
        if not self.devices:
            self.list.append(compact_status("network-workgroup-symbolic", t("lan.empty")))
            return
        for dev in self.devices:
            self.list.append(self._row(dev))

    def _row(self, dev: LanDevice) -> Adw.ActionRow:
        tags = []
        if dev.is_gateway:
            tags.append(t("lan.gateway"))
        if dev.is_self:
            tags.append(t("lan.this_device"))
        title = dev.hostname or dev.ip
        if tags:
            title += f"  [{', '.join(tags)}]"
        subtitle = f"{t('lan.ip')}: {dev.ip}"
        if dev.mac:
            subtitle += f" • {t('lan.mac')}: {dev.mac}"
        if dev.state:
            subtitle += f" • {dev.state}"
        row = Adw.ActionRow(title=title, subtitle=subtitle)

        if dev.is_self:
            today = usage_today(self.window.snap)
            value = fmt_bytes(today.total) if today else "—"
            row.add_suffix(Gtk.Label(label=f"{t('summary.today')}: {value}", css_classes=["small"]))
        else:
            row.add_suffix(hint(t("lan.unknown_usage"), max_width_chars=22, xalign=1))
        return row
