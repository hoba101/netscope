# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""First-run welcome: checks that long-term history (vnStat) is set up."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..i18n import t
from .gtk import Adw, Gtk
from .widgets import boxed_list, button, status_page

if TYPE_CHECKING:
    from .window import MainWindow


def _check_row(title: str, ok: bool) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=t("label.available") if ok else t("label.unavailable"))
    icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic" if ok else "dialog-warning-symbolic")
    icon.add_css_class("good" if ok else "warn")
    row.add_prefix(icon)
    return row


def present_onboarding(window: MainWindow, perms) -> None:
    dialog = Adw.Dialog(title=t("onboarding.title"), content_width=480)
    body = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_start=24, margin_end=24, margin_bottom=24
    )

    checks = boxed_list()
    has_vnstat = bool(perms and perms.has_vnstat)
    has_service = bool(perms and perms.has_vnstatd_service)
    checks.append(_check_row(t("onboarding.vnstat"), has_vnstat))
    checks.append(_check_row(t("onboarding.service"), has_service))
    body.append(checks)

    actions = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
    if not (has_vnstat and has_service):
        actions.append(
            button(t("onboarding.fix"), lambda: (dialog.close(), window.setup_vnstat()), "suggested-action")
        )
    actions.append(
        button(
            t("onboarding.start"),
            dialog.close,
            "" if not (has_vnstat and has_service) else "suggested-action",
        )
    )
    body.append(actions)

    page = status_page(APP_ICON, t("onboarding.heading"), t("onboarding.body"), body)
    view = Adw.ToolbarView(content=page)
    view.add_top_bar(Adw.HeaderBar(show_title=False))
    dialog.set_child(view)
    dialog.present(window)


APP_ICON = "io.github.hoba101.NetScope"
