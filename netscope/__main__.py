# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--gui":
        from .app import run_gui
        return run_gui([sys.argv[0]] + argv[1:])
    if argv and argv[0] == "--cli":
        from .cli import run
        return run(argv[1:])
    # Auto: GUI when display is likely available and no explicit subcommand; else CLI.
    import os
    cli_cmds = {"summary", "hours", "days", "months", "years", "top", "interfaces", "export-json", "help", "-h", "--help", "--panel", "5min", "fiveminute", "doctor", "permissions", "accuracy", "quota", "control-status", "control", "monitor-once", "alerts"}
    if argv and (argv[0] in cli_cmds or "--json" in argv or "--panel" in argv):
        from .cli import run
        return run(argv)
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and sys.platform.startswith("linux")
    if not argv and not graphical and not sys.stdout.isatty():
        from .cli import run
        return run(["summary"])
    try:
        from .app import GTK_AVAILABLE, run_gui
        if GTK_AVAILABLE and (graphical or sys.stdout.isatty() or not argv):
            return run_gui([sys.argv[0]] + argv)
    except Exception:
        if not graphical:
            pass
        else:
            try:
                import traceback, pathlib
                log = pathlib.Path.home()/'.cache/netscope/startup-error.log'
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(traceback.format_exc())
            except Exception: pass
    from .cli import run
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
