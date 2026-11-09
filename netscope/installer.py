# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import shutil


def detect_package_manager():
    for name in ("dnf", "apt-get", "pacman", "zypper"):
        if shutil.which(name):
            return name
    return None


def install_command(packages: list[str]) -> list[str] | None:
    pm = detect_package_manager()
    pkgs = " ".join(packages)
    if pm == "dnf":
        return ["pkexec", "dnf", "install", "-y", *packages]
    if pm == "apt-get":
        return ["pkexec", "sh", "-c", f"apt-get update && apt-get install -y {pkgs}"]
    if pm == "pacman":
        return ["pkexec", "pacman", "-S", "--noconfirm", *packages]
    if pm == "zypper":
        return ["pkexec", "zypper", "--non-interactive", "install", *packages]
    return None


def service_enable_command(service: str) -> list[str] | None:
    if not shutil.which("systemctl"):
        return None
    return ["pkexec", "systemctl", "enable", "--now", service]
