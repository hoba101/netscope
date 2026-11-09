# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""All preferences in one dialog. Every change is saved immediately."""

from __future__ import annotations

from collections.abc import Callable

from ..i18n import t
from ..settings import Settings
from .gtk import Adw, Gtk

LANGUAGES = ("system", "en", "ar")
THEMES = ("system", "light", "dark")
RATE_UNITS = ("bits", "bytes")
QUOTA_ACTIONS = ("warn", "disconnect", "disable_interface", "throttle")
_COLOR_SCHEMES = {
    "system": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}


def apply_theme(theme: str) -> None:
    Adw.StyleManager.get_default().set_color_scheme(_COLOR_SCHEMES.get(theme, Adw.ColorScheme.DEFAULT))


class _Binder:
    """Creates rows bound to a ``Settings`` attribute; saves and notifies on change."""

    def __init__(self, settings: Settings, on_change: Callable[[str], None]):
        self.settings = settings
        self.on_change = on_change

    def _commit(self, attr: str, value) -> None:
        if getattr(self.settings, attr) == value:
            return
        setattr(self.settings, attr, value)
        self.settings.save()
        self.on_change(attr)

    def switch(self, attr: str, title: str, subtitle: str = "") -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=title, subtitle=subtitle, active=bool(getattr(self.settings, attr)))
        row.connect("notify::active", lambda r, _p: self._commit(attr, r.get_active()))
        return row

    def spin(
        self, attr: str, title: str, lo: float, hi: float, step: float, subtitle: str = ""
    ) -> Adw.SpinRow:
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_value(getattr(self.settings, attr))
        row.connect("notify::value", lambda r, _p: self._commit(attr, int(r.get_value())))
        return row

    def combo(self, attr: str, title: str, options: tuple[str, ...], key_prefix: str) -> Adw.ComboRow:
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new([t(f"{key_prefix}.{o}") for o in options]))
        current = getattr(self.settings, attr)
        row.set_selected(options.index(current) if current in options else 0)
        row.connect("notify::selected", lambda r, _p: self._commit(attr, options[r.get_selected()]))
        return row


def _page(
    name: str, title: str, icon: str, groups: list[tuple[str, list[Gtk.Widget]]]
) -> Adw.PreferencesPage:
    page = Adw.PreferencesPage(name=name, title=title, icon_name=icon)
    for group_title, rows in groups:
        group = Adw.PreferencesGroup(title=group_title)
        for row in rows:
            group.add(row)
        page.add(group)
    return page


def present_preferences(
    parent: Gtk.Window,
    settings: Settings,
    on_change: Callable[[str], None],
    on_closed: Callable[[bool], None],
    page: str | None = None,
) -> None:
    """Show preferences. ``on_closed(language_changed)`` runs when the dialog closes."""
    dialog = Adw.PreferencesDialog(title=t("settings.title"), search_enabled=True)
    start_language = settings.language

    def changed(attr: str) -> None:
        if attr == "theme":
            apply_theme(settings.theme)
        on_change(attr)

    b = _Binder(settings, changed)

    dialog.add(
        _page(
            "general",
            t("prefs.general"),
            "preferences-system-symbolic",
            [
                (
                    t("settings.appearance"),
                    [
                        b.combo("language", t("settings.language"), LANGUAGES, "settings.language"),
                        b.combo("theme", t("settings.theme"), THEMES, "settings.theme"),
                    ],
                ),
                (
                    t("prefs.behaviour"),
                    [
                        b.switch("run_in_background", t("prefs.background"), t("prefs.background_hint")),
                        b.switch("autostart", t("prefs.autostart"), t("prefs.autostart_hint")),
                    ],
                ),
            ],
        )
    )
    dialog.add(
        _page(
            "data",
            t("settings.data"),
            "view-continuous-symbolic",
            [
                (
                    t("settings.data"),
                    [
                        b.spin(
                            "refresh_seconds", t("settings.refresh"), 15, 3600, 15, t("prefs.seconds_hint")
                        ),
                        b.switch("live_speed", t("settings.live_speed")),
                        b.combo("rate_unit", t("settings.rate_unit"), RATE_UNITS, "settings.rate_unit"),
                    ],
                ),
                (
                    t("prefs.charts"),
                    [
                        b.spin("chart_hours", t("settings.chart_hours"), 6, 168, 6),
                        b.spin("chart_days", t("settings.chart_days"), 7, 365, 1),
                        b.spin("chart_months", t("settings.chart_months"), 3, 60, 1),
                    ],
                ),
            ],
        )
    )
    dialog.add(
        _page(
            "quota",
            t("settings.quota"),
            "speedometer-symbolic",
            [
                (
                    t("settings.quota"),
                    [
                        b.switch("quota_enabled", t("settings.quota_enabled")),
                        b.spin("quota_daily_mb", t("settings.quota_daily_mb"), 1, 10_000_000, 100),
                        b.spin("quota_warn_percent", t("settings.quota_warn_percent"), 1, 100, 1),
                        b.combo(
                            "quota_action", t("settings.quota_action"), QUOTA_ACTIONS, "settings.quota_action"
                        ),
                        b.spin("quota_throttle_kbit", t("settings.quota_throttle_kbit"), 16, 10_000_000, 64),
                    ],
                ),
            ],
        )
    )
    dialog.add(
        _page(
            "alerts",
            t("page.alerts"),
            "preferences-system-notifications-symbolic",
            [
                (
                    t("alerts.settings"),
                    [
                        b.switch("alerts_enabled", t("alerts.enabled")),
                        b.switch("alert_desktop_notify", t("alerts.notify")),
                    ],
                ),
                (
                    t("prefs.alert_rules"),
                    [
                        b.switch("alert_daily_enabled", t("alerts.daily")),
                        b.switch("alert_hourly_enabled", t("alerts.hourly")),
                        b.spin("alert_hourly_mb", t("alerts.hourly_mb"), 1, 10_000_000, 100),
                        b.spin("alert_hourly_warn_percent", t("alerts.hourly_warn"), 1, 100, 1),
                        b.switch("alert_low_speed_enabled", t("alerts.low_speed")),
                        b.spin("alert_low_speed_kbps", t("alerts.low_speed_kbps"), 1, 10_000_000, 16),
                        b.spin("alert_low_speed_seconds", t("alerts.low_speed_sec"), 3, 3600, 1),
                        b.switch("alert_disconnect_enabled", t("alerts.disconnect")),
                        b.switch("alert_network_change_enabled", t("alerts.network_change")),
                    ],
                ),
            ],
        )
    )
    if page:
        dialog.set_visible_page_name(page)
    dialog.connect("closed", lambda *_: on_closed(settings.language != start_language))
    dialog.present(parent)
