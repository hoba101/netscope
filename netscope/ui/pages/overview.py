# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime

from ...i18n import t
from ...quota import evaluate as evaluate_quota
from ...series import day_points, hour_points, month_points, usage_this_hour, usage_this_month, usage_today
from ...utils import fmt_bytes, fmt_clock, fmt_datetime, fmt_rate, is_linux, month_name
from ..gtk import Adw, Gtk
from ..widgets import (
    Chart,
    MetricCard,
    Sparkline,
    button,
    card,
    flow,
    hint,
    label,
    legend,
    page_scroller,
    status_page,
)
from .base import Page

# Sources that only provide live counters, i.e. no long-term history.
_COUNTER_ONLY = {"Linux counters", "Windows counters"}


class OverviewPage(Page):
    name = "overview"
    icon = "view-grid-symbolic"
    title_key = "page.overview"
    subtitle_key = "overview.subtitle"

    def build(self):
        self.views = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        retry = button(t("action.refresh"), self.window.refresh, "suggested-action", halign=Gtk.Align.CENTER)
        retry.add_css_class("pill")
        self.views.add_named(
            status_page("network-offline-symbolic", t("empty.no_data"), t("empty.no_data_hint"), retry),
            "empty",
        )
        self.views.add_named(self._build_content(), "content")
        self.views.set_visible_child_name("content")
        return self.views

    def _build_content(self):
        scroller, column = page_scroller()
        self.history_banner = Adw.Banner(title=t("banner.no_history"), revealed=False)
        if is_linux():
            self.history_banner.set_button_label(t("onboarding.fix"))
            self.history_banner.connect("button-clicked", lambda *_: self.window.setup_vnstat())
        self.quota_banner = Adw.Banner(revealed=False, button_label=t("prefs.open"))
        self.quota_banner.connect("button-clicked", lambda *_: self.window.open_preferences("quota"))
        column.append(self.history_banner)
        column.append(self.quota_banner)

        metrics = flow(4)
        self.month_card = MetricCard(t("summary.month"), "x-office-calendar-symbolic")
        self.today_card = MetricCard(t("summary.today"), "weather-clear-symbolic")
        self.hour_card = MetricCard(t("summary.hour"), "preferences-system-time-symbolic")
        self.live_card = MetricCard(t("summary.live"), "network-transmit-receive-symbolic")
        self.sparkline = Sparkline()
        self.live_card.append(self.sparkline)
        self.live_on = button(t("overview.live_turn_on"), self._enable_live, halign=Gtk.Align.START)
        self.live_on.set_visible(False)
        self.live_card.append(self.live_on)
        for widget in (self.month_card, self.today_card, self.hour_card, self.live_card):
            metrics.append(widget)
        column.append(metrics)

        quota = card(t("quota.status"))
        self.quota_label = label("", "small")
        self.quota_bar = Gtk.ProgressBar(show_text=True)
        quota.append(self.quota_label)
        quota.append(self.quota_bar)
        column.append(quota)

        self.hour_title = label("", "h2")
        hours = card()
        hours.append(self.hour_title)
        self.hour_chart = Chart(210)
        hours.append(self.hour_chart)
        hours.append(legend())
        column.append(hours)

        grid = flow(2)
        self.day_title, self.month_title = label("", "h2"), label("", "h2")
        self.day_chart, self.month_chart = Chart(180), Chart(180)
        for title, chart in ((self.day_title, self.day_chart), (self.month_title, self.month_chart)):
            box = card()
            box.append(title)
            box.append(chart)
            grid.append(box)
        column.append(grid)

        self.footer = hint()
        column.append(self.footer)
        return scroller

    def on_snapshot(self, snap):
        if snap is None:
            self.views.set_visible_child_name("empty")
            return
        self.views.set_visible_child_name("content")
        now = datetime.now()
        today = now.date()
        s = self.settings
        self.history_banner.set_revealed(set(snap.sources) <= _COUNTER_ONLY)
        self.month_card.set_bytes(usage_this_month(snap, today), f"{month_name(today.month)} {today.year}")
        self.today_card.set_bytes(usage_today(snap, today), today.isoformat())
        self.hour_card.set_bytes(
            usage_this_hour(snap, now), f"{fmt_clock(now.hour)}–{fmt_clock((now.hour + 1) % 24)}"
        )
        self._show_rates(snap.live_rx_bps, snap.live_tx_bps)

        self.hour_title.set_text(t("chart.hours", count=s.chart_hours))
        self.day_title.set_text(t("chart.days", count=s.chart_days))
        self.month_title.set_text(t("chart.months", count=s.chart_months))
        self.hour_chart.set_data(hour_points(snap, s.chart_hours, now), max(1, s.chart_hours // 6))
        self.day_chart.set_data(day_points(snap, s.chart_days, today), max(1, s.chart_days // 6))
        self.month_chart.set_data(month_points(snap, s.chart_months, today), max(1, s.chart_months // 6))
        self.render_quota(snap)

        created = fmt_datetime(snap.interface.created) if snap.interface.created else t("label.unknown")
        self.footer.set_text(
            f"{t('status.sources')}: {', '.join(snap.sources)}  •  "
            f"{t('status.recording_since')}: {created}  •  {t('status.updated')}: {now:%H:%M:%S}"
        )

    def on_live_rates(self, rx_bps, tx_bps):
        self._show_rates(rx_bps, tx_bps)
        self.live_card.caption.set_text(self.window.iface())
        self.sparkline.push(rx_bps + tx_bps)

    def _show_rates(self, rx_bps, tx_bps):
        live = self.settings.live_speed
        self.live_on.set_visible(not live)
        self.sparkline.set_visible(live)
        if not live:
            self.live_card.set_text("—", "—", "—", t("overview.live_off"))
            return
        unit = self.settings.rate_unit
        self.live_card.set_text(
            fmt_rate(rx_bps + tx_bps, unit), fmt_rate(rx_bps, unit), fmt_rate(tx_bps, unit)
        )

    def _enable_live(self):
        self.settings.live_speed = True
        self.settings.save()
        self.window.on_setting_changed("live_speed")

    def render_quota(self, snap):
        s = self.settings
        if not s.quota_enabled:
            self.quota_label.set_text(f"{t('quota.not_enabled')} — {t('quota.enable_hint')}")
            self.quota_bar.set_fraction(0)
            self.quota_bar.set_text("")
            self.quota_banner.set_revealed(False)
            return
        q = evaluate_quota(snap, s)
        self.quota_bar.set_fraction(min(1.0, max(0.0, q.used_bytes / max(1, q.limit_bytes))))
        self.quota_bar.set_text(
            f"{q.percent:.1f}%  •  {fmt_bytes(q.used_bytes)} / {fmt_bytes(q.limit_bytes)}"
        )
        remaining = max(0, q.limit_bytes - q.used_bytes)
        self.quota_label.set_text(
            f"{t('quota.used')}: {fmt_bytes(q.used_bytes)}  •  {t('quota.remaining')}: {fmt_bytes(remaining)}"
            f"  •  {t('settings.quota_action')}: {t('settings.quota_action.' + s.quota_action)}"
        )
        self.quota_banner.set_title(t("banner.quota_exceeded") if q.exceeded else t("banner.quota_warn"))
        self.quota_banner.set_revealed(q.exceeded or q.warn)
