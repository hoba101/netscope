# Changelog

## 1.1.0 — 2026-11-09

- Desktop redesign: real sidebar, interface switcher, responsive layout, remembered window size and page.
- Data refreshes in the background so the window never freezes.
- Keeps running in the background after closing (alerts and quota stay active); optional start at login.
- One Preferences dialog that saves instantly (general, data, quota, alerts).
- Charts with legend, tooltips, RTL mirroring and system accent colour; live-speed sparkline.
- History ranges, comparison with the previous period, CSV export.
- Speed test with ping, download and upload tiles plus saved history.
- Network devices page (`netscope lan`).
- First-run setup for vnStat, keyboard shortcuts, About dialog, undo for network actions.
- Alerts, quota and diagnostics fully translated to Arabic.
- Code split into `netscope/ui/` page modules; test suite and lint in CI.

## 1.0.0 — 2026-11-09

- Initial professional release of **NetScope** by miro (hoba101).
- Linux GTK4/libadwaita interface with Arabic and English support.
- Reads vnStat CLI JSON history.
- Recovers old stored vnStat SQLite database history when available.
- Shows live speed, current hour, today, month, 5-minute samples, hourly/daily/monthly/yearly charts, and top usage days.
- Settings: language, theme, refresh, live speed, rate units, history sources, chart ranges.
- CLI with summary, history views, panel output, and JSON export.
- Windows backend/build pipeline and cross-distro packaging metadata (deb, rpm, Arch, Flatpak, Windows).
- Licensed under GPL-3.0-or-later.
