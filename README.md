<div align="center">

# NetScope / نت سكوب

**Professional network usage analytics for Linux & Windows**  
*Live speed, deep history, smart alerts, controls, and old-data recovery — in a polished GTK/libadwaita experience.*

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3%2B-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-2ea44f)
![UI](https://img.shields.io/badge/UI-GTK4%20%2F%20libadwaita-4a86cf)
![Languages](https://img.shields.io/badge/languages-English%20%7C%20العربية-6f42c1)

</div>

## Overview

**NetScope** (نت سكوب) is a cross-platform network usage monitor and control center built by **miro** ([hoba101](https://github.com/hoba101)). It combines accurate live monitoring, historical analytics, smart alerts, and user-confirmed network controls in a clean, UI/UX-focused interface.

**ملخص عربي:** NetScope برنامج احترافي لمراقبة استهلاك الإنترنت والسرعة والسجل والتنبيهات الذكية والتحكم بالشبكة، مع دعم العربية والإنجليزية، واستعادة بيانات vnStat القديمة المخزنة عندما تكون متاحة.

## Features

### Monitoring & history
- **Live speed** (download/upload/total) with current interface context.
- **Current hour, today, and this month** usage cards.
- **Deep history views:** 5-minute samples, hourly, daily, monthly, yearly, and top usage days.
- **History recovery (Linux/vnStat):** reads `vnstat --json` and, when readable, the **vnStat SQLite database** directly (e.g. `/var/lib/vnstat/vnstat.db`) to recover old stored usage that already exists on the device.
- **NetScope history store:** keeps its own local SQLite history for continuity (`~/.local/share/netscope/history.db` on Linux, `%LOCALAPPDATA%\NetScope\history.db` on Windows).

### Accuracy & diagnostics
- **Multi-source accuracy engine:** correlates available sources such as `sysfs`, `procfs`, `ip -s link`, `nmcli`, `psutil`, vnStat JSON/DB, and Windows counters/PowerShell where applicable.
- **Confidence level** shown in the UI (high/medium/low) with probe details.
- **Diagnostics page:** permissions/capabilities, data sources, recovery status, probe results, copy summary, export JSON.

### Smart alerts (with log)
- **Daily quota alerts** (warning + exceeded).
- **Hourly limit alerts** (separate hourly threshold/warning).
- **Low-speed alerts** when speed stays below a threshold for a sustained duration.
- **Disconnection alerts** (best-effort from system/network state).
- **Network change alerts** (interface/connection/gateway/state changes, best-effort).
- **Alert log** with severity, timestamp, interface, message, read/clear actions.
- **Desktop notifications** (optional, best-effort via `notify-send`).
- **Cooldown/dedup** to reduce alert spam.

### Controls & quota (user-confirmed)
- **Daily quota settings:** enable, MB limit, warning %, and action on exceed (`warn`, `disconnect`, `disable interface`, `throttle`).
- **Network controls:** apply/restore speed limit, disconnect/connect (where supported).
- **Safety-first UX:** disruptive actions require confirmation; privileged actions request permission (e.g. `pkexec`) and are never applied silently.
- **Capability-aware UI:** unsupported features show status/reason and install/enable actions when possible.
- **Linux throttling:** uses `tc` when `iproute-tc` is available.
- **Install/enable helpers (GUI):** can start system install/enable flows with permission (e.g. `iproute-tc`, `vnstat` service) based on detected platform/package manager.

### Speed test
- Dedicated **Speed Test** page.
- **Basic checks:** link/state info, gateway/DNS latency checks, accuracy context.
- **Download test:** user-initiated real throughput test (uses internet data; clear notice shown).

### UX & localization
- **Modern GTK4/libadwaita UI** with navigation: Overview, History, Controls & Quota, Speed Test, Alerts, Diagnostics.
- **Arabic + English** with system detection, RTL support, and language selection.
- **Theme support:** system/light/dark (applies immediately).
- **CLI support:** summaries, history, export JSON, permissions/accuracy/quota/alerts, control commands, `monitor-once`.

## Requirements

### Linux
- Python 3.10+
- GTK4, libadwaita, PyGObject
- Recommended for full history: `vnstat` + `vnstatd`
- Optional for throttling: `iproute-tc` (`tc`)
- Optional for controls/integration: `nmcli` (NetworkManager), `pkexec` (PolicyKit), `notify-send`

### Windows
- Python 3.10+ for source usage, or packaged artifacts from CI/releases
- Optional: `psutil`, PowerShell/NetAdapter cmdlets as available

## Installation

### Linux (user install)
```bash
git clone https://github.com/hoba101/netscope.git
cd netscope
bash scripts/install-linux.sh user
```
Then run:
```bash
netscope --gui
# or
~/.local/bin/netscope --gui
```

### From source
```bash
cd netscope
PYTHONPATH=. python3 -m netscope --gui
PYTHONPATH=. python3 -m netscope --cli summary
PYTHONPATH=. python3 -m netscope --cli export-json > usage.json
PYTHONPATH=. python3 -m netscope --cli alerts
PYTHONPATH=. python3 -m netscope --cli monitor-once
```

## Packaging / distribution

| Target | Path | Notes |
|---|---|---|
| Linux installer | `scripts/install-linux.sh` | User/system install with desktop entry |
| Debian/Ubuntu (.deb) | `packaging/deb/build-deb.sh` | Builds package tree; final `.deb` needs `dpkg-deb`/CI host |
| Fedora/RHEL (.rpm) | `packaging/rpm/netscope.spec` | RPM spec; build with `rpmbuild` |
| Arch Linux | `packaging/arch/PKGBUILD` | PKGBUILD for makepkg/AUR-style workflows |
| Flatpak | `packaging/flatpak/io.github.hoba101.NetScope.yml` | Manifest; host vnStat access may require overrides/native package for full recovery |
| Windows | `packaging/windows/build-windows.ps1` | PyInstaller/CI-oriented packaging flow |
| CI | `.github/workflows/build.yml` | Linux checks + Windows/deb artifact workflows |

## Privacy & permissions

NetScope is designed to be transparent:
- Reads network counters/history from local system sources (vnStat, sysfs/procfs/ip/nmcli, local DBs, Windows counters as available).
- Stores its own history/alerts locally.
- Does **not** silently escalate privileges.
- Network-affecting actions and system installs/enables require explicit user action and confirmation/authorization.

## Troubleshooting

- **Desktop launcher opens CLI/no window (fixed):** use the updated launcher (`Exec=... netscope --gui`) or run `netscope --gui`. If an old instance is stuck, close it or run `pkill -f 'python3 -m netscope --gui'`.
- **Startup logs:** `~/.cache/netscope/startup-error.log` and `/tmp/netscope-gui.log` (session-dependent).
- **Throttle unavailable:** install `iproute-tc` (Fedora: `sudo dnf install -y iproute-tc`) or use the Diagnostics install action.
- **No old history:** install/enable `vnstat`/`vnstatd` for long-term Linux history; NetScope can recover existing readable vnStat DB data when present.

## Copyright and printing/publication rights / حقوق النشر والطبع

**Copyright © 2026 miro (hoba101). All rights reserved where applicable, and all copyright and printing/publication rights are reserved to the author except as granted by the project license.**  
**حقوق النشر والطبع محفوظة لـ miro (hoba101).**

This project is distributed as free/open-source software under the terms of the **GNU General Public License v3.0 or later (GPL-3.0-or-later)**. See [LICENSE](LICENSE).  
The GPL license governs copying, modification, and redistribution of the licensed source code; attribution and copyright notices must be preserved.

- Author: **miro**
- GitHub: [**hoba101**](https://github.com/hoba101)
- Repository: <https://github.com/hoba101/netscope>
- Contact: <https://github.com/hoba101>

## Contributing

Issues and pull requests are welcome after the repository is published. Please preserve copyright notices, test changes, and keep UI/UX changes accessible and consistent.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
