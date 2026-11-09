# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI entry point. The interface itself lives in :mod:`netscope.ui`."""

from __future__ import annotations

import logging
import os
import sys
import traceback

from . import APP_ID, __version__
from .i18n import init as init_i18n
from .i18n import is_rtl, t
from .settings import Settings
from .utils import cache_dir

try:
    from .ui.gtk import Adw, Gio, GLib, Gtk

    GTK_AVAILABLE = True
except (ImportError, ValueError):  # pragma: no cover - depends on the system
    GTK_AVAILABLE = False

log = logging.getLogger(__name__)

BACKGROUND_FLAG = "--background"

# (action, accelerators, translation key shown in the shortcuts dialog)
SHORTCUTS = (
    ("win.refresh", ["<Control>r", "F5"], "action.refresh"),
    ("app.preferences", ["<Control>comma"], "page.settings"),
    ("app.shortcuts", ["<Control>question"], "menu.shortcuts"),
    ("app.quit", ["<Control>q"], "menu.quit"),
)


def _write_startup_log() -> None:
    try:
        path = cache_dir() / "startup-error.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(traceback.format_exc())
    except OSError:
        pass


if GTK_AVAILABLE:

    class NetScopeApp(Adw.Application):
        def __init__(self, settings: Settings, start_hidden: bool = False):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.settings = settings
            self.start_hidden = start_hidden
            self._held = False

        # -- lifecycle --------------------------------------------------------

        def do_startup(self):
            Adw.Application.do_startup(self)
            for name, handler in (
                ("preferences", lambda *_: self._window().open_preferences()),
                ("shortcuts", lambda *_: self._show_shortcuts()),
                ("about", lambda *_: self._show_about()),
                ("show", lambda *_: self.activate()),
                ("quit", lambda *_: self._quit()),
            ):
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", handler)
                self.add_action(action)
            for action, accels, _key in SHORTCUTS:
                self.set_accels_for_action(action, accels)
            from .ui.pages import PAGES

            for index, page in enumerate(PAGES, start=1):
                self.set_accels_for_action(f"win.go-page::{page.name}", [f"<Control>{index}"])

        def do_activate(self):
            from .ui.window import MainWindow

            try:
                window = self.props.active_window or next(iter(self.get_windows()), None)
                if window is None:
                    window = MainWindow(self, self.settings)
                    if self.start_hidden:
                        self.start_hidden = False
                        self.keep_running()
                        return
                window.present()
            except Exception as exc:
                _write_startup_log()
                print(f"NetScope failed to start: {exc}", file=sys.stderr)
                raise

        # -- API used by the window --------------------------------------------

        def keep_running(self) -> None:
            """Keep the process alive (alerts, quota) while no window is visible."""
            if not self._held:
                self._held = True
                self.hold()

        def notify(self, title: str, body: str, notification_id: str = "netscope") -> None:
            notification = Gio.Notification.new(title)
            notification.set_body(body)
            notification.set_default_action("app.show")
            self.send_notification(notification_id, notification)

        def apply_language(self) -> None:
            init_i18n(self.settings.language)
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR)

        # -- actions -----------------------------------------------------------

        def _window(self):
            self.activate()
            return self.props.active_window or self.get_windows()[0]

        def _quit(self):
            for window in self.get_windows():
                if hasattr(window, "save_state"):
                    window.save_state()
            self.quit()

        def _show_about(self):
            about = Adw.AboutDialog(
                application_name=t("app.name"),
                application_icon=APP_ID,
                version=__version__,
                developer_name="miro (hoba101)",
                copyright="© 2026 miro (hoba101)",
                license_type=Gtk.License.GPL_3_0,
                website="https://github.com/hoba101/netscope",
                issue_url="https://github.com/hoba101/netscope/issues",
                comments=t("overview.subtitle"),
            )
            about.present(self._window())

        def _show_shortcuts(self):
            parent = self._window()
            if not hasattr(Adw, "ShortcutsDialog"):  # libadwaita < 1.8
                parent.toast(" • ".join(f"{t(key)}: {accels[0]}" for _a, accels, key in SHORTCUTS))
                return
            dialog = Adw.ShortcutsDialog()
            general = Adw.ShortcutsSection(title=t("menu.general"))
            for _action, accels, key in SHORTCUTS:
                general.add(Adw.ShortcutsItem.new(t(key), " ".join(accels)))
            dialog.add(general)
            pages = Adw.ShortcutsSection(title=t("menu.navigation"))
            for name, page in parent.pages.items():
                index = list(parent.pages).index(name) + 1
                pages.add(Adw.ShortcutsItem.new(page.title, f"<Control>{index}"))
            dialog.add(pages)
            dialog.present(parent)


def run_gui(argv: list[str] | None = None) -> int:
    if not GTK_AVAILABLE:
        print("GTK/libadwaita is not available. Use --cli mode.", file=sys.stderr)
        return 1
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("NETSCOPE_DEBUG") else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    argv = list(argv or [sys.argv[0]])
    start_hidden = BACKGROUND_FLAG in argv
    argv = [a for a in argv if a != BACKGROUND_FLAG]
    settings = Settings.load()
    app = NetScopeApp(settings, start_hidden=start_hidden)
    app.apply_language()
    GLib.set_application_name(t("app.name"))
    return app.run(argv)
