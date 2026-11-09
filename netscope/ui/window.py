# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from .. import __version__, autostart
from ..backends.collector import collect_snapshot, list_interfaces
from ..i18n import t
from ..installer import install_command, service_enable_command
from ..models import UsageSnapshot
from ..settings import Settings
from ..utils import is_linux, is_windows
from .gtk import Adw, Gio, GLib, Gtk
from .pages import PAGES, Page
from .settings_dialog import apply_theme, present_preferences
from .tasks import run_async
from .widgets import hint, install_css

log = logging.getLogger(__name__)

# Settings whose change only needs the current snapshot re-rendered.
_RERENDER_KEYS = {
    "live_speed",
    "rate_unit",
    "chart_hours",
    "chart_days",
    "chart_months",
    "quota_enabled",
    "quota_daily_mb",
    "quota_warn_percent",
    "quota_action",
}


class MainWindow(Adw.ApplicationWindow):
    """Owns shared state (settings, latest snapshot) and fans updates out to pages."""

    def __init__(self, app: Adw.Application, settings: Settings):
        super().__init__(application=app, title=t("app.name"))
        self.settings = settings
        self.snap: UsageSnapshot | None = None
        self.perms = None
        self._refreshing = False
        self._timers: dict[str, int] = {}
        self._quitting = False
        install_css()
        apply_theme(settings.theme)

        self.set_default_size(settings.window_width, settings.window_height)
        if settings.window_maximized:
            self.maximize()

        self.pages: dict[str, Page] = {}
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        for page_cls in PAGES:
            page = page_cls(self)
            self.pages[page.name] = page
            self.stack.add_named(_with_header(page.widget, page.title, page.subtitle), page.name)

        self.split = Adw.NavigationSplitView(
            sidebar_width_fraction=0.24, min_sidebar_width=230, max_sidebar_width=300
        )
        self.split.set_sidebar(Adw.NavigationPage.new(self._build_sidebar(), t("app.name")))
        self.content_page = Adw.NavigationPage.new(self.stack, t("page.overview"))
        self.split.set_content(self.content_page)
        self._toasts = Adw.ToastOverlay(child=self.split)
        self.set_content(self._toasts)

        breakpoint_ = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        breakpoint_.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint_)

        self._install_actions()
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_: self._stop_timers())
        self.show_page(settings.last_page if settings.last_page in self.pages else "overview", reveal=False)

        self._load_interfaces()
        self.refresh()
        self.refresh_diagnostics()
        self._schedule_refresh()
        self._timers["live"] = GLib.timeout_add_seconds(1, self._on_live_timer)
        if settings.autostart:
            try:
                autostart.set_enabled(True)
            except OSError:
                log.exception("could not refresh autostart entry")

    # -- shared API used by pages -------------------------------------------

    def page(self, name: str) -> Page:
        return self.pages[name]

    def iface(self) -> str:
        return (self.snap.interface.name if self.snap else "") or self.settings.selected_interface or ""

    def toast(
        self, message: str, button: str | None = None, on_click: Callable[[], None] | None = None
    ) -> None:
        toast = Adw.Toast(title=GLib.markup_escape_text(message))
        if button and on_click:
            toast.set_button_label(button)
            toast.connect("button-clicked", lambda *_: on_click())
        self._toasts.add_toast(toast)

    def show_page(self, name: str, reveal: bool = True) -> None:
        self.stack.set_visible_child_name(name)
        self.content_page.set_title(self.pages[name].title)
        row = self._nav_rows.get(name)
        if row and self.nav.get_selected_row() is not row:
            self.nav.select_row(row)
        if reveal:
            self.split.set_show_content(True)
        self.settings.last_page = name

    def open_preferences(self, page: str | None = None) -> None:
        present_preferences(self, self.settings, self.on_setting_changed, self._on_preferences_closed, page)

    def refresh(self) -> None:
        """Collect a new snapshot (and evaluate alerts) without blocking the UI."""
        if self._refreshing:
            return
        self._refreshing = True
        self.spinner.set_visible(True)
        self.refresh_button.set_visible(False)

        def work():
            from .. import alerts

            snap = collect_snapshot(settings=self.settings)
            fired = []
            if snap:
                try:
                    fired = alerts.evaluate(
                        snap, self.settings, snap.live_rx_bps, snap.live_tx_bps, do_notify=False
                    )
                except Exception:
                    log.exception("alert evaluation failed")
            return snap, fired

        run_async(work, self._on_refreshed)

    def refresh_diagnostics(self) -> None:
        def work():
            from ..accuracy import collect
            from ..permissions import scan

            return collect(self.iface()), scan()

        run_async(work, self._on_diagnostics)

    def rerender(self) -> None:
        """Re-render every page from the current snapshot (after a settings change)."""
        for page in self.pages.values():
            try:
                page.on_snapshot(self.snap)
            except Exception:
                log.exception("page %s failed to render snapshot", page.name)

    def run_commands(self, commands: list[list[str]], label: str = "") -> None:
        """Run (usually pkexec-wrapped) commands in order, then re-scan."""
        commands = [c for c in commands if c]
        if not commands:
            return
        self.toast(label or t("toast.action_started"))

        def work():
            for cmd in commands:
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    return (proc.stderr or proc.stdout or " ".join(cmd)).strip()[:160]
            return ""

        def done(error_text, error):
            self.toast(str(error) if error else error_text or t("toast.done"))
            self.refresh()
            self.refresh_diagnostics()

        run_async(work, done)

    def setup_vnstat(self) -> None:
        perms = self.perms
        commands = []
        if not perms or not perms.has_vnstat:
            commands.append(install_command(["vnstat"]))
        if not perms or not perms.has_vnstatd_service:
            commands.append(service_enable_command("vnstat"))
        self.run_commands(commands, t("onboarding.installing"))

    def on_setting_changed(self, key: str) -> None:
        if key == "refresh_seconds":
            self._schedule_refresh()
        elif key == "autostart":
            try:
                autostart.set_enabled(self.settings.autostart)
            except OSError as exc:
                self.toast(str(exc))
        elif key in _RERENDER_KEYS:
            self.rerender()

    def save_state(self) -> None:
        if not self.is_maximized():
            width, height = self.get_default_size()
            self.settings.window_width, self.settings.window_height = width, height
        self.settings.window_maximized = self.is_maximized()
        self.settings.save()

    def quit_app(self) -> None:
        self._quitting = True
        self.save_state()
        self.get_application().quit()

    # -- internals -------------------------------------------------------------

    def _build_sidebar(self) -> Gtk.Widget:
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=t("app.name"), subtitle=f"v{__version__}"))
        self.refresh_button = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text=f"{t('action.refresh')} (Ctrl+R)",
            action_name="win.refresh",
        )
        self.spinner = Adw.Spinner(visible=False, tooltip_text=t("status.refreshing"))
        header.pack_start(self.refresh_button)
        header.pack_start(self.spinner)
        header.pack_end(
            Gtk.MenuButton(
                icon_name="open-menu-symbolic",
                menu_model=_primary_menu(),
                primary=True,
                tooltip_text=t("menu.main"),
            )
        )
        view.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        iface_row = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=6)
        iface_row.append(Gtk.Image.new_from_icon_name("network-wired-symbolic"))
        self.iface_dropdown = Gtk.DropDown.new_from_strings([t("settings.interface.auto")])
        self.iface_dropdown.set_hexpand(True)
        self.iface_dropdown.set_tooltip_text(t("settings.interface"))
        self._iface_names: list[str] = [""]
        self._iface_handler = self.iface_dropdown.connect("notify::selected", self._on_iface_selected)
        iface_row.append(self.iface_dropdown)
        box.append(iface_row)
        self.status_line = hint(margin_start=14, margin_end=14)
        box.append(self.status_line)

        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, vexpand=True)
        self.nav.add_css_class("navigation-sidebar")
        self._nav_rows: dict[str, Gtk.ListBoxRow] = {}
        for index, page in enumerate(self.pages.values(), start=1):
            row = Gtk.ListBoxRow(tooltip_text=f"{page.subtitle} (Ctrl+{index})")
            content = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=6, margin_end=6)
            content.append(Gtk.Image.new_from_icon_name(page.icon))
            content.append(Gtk.Label(label=page.title, xalign=0, hexpand=True))
            row.set_child(content)
            row.page_name = page.name
            self._nav_rows[page.name] = row
            self.nav.append(row)
        self.nav.connect("row-activated", lambda _l, row: self.show_page(row.page_name))
        box.append(self.nav)
        view.set_content(box)
        return view

    def _install_actions(self) -> None:
        refresh = Gio.SimpleAction.new("refresh", None)
        refresh.connect("activate", lambda *_: (self.refresh(), self.refresh_diagnostics()))
        self.add_action(refresh)
        go = Gio.SimpleAction.new("go-page", GLib.VariantType.new("s"))
        go.connect("activate", lambda _a, name: self.show_page(name.get_string()))
        self.add_action(go)

    def _load_interfaces(self) -> None:
        run_async(lambda: list_interfaces(self.settings), self._on_interfaces)

    def _on_interfaces(self, names, error):
        if error or not names:
            return
        self._iface_names = ["", *names]
        self.iface_dropdown.handler_block(self._iface_handler)
        self.iface_dropdown.set_model(Gtk.StringList.new([t("settings.interface.auto"), *names]))
        selected = self.settings.selected_interface
        self.iface_dropdown.set_selected(
            self._iface_names.index(selected) if selected in self._iface_names else 0
        )
        self.iface_dropdown.handler_unblock(self._iface_handler)

    def _on_iface_selected(self, *_):
        name = self._iface_names[self.iface_dropdown.get_selected()]
        if name == self.settings.selected_interface:
            return
        self.settings.selected_interface = name
        self.settings.save()
        self.refresh()
        self.refresh_diagnostics()

    def _on_refreshed(self, result, error):
        self._refreshing = False
        self.spinner.set_visible(False)
        self.refresh_button.set_visible(True)
        if error:
            self.toast(str(error))
            return
        self.snap, fired = result
        if self.snap:
            sources = ", ".join(self.snap.sources[:2])
            self.status_line.set_text(
                f"{t('status.updated')} {GLib.DateTime.new_now_local().format('%H:%M')} • {sources}"
            )
        self.rerender()
        if fired:
            self.page("alerts").reload()
            self.toast(
                f"{t('alerts.fired')}: {fired[-1]['title']}", t("menu.view"), lambda: self.show_page("alerts")
            )
            if self.settings.alert_desktop_notify:
                for alert in fired:
                    self.get_application().notify(alert["title"], alert["message"], f"alert-{alert['kind']}")

    def _on_diagnostics(self, result, error):
        if error:
            return
        accuracy, self.perms = result
        for page in self.pages.values():
            try:
                page.on_diagnostics(accuracy, self.perms)
            except Exception:
                log.exception("page %s failed to render diagnostics", page.name)
        if not self.settings.onboarding_done:
            from .onboarding import present_onboarding

            self.settings.onboarding_done = True
            self.settings.save()
            present_onboarding(self, self.perms)

    def _schedule_refresh(self) -> None:
        if "refresh" in self._timers:
            GLib.source_remove(self._timers.pop("refresh"))
        self._timers["refresh"] = GLib.timeout_add_seconds(
            max(15, self.settings.refresh_seconds), self._on_refresh_timer
        )

    def _stop_timers(self) -> None:
        for source in self._timers.values():
            GLib.source_remove(source)
        self._timers.clear()

    def _on_refresh_timer(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _on_live_timer(self) -> bool:
        if self.settings.live_speed and self.snap:
            rates = _read_live_rates(self.snap.interface.name)
            if rates:
                self.snap.live_rx_bps, self.snap.live_tx_bps = rates
                for page in self.pages.values():
                    page.on_live_rates(*rates)
        return GLib.SOURCE_CONTINUE

    def _on_close_request(self, *_):
        self.save_state()
        app = self.get_application()
        if self.settings.run_in_background and not self._quitting:
            self.set_visible(False)
            app.keep_running()
            if not self.settings.background_hint_shown:
                self.settings.background_hint_shown = True
                self.settings.save()
                app.notify(t("background.title"), t("background.body"), "background")
            return True
        app.quit()
        return False

    def _on_preferences_closed(self, language_changed: bool) -> None:
        if not language_changed:
            return
        # Strings are resolved at build time, so a language change rebuilds the window.
        app = self.get_application()
        app.apply_language()
        replacement = MainWindow(app, self.settings)
        replacement.present()
        self._quitting = True
        self.destroy()


def _read_live_rates(iface: str) -> tuple[float, float] | None:
    if is_linux():
        from ..backends.linux_sysfs import read_live_rates
    elif is_windows():
        from ..backends.windows import read_live_rates
    else:
        return None
    return read_live_rates(iface)


def _primary_menu() -> Gio.Menu:
    menu = Gio.Menu()
    main = Gio.Menu()
    main.append(t("page.settings"), "app.preferences")
    main.append(t("menu.shortcuts"), "app.shortcuts")
    main.append(t("menu.about"), "app.about")
    menu.append_section(None, main)
    end = Gio.Menu()
    end.append(t("menu.quit"), "app.quit")
    menu.append_section(None, end)
    return menu


def _with_header(child: Gtk.Widget, title: str, subtitle: str) -> Adw.ToolbarView:
    view = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(title=title, subtitle=subtitle))
    view.add_top_bar(header)
    view.set_content(child)
    return view
