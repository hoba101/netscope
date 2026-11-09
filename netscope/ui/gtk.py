# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""The single place that pins GI versions. UI modules import GTK names from here.

Importing this module raises ``ImportError``/``ValueError`` when GTK 4 or
libadwaita is missing; :mod:`netscope.app` turns that into ``GTK_AVAILABLE``.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

__all__ = ["Adw", "Gdk", "Gio", "GLib", "Gtk"]
