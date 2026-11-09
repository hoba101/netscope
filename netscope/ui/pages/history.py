# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime

from ...i18n import t
from ...series import HISTORY_PERIODS, RANGE_CHOICES, compare_periods, history_points, to_csv
from ...utils import fmt_bytes
from ..gtk import Adw, Gtk
from ..widgets import Chart, boxed_list, button, card, clear, hint, label, legend, page_scroller, save_file
from .base import Page

# Translation keys for HISTORY_PERIODS, in the same order.
_PERIOD_KEYS = (
    "history.fiveminute",
    "history.hourly",
    "history.daily",
    "history.monthly",
    "history.yearly",
    "history.top",
)
_RANGE_KEYS = {
    "fiveminute": "history.range.samples",
    "hour": "chart.hours",
    "day": "chart.days",
    "month": "chart.months",
}


class HistoryPage(Page):
    name = "history"
    icon = "document-open-recent-symbolic"
    title_key = "page.history"
    subtitle_key = "history.subtitle"

    def build(self):
        self.points = []
        scroller, column = page_scroller()
        controls = card()
        row = Gtk.Box(spacing=8)
        self.period = Gtk.DropDown.new_from_strings([t(k) for k in _PERIOD_KEYS])
        self.period.set_selected(HISTORY_PERIODS.index("day"))
        self.range = Gtk.DropDown.new_from_strings([""])
        row.append(Gtk.Label(label=t("history.period")))
        row.append(self.period)
        row.append(self.range)
        row.append(Gtk.Box(hexpand=True))
        row.append(button(t("history.export_csv"), self.export_csv))
        controls.append(row)
        self.compare = label("", "small")
        controls.append(self.compare)
        column.append(controls)

        body = card()
        self.chart = Chart(260)
        body.append(self.chart)
        body.append(legend())
        self.rows = boxed_list()
        body.append(self.rows)
        column.append(body)

        self._update_ranges()
        self.period.connect("notify::selected", lambda *_: (self._update_ranges(), self.render()))
        self.range.connect("notify::selected", lambda *_: self.render())
        return scroller

    @property
    def _period(self) -> str:
        return HISTORY_PERIODS[self.period.get_selected()]

    def _update_ranges(self):
        choices = RANGE_CHOICES[self._period]
        key = _RANGE_KEYS.get(self._period)
        self.range.set_visible(bool(choices))
        if choices:
            self.range.set_model(Gtk.StringList.new([t(key, count=n) for n in choices]))
            defaults = {
                "hour": self.settings.chart_hours,
                "day": self.settings.chart_days,
                "month": self.settings.chart_months,
            }
            wanted = defaults.get(self._period, choices[1] if len(choices) > 1 else choices[0])
            closest = min(range(len(choices)), key=lambda i: abs(choices[i] - wanted))
            self.range.set_selected(closest)

    @property
    def _count(self) -> int | None:
        choices = RANGE_CHOICES[self._period]
        return choices[self.range.get_selected()] if choices else None

    def on_snapshot(self, snap):
        self.render()

    def render(self):
        snap = self.window.snap
        if not snap:
            return
        period, count = self._period, self._count
        self.points, step = history_points(snap, period, count)
        self.chart.set_data(self.points, step)

        totals = compare_periods(snap, period, count) if count else None
        if totals:
            current, previous = totals
            change = f" ({(current - previous) / previous * 100:+.0f}%)" if previous else ""
            self.compare.set_text(
                f"{t('history.total')}: {fmt_bytes(current)}  •  {t('history.previous')}: {fmt_bytes(previous)}{change}"
            )
        else:
            self.compare.set_text(f"{t('history.total')}: {fmt_bytes(sum(p.total for p in self.points))}")

        if period == "top":
            listed = sorted(self.points, key=lambda p: p.total, reverse=True)[:20]
        else:
            listed = [p for p in reversed(self.points) if p.total > 0][:20]
        clear(self.rows)
        if not listed:
            self.rows.append(Adw.ActionRow(title=t("chart.empty")))
        for p in listed:
            row = Adw.ActionRow(
                title=p.detail or p.label, subtitle=f"↓ {fmt_bytes(p.rx)}   ↑ {fmt_bytes(p.tx)}"
            )
            row.add_suffix(hint(fmt_bytes(p.total), wrap=False))
            self.rows.append(row)

    def export_csv(self):
        name = f"netscope-{self._period}-{datetime.now():%Y%m%d}.csv"

        def saved(path, error):
            self.window.toast(str(error) if error else f"{t('toast.exported')}: {path}")

        save_file(self.window, t("history.export_csv"), name, lambda: to_csv(self.points), saved)
