# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK 4 / libadwaita user interface.

Layout:
    gtk.py        GI version pinning; import Adw/Gtk/GLib from here
    widgets.py    reusable widgets (cards, pills, Chart, MetricCard) and CSS
    tasks.py      run blocking work off the main loop
    window.py     MainWindow: navigation, refresh timers, shared state
    settings_dialog.py
    pages/        one module per sidebar page, each a ``Page`` subclass
"""
