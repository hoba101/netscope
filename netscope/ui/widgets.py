# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets and the application stylesheet."""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Callable, Sequence

from ..i18n import t
from ..models import UsagePoint
from ..utils import fmt_bytes
from .gtk import Adw, Gdk, GLib, Gtk

log = logging.getLogger(__name__)

CSS = r"""
window { font-family: "Vazirmatn","Noto Sans Arabic","Cantarell",sans-serif; }
.cardx { padding: 16px 18px; border-radius: 18px; background: alpha(@card_bg_color, 0.92); }
.metric-card { padding: 14px 16px; border-radius: 16px; background: alpha(@card_bg_color, 0.92); }
.big { font-size: 30px; font-weight: 800; }
.stat { font-size: 26px; font-weight: 800; }
.h2 { font-size: 14px; font-weight: 700; }
.muted { opacity: 0.66; }
.small { font-size: 11.5px; }
.dl { color: @accent_color; font-weight: 700; }
.ul { color: #e68c33; font-weight: 700; }
.good { color: @success_color; }
.warn { color: @warning_color; }
.bad { color: @error_color; }
.pill { border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 700; background: alpha(@window_fg_color,0.08); }
.swatch { min-width: 10px; min-height: 10px; border-radius: 3px; }
.swatch.rx { background: @accent_bg_color; }
.swatch.tx { background: #e68c33; }
"""

TX_COLOR = (0.90, 0.55, 0.20)


def accent_rgb() -> tuple[float, float, float]:
    """The system accent colour (libadwaita ≥ 1.6), with a blue fallback."""
    manager = Adw.StyleManager.get_default()
    if hasattr(manager, "get_accent_color_rgba"):
        c = manager.get_accent_color_rgba()
        return (c.red, c.green, c.blue)
    return (0.21, 0.52, 0.89)


def fg_rgb() -> tuple[float, float, float]:
    return (1, 1, 1) if Adw.StyleManager.get_default().get_dark() else (0, 0, 0)


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def label(text: str = "", *classes: str, **props) -> Gtk.Label:
    """A start-aligned, wrapping label with optional CSS classes."""
    props.setdefault("xalign", 0)
    props.setdefault("wrap", True)
    widget = Gtk.Label(label=text, **props)
    for cls in classes:
        widget.add_css_class(cls)
    return widget


def hint(text: str = "", **props) -> Gtk.Label:
    """Small, muted secondary text."""
    return label(text, "muted", "small", **props)


def pill(text: str, cls: str = "") -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.add_css_class("pill")
    if cls:
        widget.add_css_class(cls)
    return widget


def button(text: str, on_click: Callable[..., object], style: str = "", **props) -> Gtk.Button:
    widget = Gtk.Button(label=text, **props)
    if style:
        widget.add_css_class(style)
    widget.connect("clicked", lambda *_: on_click())
    return widget


def button_row(*buttons: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(spacing=8)
    for b in buttons:
        row.append(b)
    return row


def card(title: str | None = None, subtitle: str | None = None) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.add_css_class("cardx")
    if title:
        box.append(label(title, "h2"))
    if subtitle:
        box.append(hint(subtitle))
    return box


def boxed_list() -> Gtk.ListBox:
    widget = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    widget.add_css_class("boxed-list")
    return widget


def vbox(spacing: int = 8) -> Gtk.Box:
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def clear(container: Gtk.Widget) -> None:
    """Remove every child from a Gtk.Box / Gtk.ListBox / Gtk.FlowBox."""
    while child := container.get_first_child():
        container.remove(child)


def status_page(
    icon: str, title: str, description: str = "", child: Gtk.Widget | None = None
) -> Adw.StatusPage:
    page = Adw.StatusPage(icon_name=icon, title=title, description=description)
    if child:
        page.set_child(child)
    return page


def compact_status(icon: str, title: str, description: str = "") -> Adw.StatusPage:
    """A small status page for empty lists inside cards."""
    page = status_page(icon, title, description)
    page.add_css_class("compact")
    return page


def page_scroller() -> tuple[Gtk.ScrolledWindow, Gtk.Box]:
    """A scrolling, width-clamped column that pages append their cards to."""
    scroller = Gtk.ScrolledWindow(vexpand=True)
    clamp = Adw.Clamp(maximum_size=1100, tightening_threshold=760)
    column = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=14,
        margin_top=18,
        margin_bottom=24,
        margin_start=16,
        margin_end=16,
    )
    clamp.set_child(column)
    scroller.set_child(clamp)
    return scroller, column


def flow(max_per_line: int) -> Gtk.FlowBox:
    return Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        homogeneous=True,
        max_children_per_line=max_per_line,
        min_children_per_line=1,
        column_spacing=12,
        row_spacing=12,
    )


def legend() -> Gtk.Box:
    """Colour key for rx/tx charts."""
    box = Gtk.Box(spacing=14)
    for cls, text in (("rx", t("summary.download")), ("tx", t("summary.upload"))):
        item = Gtk.Box(spacing=6)
        swatch = Gtk.Box(valign=Gtk.Align.CENTER)
        swatch.add_css_class("swatch")
        swatch.add_css_class(cls)
        item.append(swatch)
        item.append(hint(text, wrap=False))
        box.append(item)
    return box


def save_file(
    parent: Gtk.Window, title: str, initial_name: str, content: Callable[[], str], on_saved=None
) -> None:
    """Ask for a destination with Gtk.FileDialog and write ``content()`` there."""
    dialog = Gtk.FileDialog(title=title, initial_name=initial_name)

    def finished(dlg, result):
        try:
            gfile = dlg.save_finish(result)
        except GLib.Error:
            return  # cancelled
        path = gfile.get_path()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content())
        except OSError as exc:
            log.exception("could not save %s", path)
            if on_saved:
                on_saved(None, exc)
            return
        if on_saved:
            on_saved(path, None)

    dialog.save(parent, None, finished)


def nice_ceiling(value: float) -> float:
    """Round ``value`` (plus 10% headroom) up to a readable axis maximum."""
    if value <= 0:
        return 1.0
    padded = value * 1.1
    base = 10 ** math.floor(math.log10(padded))
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if padded / base <= step:
            return step * base
    return 10 * base


class Chart(Gtk.DrawingArea):
    """Stacked rx/tx bar chart with tooltips; mirrors itself in RTL layouts."""

    AXIS_MARGIN, EDGE_MARGIN, MARGIN_TOP, MARGIN_BOTTOM = 68, 12, 12, 32

    def __init__(self, height: int = 200):
        super().__init__()
        self.set_content_height(height)
        self.set_hexpand(True)
        self.points: list[UsagePoint] = []
        self.hover = -1
        self.step = 4
        self.set_draw_func(self._draw)
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._tooltip)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._motion)
        motion.connect("leave", self._leave)
        self.add_controller(motion)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self.queue_draw())

    def set_data(self, points: Sequence[UsagePoint], step: int = 4) -> None:
        self.points = list(points)
        self.step = max(1, step)
        self.hover = -1
        self.queue_draw()

    @property
    def _rtl(self) -> bool:
        return self.get_direction() == Gtk.TextDirection.RTL

    def _plot_rect(self) -> tuple[float, float, float, float]:
        width = max(1, self.get_width())
        height = max(1, self.get_height())
        left = self.EDGE_MARGIN if self._rtl else self.AXIS_MARGIN
        plot_w = max(1, width - self.AXIS_MARGIN - self.EDGE_MARGIN)
        plot_h = max(1, height - self.MARGIN_TOP - self.MARGIN_BOTTOM)
        return left, self.MARGIN_TOP, plot_w, plot_h

    def _slot_x(self, index: int, left: float, slot: float) -> float:
        position = len(self.points) - 1 - index if self._rtl else index
        return left + position * slot

    def _index_at(self, x: float) -> int:
        left, _top, plot_w, _h = self._plot_rect()
        if not self.points or x < left or x > left + plot_w:
            return -1
        position = max(0, min(int((x - left) / (plot_w / len(self.points))), len(self.points) - 1))
        return len(self.points) - 1 - position if self._rtl else position

    def _motion(self, _ctrl, x, _y):
        index = self._index_at(x)
        if index != self.hover:
            self.hover = index
            self.queue_draw()

    def _leave(self, _ctrl):
        self.hover = -1
        self.queue_draw()

    def _tooltip(self, _widget, x, _y, _keyboard, tooltip):
        index = self._index_at(x)
        if index < 0:
            return False
        p = self.points[index]
        tooltip.set_text(
            f"{p.detail or p.label}\n{fmt_bytes(p.total)}  (↓ {fmt_bytes(p.rx)}  ↑ {fmt_bytes(p.tx)})"
        )
        return True

    def _draw(self, _area, cr, width, height, _data=None):
        left, top, plot_w, plot_h = self._plot_rect()
        base = top + plot_h
        fg = fg_rgb()
        rx_color = accent_rgb()
        cr.set_font_size(9)

        peak = max((p.total for p in self.points), default=0)
        if peak <= 0:
            cr.set_source_rgba(*fg, 0.45)
            cr.set_font_size(12)
            text = t("chart.empty")
            ext = cr.text_extents(text)
            cr.move_to(width / 2 - ext.width / 2, height / 2)
            cr.show_text(text)
            return

        axis_max = nice_ceiling(peak)
        slot = plot_w / len(self.points)

        for i in range(5):
            y = base - plot_h * i / 4
            cr.set_source_rgba(*fg, 0.08)
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            text = "0" if i == 0 else fmt_bytes(axis_max * i / 4)
            ext = cr.text_extents(text)
            cr.set_source_rgba(*fg, 0.5)
            cr.move_to(left + plot_w + 6 if self._rtl else left - 6 - ext.width, y + 3)
            cr.show_text(text)

        for i, p in enumerate(self.points):
            if p.total <= 0:
                continue
            bar_h = max(2, plot_h * p.total / axis_max)
            bar_w = min(slot * 0.62, 42)
            x = self._slot_x(i, left, slot) + (slot - bar_w) / 2
            y = base - bar_h
            rx_h = bar_h * p.rx / p.total
            alpha = 1.0 if self.hover in (-1, i) else 0.55
            cr.set_source_rgba(*rx_color, alpha)
            cr.rectangle(x, base - rx_h, bar_w, rx_h)
            cr.fill()
            cr.set_source_rgba(*TX_COLOR, alpha)
            cr.rectangle(x, y, bar_w, bar_h - rx_h)
            cr.fill()

        offset = (len(self.points) - 1) % self.step
        cr.set_source_rgba(*fg, 0.5)
        for i, p in enumerate(self.points):
            if (i - offset) % self.step:
                continue
            ext = cr.text_extents(p.label)
            cr.move_to(self._slot_x(i, left, slot) + slot / 2 - ext.width / 2, base + 16)
            cr.show_text(p.label)


class Sparkline(Gtk.DrawingArea):
    """The last ``size`` live-rate samples as a filled line."""

    def __init__(self, size: int = 60, height: int = 36):
        super().__init__()
        self.samples: deque[float] = deque([0.0] * size, maxlen=size)
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, value: float) -> None:
        self.samples.append(max(0.0, value))
        self.queue_draw()

    def _draw(self, _area, cr, width, height, _data=None):
        peak = max(self.samples) or 1.0
        n = len(self.samples)
        rtl = self.get_direction() == Gtk.TextDirection.RTL
        r, g, b = accent_rgb()

        def point(i, v):
            x = width * i / (n - 1)
            return (width - x if rtl else x), height - 2 - (height - 4) * v / peak

        cr.move_to(*point(0, self.samples[0]))
        for i, v in enumerate(self.samples):
            cr.line_to(*point(i, v))
        cr.set_source_rgba(r, g, b, 0.9)
        cr.set_line_width(1.6)
        cr.stroke_preserve()
        cr.line_to(*point(n - 1, 0))
        cr.line_to(*point(0, 0))
        cr.close_path()
        cr.set_source_rgba(r, g, b, 0.15)
        cr.fill()


class MetricCard(Gtk.Box):
    """A headline number with download/upload breakdown."""

    def __init__(self, title: str, icon: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("metric-card")
        header = Gtk.Box(spacing=8)
        image = Gtk.Image.new_from_icon_name(icon)
        image.add_css_class("muted")
        header.append(image)
        header.append(label(title, "h2", "muted", hexpand=True, wrap=False))
        self.append(header)
        self.value = label("—", "big", wrap=False)
        self.append(self.value)
        row = Gtk.Box(spacing=10)
        self.down = label("", "dl", wrap=False)
        self.up = label("", "ul", wrap=False)
        row.append(self.down)
        row.append(self.up)
        self.append(row)
        self.caption = hint()
        self.append(self.caption)

    def set_text(self, value: str, down: str, up: str, caption: str | None = None) -> None:
        self.value.set_text(value)
        self.down.set_text(f"↓ {down}")
        self.up.set_text(f"↑ {up}")
        if caption is not None:
            self.caption.set_text(caption)

    def set_bytes(self, point: UsagePoint | None, caption: str = "") -> None:
        rx, tx = (point.rx, point.tx) if point else (0, 0)
        self.set_text(fmt_bytes(rx + tx), fmt_bytes(rx), fmt_bytes(tx), caption)


class StatTile(Gtk.Box):
    """A big single value with a caption, e.g. "Download 94.2 Mbps"."""

    def __init__(self, title: str, icon: str, unit: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("metric-card")
        self.unit = unit
        header = Gtk.Box(spacing=8)
        header.append(Gtk.Image.new_from_icon_name(icon))
        header.append(label(title, "h2", "muted", wrap=False))
        self.append(header)
        self.value = label("—", "stat", wrap=False)
        self.append(self.value)

    def set_value(self, value: float | None) -> None:
        self.value.set_text("—" if value is None else f"{value:.1f} {self.unit}")
