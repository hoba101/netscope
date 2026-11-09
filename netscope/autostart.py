# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start NetScope in the background at login (XDG autostart)."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from . import APP_ID, APP_NAME


def autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "autostart" / f"{APP_ID}.desktop"


def launch_command() -> str:
    exe = shutil.which("netscope")
    base = [exe] if exe else [sys.executable, "-m", "netscope"]
    return shlex.join([*base, "--gui", "--background"])


def is_enabled() -> bool:
    return autostart_path().exists()


def set_enabled(enabled: bool) -> None:
    path = autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={launch_command()}\n"
        f"Icon={APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n",
        encoding="utf-8",
    )
