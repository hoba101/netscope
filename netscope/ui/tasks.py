# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run blocking work on a background thread and hand the result back to GTK."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from .gtk import GLib

log = logging.getLogger(__name__)


def run_async(work: Callable[[], Any], on_done: Callable[[Any, BaseException | None], None]) -> None:
    """Call ``work()`` on a daemon thread, then ``on_done(result, error)`` on the main loop."""

    def runner():
        try:
            result, error = work(), None
        except Exception as exc:
            log.exception("background task failed")
            result, error = None, exc
        GLib.idle_add(lambda: on_done(result, error) and False)

    threading.Thread(target=runner, daemon=True).start()


def idle(func: Callable[..., Any], *args: Any) -> None:
    """Schedule ``func(*args)`` once on the main loop (safe from any thread)."""
    GLib.idle_add(lambda: func(*args) and False)
