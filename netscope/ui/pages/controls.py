# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

from ... import controls
from ...i18n import t
from ...utils import is_linux
from ..gtk import Adw, Gtk
from ..widgets import button, button_row, card, hint, label, page_scroller
from .base import Page

log = logging.getLogger(__name__)

_ACTIONS = {
    "throttle": lambda iface, kbit: controls.throttle_linux(iface, kbit),
    "restore": lambda iface, _kbit: controls.restore_linux(iface),
    "disconnect": lambda iface, _kbit: controls.disconnect_linux(iface),
    "connect": lambda iface, _kbit: controls.connect_linux(iface),
}
# Action that reverses each one, offered as "Undo" in the result toast.
_UNDO = {"throttle": "restore", "disconnect": "connect"}


class ControlsPage(Page):
    name = "controls"
    icon = "security-high-symbolic"
    title_key = "page.controls"
    subtitle_key = "controls.subtitle"

    def build(self):
        scroller, column = page_scroller()

        quota = card(t("settings.quota"))
        self.quota_summary = label("", "small")
        quota.append(self.quota_summary)
        quota.append(
            button(t("prefs.open"), lambda: self.window.open_preferences("quota"), halign=Gtk.Align.START)
        )
        column.append(quota)

        box = card(t("controls.current"), t("controls.safe"))
        self.caps = hint()
        box.append(self.caps)
        throttle = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.throttle_kbit = Gtk.SpinButton.new_with_range(16, 10_000_000, 64)
        self.throttle_kbit.set_value(self.settings.quota_throttle_kbit)
        throttle.append(label(f"{t('controls.throttle')} (kbit/s)", hexpand=True))
        throttle.append(self.throttle_kbit)
        throttle.append(
            button(
                t("action.apply"),
                lambda: self.confirm("throttle", int(self.throttle_kbit.get_value())),
                "suggested-action",
                valign=Gtk.Align.CENTER,
            )
        )
        box.append(throttle)
        box.append(hint(t("controls.throttle_hint")))
        box.append(
            button_row(
                button(t("action.restore"), lambda: self.confirm("restore")),
                button(t("action.connect"), lambda: self.confirm("connect")),
                button(t("action.disconnect"), lambda: self.confirm("disconnect"), "destructive-action"),
            )
        )
        box.append(hint(t("controls.disconnect_hint")))
        column.append(box)
        return scroller

    def on_snapshot(self, snap):
        s = self.settings
        if not s.quota_enabled:
            self.quota_summary.set_text(t("quota.not_enabled"))
            return
        self.quota_summary.set_text(
            t(
                "controls.quota_summary",
                mb=s.quota_daily_mb,
                percent=s.quota_warn_percent,
                action=t(f"settings.quota_action.{s.quota_action}"),
            )
        )

    def on_diagnostics(self, accuracy, perms):
        yes, no = t("label.yes"), t("label.no")
        caps = "  ".join(
            f"{name}: {yes if ok else no}"
            for name, ok in (("tc", perms.has_tc), ("nmcli", perms.has_nmcli), ("pkexec", perms.has_pkexec))
        )
        self.caps.set_text(f"{t('label.status')} — {caps}")

    def confirm(self, action: str, kbit: int | None = None):
        iface = self.window.iface() or "?"
        kbit = kbit or self.settings.quota_throttle_kbit
        if action == "connect":
            heading, body = t("action.connect"), iface
        else:
            heading = t(f"confirm.{action}.title")
            body = t(f"confirm.{action}.body", iface=iface, kbit=kbit)
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", t("action.cancel"))
        dialog.add_response("ok", t("action.confirm"))
        appearance = (
            Adw.ResponseAppearance.DESTRUCTIVE if action == "disconnect" else Adw.ResponseAppearance.SUGGESTED
        )
        dialog.set_response_appearance("ok", appearance)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, resp: resp == "ok" and self.run_action(action, kbit))
        dialog.present(self.window)

    def run_action(self, action: str, kbit: int):
        iface = self.window.iface()
        result = _ACTIONS[action](iface, kbit)
        if (
            not result.ok
            and result.needs_privilege
            and is_linux()
            and self._run_elevated(action, iface, kbit)
        ):
            self.window.toast(f"{t('toast.action_started')} — {t('label.needs_permission')}")
            return
        undo = _UNDO.get(action) if result.ok else None
        self.window.toast(
            (result.message or action)[:120],
            t("action.undo") if undo else None,
            (lambda: self.run_action(undo, kbit)) if undo else None,
        )
        self.window.refresh()
        self.window.refresh_diagnostics()

    @staticmethod
    def _run_elevated(action: str, iface: str, kbit: int) -> bool:
        exe = shutil.which("netscope")
        # Without an installed launcher, re-run this package through the interpreter.
        base = [exe] if exe else [sys.executable, "-m", "netscope"]
        cmd = ["pkexec", *base, "--cli", "control", action]
        if iface:
            cmd += ["--iface", iface]
        if action == "throttle":
            cmd += ["--kbit", str(kbit)]
        try:
            subprocess.Popen(cmd)
        except OSError:
            log.exception("could not start pkexec for %s", action)
            return False
        return True
