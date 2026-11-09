# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from datetime import datetime

from ...i18n import t
from ...installer import install_command, service_enable_command
from ...utils import fmt_bytes
from ..gtk import Gdk, Gtk
from ..widgets import button, button_row, card, clear, flow, hint, label, page_scroller, pill, save_file, vbox
from .base import Page

_CONFIDENCE_CSS = {"high": "good", "medium": "warn", "low": "bad"}


class DiagnosticsPage(Page):
    name = "diagnostics"
    icon = "dialog-information-symbolic"
    title_key = "page.diagnostics"
    subtitle_key = "diagnostics.subtitle"

    def build(self):
        self.report: dict = {}
        scroller, column = page_scroller()
        top = card()
        top.append(
            button_row(
                button(t("diag.refresh"), self.window.refresh_diagnostics),
                button(t("action.copy"), self.copy),
                button(t("diag.export"), self.export, "suggested-action"),
            )
        )
        column.append(top)
        # Each card keeps a fixed header and a body box that is rebuilt on refresh.
        self.accuracy_body = self._section(column, t("diag.accuracy"))
        self.perms_body = self._section(column, t("diag.permissions"))
        self.sources_body = self._section(column, t("diag.sources"))
        self.install_body = self._section(column, t("diag.install"), t("diag.install_hint"))
        return scroller

    @staticmethod
    def _section(column: Gtk.Box, title: str, subtitle: str | None = None) -> Gtk.Box:
        box = card(title, subtitle)
        body = vbox()
        box.append(body)
        column.append(box)
        return body

    def on_diagnostics(self, accuracy, perms):
        self.report = {"accuracy": accuracy.as_dict(), "permissions": perms.as_dict()}
        self._render_accuracy(accuracy)
        self._render_permissions(perms)
        self._render_install(perms)

    def on_snapshot(self, snap):
        clear(self.sources_body)
        if not snap:
            return
        for src in snap.sources:
            self.sources_body.append(pill(src, "good"))
        for note in snap.notes:
            self.sources_body.append(hint(f"• {note}"))

    def _render_accuracy(self, acc):
        clear(self.accuracy_body)
        conf = acc.confidence
        row = Gtk.Box(spacing=8)
        row.append(pill(t(f"accuracy.confidence.{conf}", default=conf), _CONFIDENCE_CSS.get(conf, "")))
        row.append(hint(t(f"accuracy.confidence.{conf}_hint", default=t("status.accuracy")), hexpand=True))
        self.accuracy_body.append(row)
        for probe in acc.probes[:8]:
            if probe.rx_bytes is not None:
                value = f"↓{fmt_bytes(probe.rx_bytes)} ↑{fmt_bytes(probe.tx_bytes or 0)}"
            else:
                value = probe.error[:80] if probe.error else "—"
            meta = []
            if probe.link_up is not None:
                meta.append(t("diag.link_up") if probe.link_up else t("diag.link_down"))
            if probe.speed_mbps:
                meta.append(f"{probe.speed_mbps}Mbps")
            left = vbox(2)
            left.set_hexpand(True)
            left.append(label(probe.source, wrap=False))
            if meta:
                left.append(hint(" ".join(meta)))
            line = Gtk.Box(spacing=10)
            line.append(left)
            line.append(hint(value, max_width_chars=34, xalign=1))
            self.accuracy_body.append(line)

    def _render_permissions(self, perms):
        clear(self.perms_body)
        flags = (
            ("vnStat", perms.has_vnstat),
            ("vnStat DB read", perms.can_read_vnstat_db),
            ("nmcli", perms.has_nmcli),
            ("tc", perms.has_tc),
            ("nft", perms.has_nft),
            ("pkexec", perms.has_pkexec),
            ("admin/root", perms.is_admin),
        )
        pills = flow(3)
        for name, ok in flags:
            state = t("label.available") if ok else t("label.unavailable")
            pills.append(pill(f"{name}: {state}", "good" if ok else "muted"))
        self.perms_body.append(pills)
        for note in perms.notes:
            self.perms_body.append(hint(f"• {note}"))

    def _render_install(self, perms):
        clear(self.install_body)
        fixes = []
        if not perms.has_tc:
            fixes.append((t("diag.install_tc"), install_command(["iproute-tc"])))
        if perms.has_vnstat and not perms.has_vnstatd_service:
            fixes.append((t("diag.enable_vnstat"), service_enable_command("vnstat")))
        fixes = [(text, cmd) for text, cmd in fixes if cmd]
        if not fixes:
            self.install_body.append(label(f"✓ {t('label.available')}", "good", "small"))
            return
        for text, cmd in fixes:
            self.install_body.append(
                button(text, lambda c=cmd: self.window.run_commands([c]), halign=Gtk.Align.START)
            )

    def copy(self):
        text = json.dumps(self.report, ensure_ascii=False, indent=2)
        Gdk.Display.get_default().get_clipboard().set(text)
        self.window.toast(t("toast.copied"))

    def export(self):
        payload = {"diagnostics": self.report, "snapshot_interface": self.window.iface()}

        def saved(path, error):
            self.window.toast(str(error) if error else f"{t('toast.exported')}: {path}")

        save_file(
            self.window,
            t("diag.export"),
            f"netscope-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.json",
            lambda: json.dumps(payload, ensure_ascii=False, indent=2),
            saved,
        )
