# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ... import speedtest, storage
from ...i18n import t
from ...netinfo import link_info
from ...utils import fmt_bytes
from ..gtk import Adw, Gtk
from ..tasks import idle, run_async
from ..widgets import StatTile, boxed_list, button, button_row, card, clear, flow, hint, label, page_scroller
from .base import Page


class SpeedTestPage(Page):
    name = "speedtest"
    icon = "speedometer-symbolic"
    title_key = "page.speedtest"
    subtitle_key = "speedtest.subtitle"

    def build(self):
        scroller, column = page_scroller()
        tiles = flow(3)
        self.ping_tile = StatTile(t("speedtest.ping"), "network-transmit-receive-symbolic", "ms")
        self.down_tile = StatTile(t("summary.download"), "go-down-symbolic", "Mbps")
        self.up_tile = StatTile(t("summary.upload"), "go-up-symbolic", "Mbps")
        for tile in (self.ping_tile, self.down_tile, self.up_tile):
            tiles.append(tile)
        column.append(tiles)

        run = card()
        self.full_btn = button(t("speedtest.run_full"), self.run_full, "suggested-action")
        self.latency_btn = button(t("speedtest.run_basic"), self.run_latency)
        run.append(button_row(self.full_btn, self.latency_btn))
        self.phase = label("", "small")
        self.progress = Gtk.ProgressBar(show_text=True)
        run.append(self.phase)
        run.append(self.progress)
        self.details = hint(selectable=True)
        run.append(self.details)
        run.append(hint(t("speedtest.notice_full")))
        column.append(run)

        info = card(t("label.status"))
        self.link = label("", "small", selectable=True)
        info.append(self.link)
        column.append(info)

        past = card(t("speedtest.history"))
        self.history = boxed_list()
        past.append(self.history)
        column.append(past)
        self._render_history()
        return scroller

    def on_snapshot(self, snap):
        iface = self.window.iface() or "?"
        info = link_info(iface)
        parts = [f"{t('status.interface')}: {iface}"]
        if "operstate" in info:
            parts.append(f"{t('speedtest.state')}: {info['operstate']}")
        if "speed" in info and not info["speed"].startswith("-"):
            parts.append(f"{t('speedtest.link')}: {info['speed']} Mbps")
        self.link.set_text("  •  ".join(parts))

    def _set_busy(self, busy: bool):
        self.full_btn.set_sensitive(not busy)
        self.latency_btn.set_sensitive(not busy)

    def _progress(self, phase_key: str, size: int):
        def report(total, mbps):
            idle(self.progress.set_fraction, min(1.0, total / size))
            idle(self.progress.set_text, f"{fmt_bytes(total)} — {mbps:.1f} Mbps")

        idle(self.phase.set_text, t(phase_key))
        return report

    def run_latency(self):
        self._set_busy(True)
        self.phase.set_text(t("speedtest.phase_ping"))
        run_async(
            lambda: speedtest.run_latency(lambda f: idle(self.progress.set_fraction, f)), self._latency_done
        )

    def _latency_done(self, pings, error):
        self._set_busy(False)
        self.phase.set_text("")
        if error:
            self.details.set_text(str(error))
            return
        self.ping_tile.set_value(_best_ping(pings))
        self.details.set_text("\n".join(f"{p.name} ({p.host}): {p.summary}" for p in pings))

    def run_full(self):
        self._set_busy(True)
        for tile in (self.ping_tile, self.down_tile, self.up_tile):
            tile.set_value(None)
        iface = self.window.iface()

        def work():
            idle(self.phase.set_text, t("speedtest.phase_ping"))
            pings = speedtest.run_latency()
            down = speedtest.run_download(
                speedtest.DEFAULT_DOWNLOAD_BYTES,
                self._progress("speedtest.phase_download", speedtest.DEFAULT_DOWNLOAD_BYTES),
            )
            idle(self.down_tile.set_value, down.mbit_per_s)
            up = speedtest.run_upload(
                speedtest.DEFAULT_UPLOAD_BYTES,
                self._progress("speedtest.phase_upload", speedtest.DEFAULT_UPLOAD_BYTES),
            )
            ping = _best_ping(pings)
            storage.add_speedtest(iface, ping, down.mbit_per_s, up.mbit_per_s)
            return pings, ping, down, up

        def done(result, error):
            self._set_busy(False)
            self.phase.set_text("")
            if error:
                self.details.set_text(t("speedtest.failed", error=error))
                return
            pings, ping, down, up = result
            self.ping_tile.set_value(ping)
            self.down_tile.set_value(down.mbit_per_s)
            self.up_tile.set_value(up.mbit_per_s)
            self.progress.set_fraction(1.0)
            self.progress.set_text(t("speedtest.done"))
            self.details.set_text("\n".join(f"{p.name} ({p.host}): {p.summary}" for p in pings))
            self._render_history()

        run_async(work, done)

    def _render_history(self):
        clear(self.history)
        rows = storage.list_speedtests(10)
        if not rows:
            self.history.append(Adw.ActionRow(title=t("speedtest.no_history")))
            return
        for r in rows:
            ping = f"{r['ping_ms']:.0f} ms" if r["ping_ms"] is not None else "—"
            row = Adw.ActionRow(
                title=f"↓ {r['down_mbps'] or 0:.1f}  ↑ {r['up_mbps'] or 0:.1f} Mbps",
                subtitle=f"{r['ts'].replace('T', ' ')} • {r['interface']} • {t('speedtest.ping')} {ping}",
            )
            self.history.append(row)


def _best_ping(pings) -> float | None:
    values = [v for v in (speedtest.parse_ping_avg(p.summary) for p in pings if p.ok) if v is not None]
    return min(values) if values else None
