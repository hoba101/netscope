# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta

from . import APP_ID, __version__
from .backends.collector import collect_snapshot, list_interfaces
from .i18n import init as init_i18n, is_rtl, t
from .settings import Settings
from .utils import fmt_bytes, fmt_clock, fmt_datetime, is_linux, is_windows, month_name, weekday_name

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # type: ignore
    import cairo  # type: ignore
    GTK_AVAILABLE = True
except Exception:  # pragma: no cover
    GTK_AVAILABLE = False
    Adw = Gdk = Gio = GLib = Gtk = Pango = PangoCairo = cairo = None  # type: ignore


def _dkey(v):
    if isinstance(v, datetime): return v.date()
    return v

def _hkey(v):
    if isinstance(v, datetime): return (v.year, v.month, v.day, v.hour)
    return None

class P:
    __slots__ = ("rx","tx","start","label","detail")
    def __init__(self, rx, tx, start, label, detail=""):
        self.rx=int(rx); self.tx=int(tx); self.start=start; self.label=label; self.detail=detail or label
    @property
    def total(self): return self.rx+self.tx

def hour_points(snap, count):
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    by = { _hkey(p.start): p for p in snap.hour if _hkey(p.start) }
    out=[]
    for off in range(count-1,-1,-1):
        dt = now - timedelta(hours=off); src = by.get((dt.year,dt.month,dt.day,dt.hour))
        out.append(P(src.rx if src else 0, src.tx if src else 0, dt, fmt_clock(dt.hour), f"{weekday_name(dt)} {dt:%Y-%m-%d %H:00}"))
    return out

def day_points(snap, count):
    today = date.today(); by = { _dkey(p.start): p for p in snap.day if _dkey(p.start) }
    out=[]
    for off in range(count-1,-1,-1):
        d = today - timedelta(days=off); src = by.get(d)
        out.append(P(src.rx if src else 0, src.tx if src else 0, d, str(d.day), f"{weekday_name(d)} {d.isoformat()}"))
    return out

def month_points(snap, count):
    today=date.today(); by={}
    for p in snap.month:
        d=_dkey(p.start)
        if isinstance(d,date): by[(d.year,d.month)]=p
    idx=today.year*12+(today.month-1); out=[]
    for off in range(count-1,-1,-1):
        y,m0=divmod(idx-off,12); m=m0+1; src=by.get((y,m)); d=date(y,m,1)
        out.append(P(src.rx if src else 0, src.tx if src else 0, d, month_name(m,True), f"{month_name(m)} {y}"))
    return out

CSS = r"""
window { font-family: "Vazirmatn","Noto Sans Arabic","Cantarell",sans-serif; }
.hero { padding: 18px 20px; border-radius: 20px; background: alpha(@accent_bg_color, 0.10); }
.cardx { padding: 16px 18px; border-radius: 18px; background: alpha(@card_bg_color, 0.92); }
.metric-card { padding: 14px 16px; border-radius: 16px; background: alpha(@card_bg_color, 0.92); }
.big { font-size: 30px; font-weight: 800; }
.h1 { font-size: 20px; font-weight: 800; }
.h2 { font-size: 14px; font-weight: 700; }
.muted { opacity: 0.66; }
.small { font-size: 11.5px; }
.dl { color: @accent_color; font-weight: 700; }
.ul { color: @warning_color; font-weight: 700; }
.good { color: @success_color; }
.warn { color: @warning_color; }
.bad { color: @error_color; }
.pill { border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 700; background: alpha(@window_fg_color,0.08); }
"""

def pill(text, cls=""):
    l = Gtk.Label(label=text); l.add_css_class("pill");
    if cls: l.add_css_class(cls)
    return l

def card_box(title=None, subtitle=None):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); b.add_css_class("cardx")
    if title:
        tlabel = Gtk.Label(label=title, xalign=0, wrap=True); tlabel.add_css_class("h2"); b.append(tlabel)
    if subtitle:
        sl = Gtk.Label(label=subtitle, xalign=0, wrap=True); sl.add_css_class("muted"); sl.add_css_class("small"); b.append(sl)
    return b

class Chart(Gtk.DrawingArea):
    def __init__(self, height=200):
        super().__init__(); self.set_content_height(height); self.set_hexpand(True); self.points=[]; self.hover=-1; self.on_hover=None
        self.ml=68; self.mr=12; self.mt=12; self.mb=32; self.step=4
        self.set_draw_func(self._draw)
        m=Gtk.EventControllerMotion(); m.connect("motion",self._motion); m.connect("leave",self._leave); self.add_controller(m)
    def set_data(self, points, step=4): self.points=list(points); self.step=max(1,step); self.hover=-1; self.queue_draw()
    def _rect(self): w=max(1,self.get_width()); h=max(1,self.get_height()); return self.ml,self.mt,max(1,w-self.ml-self.mr),max(1,h-self.mt-self.mb)
    def _idx(self,x): l,t,pw,ph=self._rect(); return -1 if not self.points or x<l or x>l+pw else max(0,min(int((x-l)/(pw/len(self.points))),len(self.points)-1))
    def _motion(self,_c,x,y):
        i=self._idx(x)
        if i!=self.hover:
            self.hover=i; self.queue_draw()
        if self.on_hover: self.on_hover(self.points[i] if i>=0 else None)
    def _leave(self,_c):
        self.hover=-1; self.queue_draw()
        if self.on_hover: self.on_hover(None)
    @staticmethod
    def _nice(v):
        if v<=0: return 1.0
        t=v*1.1; e=math.floor(math.log10(t)); b=10**e; f=t/b
        for n in (1,1.2,1.5,2,2.5,3,4,5,6,8,10):
            if f<=n: return n*b
        return 10*b
    def _draw(self,_a,cr,w,h,_d=None):
        l,t,pw,ph=self._rect(); base=t+ph; dark=Adw.StyleManager.get_default().get_dark(); fg=(1,1,1) if dark else (0,0,0)
        if not self.points or max(p.total for p in self.points)<=0:
            cr.set_source_rgba(*fg,0.45); cr.set_font_size(12); txt=t("chart.empty"); ext=cr.text_extents(txt); cr.move_to(w/2-ext.width/2,h/2); cr.show_text(txt); return
        mx=self._nice(max(p.total for p in self.points)); slot=pw/len(self.points)
        for i in range(5):
            val=mx*i/4; y=base-ph*i/4; cr.set_source_rgba(*fg,0.08); cr.move_to(l,y); cr.line_to(l+pw,y); cr.stroke()
            lab="0" if i==0 else fmt_bytes(val); cr.set_source_rgba(*fg,0.5); cr.set_font_size(9); ext=cr.text_extents(lab); cr.move_to(l-6-ext.width,y+3); cr.show_text(lab)
        for i,p in enumerate(self.points):
            if p.total<=0: continue
            bh=max(2,ph*p.total/mx); bw=min(slot*0.62,42); x=l+i*slot+(slot-bw)/2; y=base-bh; rxh=bh*p.rx/p.total if p.total else 0
            cr.set_source_rgba(0.29,0.56,0.89,1.0); cr.rectangle(x,base-rxh,bw,rxh); cr.fill()
            cr.set_source_rgba(0.90,0.55,0.20,1.0); cr.rectangle(x,y,bw,bh-rxh); cr.fill()
            if i==self.hover: cr.set_source_rgba(*fg,0.45); cr.rectangle(x,y,bw,bh); cr.stroke()
        off=(len(self.points)-1)%self.step
        for i,p in enumerate(self.points):
            if (i-off)%self.step: continue
            cx=l+i*slot+slot/2; cr.set_source_rgba(*fg,0.5); cr.set_font_size(9); ext=cr.text_extents(p.label); cr.move_to(cx-ext.width/2,base+16); cr.show_text(p.label)

class MetricCard(Gtk.Box):
    def __init__(self, title, icon):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6); self.add_css_class("metric-card")
        h=Gtk.Box(spacing=8); img=Gtk.Image.new_from_icon_name(icon); img.add_css_class("muted"); self.t=Gtk.Label(label=title,xalign=0,hexpand=True); self.t.add_css_class("h2"); self.t.add_css_class("muted"); h.append(img); h.append(self.t); self.append(h)
        self.v=Gtk.Label(label="—",xalign=0); self.v.add_css_class("big"); self.append(self.v)
        r=Gtk.Box(spacing=10); self.d=Gtk.Label(xalign=0); self.d.add_css_class("dl"); self.u=Gtk.Label(xalign=0); self.u.add_css_class("ul"); r.append(self.d); r.append(self.u); self.append(r)
        self.s=Gtk.Label(xalign=0,wrap=True); self.s.add_css_class("muted"); self.s.add_css_class("small"); self.append(self.s)
    def set(self, rx,tx,sub=""):
        self.v.set_text(fmt_bytes(rx+tx)); self.d.set_text(f"↓ {fmt_bytes(rx)}"); self.u.set_text(f"↑ {fmt_bytes(tx)}"); self.s.set_text(sub)

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, settings):
        super().__init__(application=app, title=t("app.name"))
        self.settings=settings; self.snap=None; self.diag=None
        self.set_default_size(1220, 860)
        self.set_direction(Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR)
        self._css()
        self.toast = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(sidebar_width_fraction=0.22, min_sidebar_width=220, max_sidebar_width=280)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._build_sidebar(); self._build_content()
        self.toast.set_child(self.split); self.set_content(self.toast)
        self.refresh(); self.refresh_diag()
        GLib.timeout_add_seconds(max(15, settings.refresh_seconds), self._auto)
        GLib.timeout_add_seconds(1, self._live)

    def _css(self):
        p=Gtk.CssProvider(); p.load_from_data(CSS.encode());
        d=Gdk.Display.get_default()
        if d: Gtk.StyleContext.add_provider_for_display(d,p,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _nav_row(self, icon, title, subtitle, name):
        row=Adw.ActionRow(title=title, subtitle=subtitle, activatable=True)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda *_: self.stack.set_visible_child_name(name))
        return row

    def _build_sidebar(self):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header=Adw.HeaderBar(); header.set_title_widget(Adw.WindowTitle(title=t("app.name"), subtitle="v"+__version__))
        refresh=Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=t("action.refresh")); refresh.connect("clicked",lambda *_: (self.refresh(),self.refresh_diag())); header.pack_start(refresh)
        box.append(header)
        hero=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); hero.add_css_class("hero"); hero.set_margin_start(12); hero.set_margin_end(12); hero.set_margin_top(12); hero.set_margin_bottom(8)
        self.hero_title=Gtk.Label(label=t("overview.subtitle"), xalign=0, wrap=True); self.hero_title.add_css_class("h2"); hero.append(self.hero_title)
        self.hero_sub=Gtk.Label(label="", xalign=0, wrap=True); self.hero_sub.add_css_class("muted"); self.hero_sub.add_css_class("small"); hero.append(self.hero_sub)
        box.append(hero)
        group=Adw.PreferencesGroup(); group.set_margin_start(12); group.set_margin_end(12)
        for icon,title,sub,name in [
            ("view-grid-symbolic",t("page.overview"),t("overview.subtitle"),"overview"),
            ("document-open-recent-symbolic",t("page.history"),t("history.subtitle"),"history"),
            ("security-high-symbolic",t("page.controls"),t("controls.subtitle"),"controls"),
            ("speedometer-symbolic",t("page.speedtest", default="Speed test"),t("speedtest.subtitle", default="Measure link, latency, and internet speed"),"speedtest"),
            ("preferences-system-notifications-symbolic",t("page.alerts"),t("alerts.subtitle"),"alerts"),
            ("dialog-information-symbolic",t("page.diagnostics"),t("diagnostics.subtitle"),"diagnostics"),
        ]: group.add(self._nav_row(icon,title,sub,name))
        settings_row=Adw.ActionRow(title=t("page.settings"), subtitle=t("settings.title"), activatable=True)
        settings_row.add_prefix(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
        settings_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        settings_row.connect("activated", self._open_settings)
        group.add(settings_row)
        box.append(group)
        self.split.set_sidebar(Adw.NavigationPage.new(box, t("app.name")))

    def _build_content(self):
        content=Adw.NavigationPage.new(self.stack, t("page.overview"))
        self.split.set_content(content)
        self.stack.add_named(self._wrap_page(self._page_overview(), t("page.overview")), "overview")
        self.stack.add_named(self._wrap_page(self._page_history(), t("page.history")), "history")
        self.stack.add_named(self._wrap_page(self._page_controls(), t("page.controls")), "controls")
        self.stack.add_named(self._wrap_page(self._page_speedtest(), t("page.speedtest", default="Speed test")), "speedtest")
        self.stack.add_named(self._wrap_page(self._page_alerts(), t("page.alerts")), "alerts")
        self.stack.add_named(self._wrap_page(self._page_diagnostics(), t("page.diagnostics")), "diagnostics")
        self.stack.set_visible_child_name("overview")


    def _wrap_page(self, child, title):
        tv=Adw.ToolbarView(); hb=Adw.HeaderBar(); hb.set_title_widget(Adw.WindowTitle(title=title))
        tv.add_top_bar(hb); tv.set_content(child); return tv

    def _page_scroller(self):
        s=Gtk.ScrolledWindow(vexpand=True); c=Adw.Clamp(maximum_size=1100,tightening_threshold=760); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=24, margin_start=20, margin_end=20); c.set_child(box); s.set_child(c); return s,box

    def _page_overview(self):
        s,box=self._page_scroller(); self.banner=Adw.Banner(revealed=False); box.append(self.banner)
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=4, min_children_per_line=1, column_spacing=12, row_spacing=12)
        self.m_month=MetricCard(t("summary.month"),"x-office-calendar-symbolic"); self.m_today=MetricCard(t("summary.today"),"weather-clear-symbolic")
        self.m_hour=MetricCard(t("summary.hour"),"preferences-system-time-symbolic"); self.m_live=MetricCard(t("summary.live"),"network-transmit-receive-symbolic")
        for w in (self.m_month,self.m_today,self.m_hour,self.m_live): flow.append(w)
        box.append(flow)
        q=card_box(t("quota.status")); self.q_label=Gtk.Label(xalign=0,wrap=True); self.q_label.add_css_class("small"); q.append(self.q_label)
        self.q_bar=Gtk.ProgressBar(show_text=True); q.append(self.q_bar); box.append(q)
        ch=card_box(t("chart.hours", count=self.settings.chart_hours), t("chart.hint")); self.ov_detail=Gtk.Label(xalign=0,wrap=True); self.ov_detail.add_css_class("muted"); self.ov_detail.add_css_class("small"); ch.append(self.ov_detail)
        self.ov_chart=Chart(210); self.ov_chart.on_hover=lambda p: self.ov_detail.set_text(f"{p.detail} — ↓{fmt_bytes(p.rx)} ↑{fmt_bytes(p.tx)}" if p else t("chart.hint")); ch.append(self.ov_chart); box.append(ch)
        grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=2, min_children_per_line=1, column_spacing=12, row_spacing=12)
        self.day_card=card_box(t("chart.days", count=self.settings.chart_days)); self.day_chart=Chart(180); self.day_card.append(self.day_chart)
        self.month_card=card_box(t("chart.months", count=self.settings.chart_months)); self.month_chart=Chart(180); self.month_card.append(self.month_chart)
        grid.append(self.day_card); grid.append(self.month_card); box.append(grid)
        self.ov_footer=Gtk.Label(xalign=0,wrap=True); self.ov_footer.add_css_class("muted"); self.ov_footer.add_css_class("small"); box.append(self.ov_footer)
        return s

    def _page_history(self):
        s,box=self._page_scroller()
        ctrl=card_box(t("page.history"), t("history.subtitle"))
        row=Gtk.Box(spacing=8)
        self.hist_period=Gtk.DropDown.new_from_strings([t("history.fiveminute"),t("history.hourly"),t("history.daily"),t("history.monthly"),t("history.yearly"),t("history.top")])
        self.hist_period.set_selected(2); self.hist_period.connect("notify::selected", lambda *_: self._render_history())
        row.append(Gtk.Label(label=t("history.period"))); row.append(self.hist_period); ctrl.append(row); box.append(ctrl)
        vis=card_box(); self.hist_detail=Gtk.Label(xalign=0,wrap=True); self.hist_detail.add_css_class("muted"); self.hist_detail.add_css_class("small"); vis.append(self.hist_detail)
        self.hist_chart=Chart(260); self.hist_chart.on_hover=lambda p: self.hist_detail.set_text(f"{p.detail} — {fmt_bytes(p.total)} (↓{fmt_bytes(p.rx)} ↑{fmt_bytes(p.tx)})" if p else t("chart.hint")); vis.append(self.hist_chart)
        self.hist_list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); self.hist_list.add_css_class("boxed-list"); vis.append(self.hist_list)
        box.append(vis); return s

    def _page_controls(self):
        s,box=self._page_scroller(); box.append(card_box(t("page.controls"), t("controls.subtitle")))
        # quota settings in GUI
        qg=Adw.PreferencesGroup(title=t("settings.quota")); qbox=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); qbox.add_css_class("boxed-list")
        self.q_enable=Adw.SwitchRow(title=t("settings.quota_enabled")); self.q_enable.set_active(self.settings.quota_enabled)
        self.q_mb=Adw.SpinRow.new_with_range(1,10_000_000,100); self.q_mb.set_title(t("settings.quota_daily_mb")); self.q_mb.set_value(self.settings.quota_daily_mb)
        self.q_warn=Adw.SpinRow.new_with_range(1,100,1); self.q_warn.set_title(t("settings.quota_warn_percent")); self.q_warn.set_value(self.settings.quota_warn_percent)
        self.q_action=Adw.ComboRow(title=t("settings.quota_action"), model=Gtk.StringList.new([t("settings.quota_action.warn"),t("settings.quota_action.disconnect"),t("settings.quota_action.disable_interface"),t("settings.quota_action.throttle")]))
        self.q_action.set_selected({"warn":0,"disconnect":1,"disable_interface":2,"throttle":3}.get(self.settings.quota_action,0))
        self.q_kbit=Adw.SpinRow.new_with_range(16,10_000_000,64); self.q_kbit.set_title(t("settings.quota_throttle_kbit")); self.q_kbit.set_value(self.settings.quota_throttle_kbit)
        for w in (self.q_enable,self.q_mb,self.q_warn,self.q_action,self.q_kbit): qbox.append(w)
        save_row=Adw.ActionRow(title=t("action.save"), subtitle=t("settings.saved")); save_btn=Gtk.Button(label=t("action.save"), valign=Gtk.Align.CENTER); save_btn.add_css_class("suggested-action"); save_btn.connect("clicked", self._save_controls); save_row.add_suffix(save_btn); save_row.set_activatable_widget(save_btn); qbox.append(save_row)
        qwrap=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); qwrap.append(qbox); box.append(qwrap)

        cg=card_box(t("controls.current"), t("controls.safe")); self.ctrl_caps=Gtk.Label(xalign=0,wrap=True); self.ctrl_caps.add_css_class("muted"); self.ctrl_caps.add_css_class("small"); cg.append(self.ctrl_caps)
        tg=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.throttle_row=Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        tl=Gtk.Label(label=t("controls.throttle")+" (kbit/s)", xalign=0, hexpand=True)
        tk=Gtk.SpinButton.new_with_range(16,10_000_000,64); tk.set_value(self.settings.quota_throttle_kbit)
        tb=Gtk.Button(label=t("action.apply"), valign=Gtk.Align.CENTER); tb.add_css_class("suggested-action"); tb.connect("clicked", lambda *_: self._confirm("throttle", lambda: int(tk.get_value())))
        self.throttle_row.append(tl); self.throttle_row.append(tk); self.throttle_row.append(tb); cg.append(self.throttle_row)
        cg.append(Gtk.Label(label=t("controls.throttle_hint"), xalign=0,wrap=True, css_classes=["muted","small"]))
        actions=Gtk.Box(spacing=8)
        for label, act, style in [(t("action.restore"),"restore",""),(t("action.connect"),"connect",""),(t("action.disconnect"),"disconnect","destructive-action")]:
            b=Gtk.Button(label=label); 
            if style: b.add_css_class(style)
            b.connect("clicked", lambda _b,a=act: self._confirm(a)); actions.append(b)
        cg.append(actions)
        cg.append(Gtk.Label(label=t("controls.disconnect_hint"), xalign=0,wrap=True, css_classes=["muted","small"]))
        box.append(cg); return s


    def _page_speedtest(self):
        s,box=self._page_scroller(); box.append(card_box(t("page.speedtest", default="Speed test"), t("speedtest.subtitle", default="Check link speed, latency, and optional internet download speed.")))
        info=card_box(t("label.status")); self.st_info=Gtk.Label(xalign=0,wrap=True,selectable=True); self.st_info.add_css_class("small"); info.append(self.st_info)
        row=Gtk.Box(spacing=8)
        self.st_btn_basic=Gtk.Button(label=t("speedtest.run_basic")); self.st_btn_basic.connect("clicked", self._run_speed_basic)
        self.st_btn_download=Gtk.Button(label=t("speedtest.run_download")); self.st_btn_download.add_css_class("suggested-action"); self.st_btn_download.connect("clicked", self._run_speed_download)
        row.append(self.st_btn_basic); row.append(self.st_btn_download); info.append(row)
        info.append(Gtk.Label(label=t("speedtest.notice", default="Download test uses internet data (about 25 MB by default) and measures real throughput to a public test endpoint."), xalign=0, wrap=True, css_classes=["muted","small"]))
        box.append(info)
        res=card_box(t("speedtest.results", default="Results")); self.st_results=Gtk.Label(xalign=0,wrap=True,selectable=True); self.st_results.add_css_class("small"); res.append(self.st_results)
        self.st_progress=Gtk.ProgressBar(show_text=True); res.append(self.st_progress); box.append(res)
        self._update_speed_info(); return s

    def _update_speed_info(self):
        iface=self._iface() or '?'; lines=[f"{t('status.interface')}: {iface}"]
        try:
            import pathlib
            base=pathlib.Path(f"/sys/class/net/{iface}")
            if base.exists():
                lines.append(f"operstate: {(base/'operstate').read_text().strip()}")
                try: lines.append(f"link: {(base/'speed').read_text().strip()} Mbps")
                except Exception: pass
        except Exception: pass
        self.st_info.set_text('\n'.join(lines))

    def _run_speed_basic(self, *_):
        if getattr(self,'_speed_running',False): return
        import threading, subprocess
        self._speed_running=True
        try: self.st_btn_basic.set_sensitive(False); self.st_btn_download.set_sensitive(False)
        except Exception: pass
        iface=self._iface(); self.st_results.set_text(t("toast.action_started")); self.st_progress.set_fraction(0)
        def work():
            out=[]
            targets=[("gateway","1.1.1.1"),("dns","8.8.8.8")]
            try:
                r=subprocess.run(["ip","route","show","default"], capture_output=True, text=True, timeout=3)
                for part in r.stdout.split():
                    if part.count('.')==3 and part[0].isdigit(): targets.insert(0,("gateway",part)); break
            except Exception: pass
            for i,(name,host) in enumerate(targets):
                try:
                    r=subprocess.run(["ping","-c","3","-W","1",host], capture_output=True, text=True, timeout=8)
                    # parse avg
                    for line in r.stdout.splitlines():
                        if 'rtt' in line or 'round-trip' in line:
                            out.append(f"{name} ({host}): {line.split('=')[-1].strip()}"); break
                    else: out.append(f"{name} ({host}): done")
                except Exception as e: out.append(f"{name} ({host}): {e}")
                GLib.idle_add(self.st_progress.set_fraction, (i+1)/max(1,len(targets)))
            try:
                from .accuracy import collect
                ar=collect(iface); out.append(f"accuracy confidence: {ar.confidence}")
            except Exception: pass
            GLib.idle_add(self.st_results.set_text, '\n'.join(out))
            def done():
                self._speed_running=False
                try: self.st_btn_basic.set_sensitive(True); self.st_btn_download.set_sensitive(True)
                except Exception: pass
                self.st_progress.set_text(t("speedtest.results"))
            GLib.idle_add(done)
        threading.Thread(target=work, daemon=True).start()

    def _run_speed_download(self, *_):
        if getattr(self,'_speed_running',False): return
        import threading, time, urllib.request
        self._speed_running=True
        try: self.st_btn_basic.set_sensitive(False); self.st_btn_download.set_sensitive(False)
        except Exception: pass
        self.st_results.set_text(t("toast.action_started")); self.st_progress.set_fraction(0)
        url="https://speed.cloudflare.com/__down?bytes=25000000"
        def work():
            try:
                t0=time.time(); req=urllib.request.Request(url, headers={'User-Agent':'NetScope/1.0'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    total=0; chunk=65536
                    while True:
                        b=r.read(chunk)
                        if not b: break
                        total+=len(b)
                        dt=max(0.001,time.time()-t0); mbps=(total*8)/(dt*1_000_000)
                        GLib.idle_add(self.st_progress.set_fraction, min(1.0,total/25_000_000))
                        GLib.idle_add(self.st_progress.set_text, f"{fmt_bytes(total)} — {mbps:.1f} Mbps")
                dt=max(0.001,time.time()-t0); mbps=(total*8)/(dt*1_000_000); MBs=(total)/(dt*1_000_000)
                GLib.idle_add(self.st_results.set_text, f"Download: {fmt_bytes(total)} in {dt:.2f}s\nThroughput: {mbps:.2f} Mbps ({MBs:.2f} MB/s)")
                def done(): 
                    self._speed_running=False
                    try: self.st_btn_basic.set_sensitive(True); self.st_btn_download.set_sensitive(True)
                    except Exception: pass
                    self.st_progress.set_fraction(1.0)
                GLib.idle_add(done)
            except Exception as e:
                def done(err=e):
                    self._speed_running=False
                    try: self.st_btn_basic.set_sensitive(True); self.st_btn_download.set_sensitive(True)
                    except Exception: pass
                    self.st_results.set_text(f"Download test failed: {err}")
                GLib.idle_add(done)
        threading.Thread(target=work, daemon=True).start()


    def _page_alerts(self):
        s,box=self._page_scroller(); box.append(card_box(t("page.alerts"), t("alerts.subtitle")))
        st=card_box(t("alerts.settings"))
        form=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); form.add_css_class("boxed-list")
        def sw(title, attr): r=Adw.SwitchRow(title=title); r.set_active(bool(getattr(self.settings,attr))); form.append(r); return r
        def sp(title, attr, lo, hi, step): r=Adw.SpinRow.new_with_range(lo,hi,step); r.set_title(title); r.set_value(getattr(self.settings,attr)); form.append(r); return r
        self.a_enabled=sw(t("alerts.enabled"),"alerts_enabled"); self.a_notify=sw(t("alerts.notify"),"alert_desktop_notify")
        self.a_daily=sw(t("alerts.daily"),"alert_daily_enabled"); self.a_hourly=sw(t("alerts.hourly"),"alert_hourly_enabled")
        self.a_hourly_mb=sp(t("alerts.hourly_mb"),"alert_hourly_mb",1,10_000_000,100); self.a_hourly_warn=sp(t("alerts.hourly_warn"),"alert_hourly_warn_percent",1,100,1)
        self.a_low=sw(t("alerts.low_speed"),"alert_low_speed_enabled"); self.a_low_k=sp(t("alerts.low_speed_kbps"),"alert_low_speed_kbps",1,10_000_000,16); self.a_low_s=sp(t("alerts.low_speed_sec"),"alert_low_speed_seconds",3,3600,1)
        self.a_disc=sw(t("alerts.disconnect"),"alert_disconnect_enabled"); self.a_change=sw(t("alerts.network_change"),"alert_network_change_enabled")
        save=Adw.ActionRow(title=t("action.save")); sb=Gtk.Button(label=t("action.save"), valign=Gtk.Align.CENTER); sb.add_css_class("suggested-action"); sb.connect("clicked", self._save_alerts); save.add_suffix(sb); save.set_activatable_widget(sb); form.append(save)
        st.append(form); box.append(st)
        logc=card_box(t("alerts.log"))
        brow=Gtk.Box(spacing=8)
        for lbl,cb in [(t("alerts.mark_read"), self._alerts_read),(t("alerts.clear"), self._alerts_clear),(t("action.refresh"), self._render_alerts)]:
            b=Gtk.Button(label=lbl); b.connect("clicked", cb); brow.append(b)
        logc.append(brow)
        self.alerts_list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); self.alerts_list.add_css_class("boxed-list")
        logc.append(self.alerts_list); box.append(logc)
        self._render_alerts(); return s

    def _save_alerts(self, *_):
        s=self.settings
        s.alerts_enabled=self.a_enabled.get_active(); s.alert_desktop_notify=self.a_notify.get_active()
        s.alert_daily_enabled=self.a_daily.get_active(); s.alert_hourly_enabled=self.a_hourly.get_active()
        s.alert_hourly_mb=int(self.a_hourly_mb.get_value()); s.alert_hourly_warn_percent=int(self.a_hourly_warn.get_value())
        s.alert_low_speed_enabled=self.a_low.get_active(); s.alert_low_speed_kbps=int(self.a_low_k.get_value()); s.alert_low_speed_seconds=int(self.a_low_s.get_value())
        s.alert_disconnect_enabled=self.a_disc.get_active(); s.alert_network_change_enabled=self.a_change.get_active()
        s.save(); self.toast.add_toast(Adw.Toast(title=t("toast.saved")))

    def _render_alerts(self, *_):
        from . import storage
        if not hasattr(self,'alerts_list'): return
        while (ch:=self.alerts_list.get_first_child()): self.alerts_list.remove(ch)
        rows=storage.list_alerts(120)
        if not rows:
            self.alerts_list.append(Adw.ActionRow(title=t("alerts.empty"))); return
        sev_css={"info":"", "warning":"warn", "critical":"bad"}
        for r in rows:
            title=f"[{r.get('severity','')}] {r.get('title','')}"
            sub=f"{r.get('ts','')} • {r.get('interface','')} • {r.get('message','')}"
            row=Adw.ActionRow(title=title, subtitle=sub)
            sev=r.get('severity','info'); 
            if sev in ('warning','critical'): row.add_prefix(Gtk.Image.new_from_icon_name('dialog-warning-symbolic' if sev=='warning' else 'dialog-error-symbolic'))
            if not r.get('seen'): row.add_suffix(pill(t('alerts.fired'), 'warn' if sev!='critical' else 'bad'))
            self.alerts_list.append(row)

    def _alerts_read(self, *_):
        from . import storage
        storage.mark_alerts_seen(); self._render_alerts()

    def _alerts_clear(self, *_):
        from . import storage
        storage.clear_alerts(); self._render_alerts()

    def _page_diagnostics(self):
        s,box=self._page_scroller(); top=card_box(t("page.diagnostics"), t("diagnostics.subtitle"))
        brow=Gtk.Box(spacing=8)
        rb=Gtk.Button(label=t("diag.refresh")); rb.connect("clicked", lambda *_: self.refresh_diag())
        cb=Gtk.Button(label=t("action.copy")); cb.connect("clicked", self._copy_diag)
        eb=Gtk.Button(label=t("action.export")); eb.add_css_class("suggested-action"); eb.connect("clicked", self._export_diag)
        for b in (rb,cb,eb): brow.append(b)
        top.append(brow); box.append(top)
        self.diag_acc=card_box(t("diag.accuracy")); box.append(self.diag_acc)
        self.diag_perm=card_box(t("diag.permissions")); box.append(self.diag_perm)
        self.diag_src=card_box(t("diag.sources")); box.append(self.diag_src)
        self.diag_install=card_box(t("diag.install"), t("diag.install_hint")); box.append(self.diag_install)
        return s

    def _open_settings(self, *_):
        dlg=Adw.PreferencesDialog(title=t("settings.title"))
        page=Adw.PreferencesPage(); dlg.add(page)
        g=Adw.PreferencesGroup(title=t("settings.appearance")); page.add(g)
        lang=Adw.ComboRow(title=t("settings.language"), model=Gtk.StringList.new([t("settings.language.system"),t("settings.language.en"),t("settings.language.ar")]))
        lang.set_selected({"system":0,"en":1,"ar":2}.get(self.settings.language,0)); g.add(lang)
        theme=Adw.ComboRow(title=t("settings.theme"), model=Gtk.StringList.new([t("settings.theme.system"),t("settings.theme.light"),t("settings.theme.dark")]))
        theme.set_selected({"system":0,"light":1,"dark":2}.get(self.settings.theme,0)); g.add(theme)
        d=Adw.PreferencesGroup(title=t("settings.data")); page.add(d)
        ref=Adw.SpinRow.new_with_range(15,3600,15); ref.set_title(t("settings.refresh")); ref.set_value(self.settings.refresh_seconds); d.add(ref)
        live=Adw.SwitchRow(title=t("settings.live_speed")); live.set_active(self.settings.live_speed); d.add(live)
        def on_close(*_):
            old_lang=self.settings.language
            self.settings.language=["system","en","ar"][lang.get_selected()]
            self.settings.theme=["system","light","dark"][theme.get_selected()]
            self.settings.refresh_seconds=int(ref.get_value()); self.settings.live_speed=live.get_active(); self.settings.save()
            style=Adw.StyleManager.get_default()
            if self.settings.theme=="light": style.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            elif self.settings.theme=="dark": style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            else: style.set_color_scheme(Adw.ColorScheme.DEFAULT)
            init_i18n(self.settings.language)
            self.set_direction(Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR)
            if old_lang != self.settings.language:
                # full reload for translated UI
                app=self.get_application(); self.close()
                GLib.idle_add(lambda: (MainWindow(app, Settings.load()).present(), False)[1])
                return
            self.toast.add_toast(Adw.Toast(title=t("toast.saved")))
        dlg.connect("closed", on_close); dlg.present(self)

    def _auto(self): self.refresh(); return True

    def _iface(self): return (self.snap.interface.name if self.snap else None) or self.settings.selected_interface or ""

    def refresh(self):
        self.snap = collect_snapshot(settings=self.settings)
        if not self.snap:
            self.banner.set_title(t("toast.no_data")); self.banner.set_revealed(True); return
        self.hero_sub.set_text(f"{self.snap.interface.name} • {', '.join(self.snap.sources[:2])}")
        today=date.today(); now=datetime.now()
        month=next((p for p in reversed(self.snap.day) if _dkey(p.start) and _dkey(p.start).year==today.year and _dkey(p.start).month==today.month), None)
        # month from month data better
        m=next((p for p in reversed(self.snap.month) if _dkey(p.start) and _dkey(p.start).year==today.year and _dkey(p.start).month==today.month), None)
        day=next((p for p in reversed(self.snap.day) if _dkey(p.start)==today), None)
        hour=next((p for p in reversed(self.snap.hour) if _hkey(p.start)==(today.year,today.month,today.day,now.hour)), None)
        self.m_month.set(m.rx if m else 0, m.tx if m else 0, f"{month_name(today.month)} {today.year}")
        self.m_today.set(day.rx if day else 0, day.tx if day else 0, today.isoformat())
        self.m_hour.set(hour.rx if hour else 0, hour.tx if hour else 0, f"{fmt_clock(now.hour)}–{fmt_clock((now.hour+1)%24)}")
        rxr = fmt_bytes(self.snap.live_rx_bps/8)+"/s" if self.settings.rate_unit=='bytes' else fmt_bytes(self.snap.live_rx_bps, rate=True)
        txr = fmt_bytes(self.snap.live_tx_bps/8)+"/s" if self.settings.rate_unit=='bytes' else fmt_bytes(self.snap.live_tx_bps, rate=True)
        total_rate = (self.snap.live_rx_bps + self.snap.live_tx_bps)
        self.m_live.v.set_text(fmt_bytes(total_rate/8)+"/s" if self.settings.rate_unit=='bytes' else fmt_bytes(total_rate, rate=True))
        self.m_live.d.set_text(f"↓ {rxr}"); self.m_live.u.set_text(f"↑ {txr}"); self.m_live.s.set_text(self.snap.interface.name)
        self.ov_chart.set_data(hour_points(self.snap,self.settings.chart_hours),4)
        self.day_chart.set_data(day_points(self.snap,self.settings.chart_days),5)
        self.month_chart.set_data(month_points(self.snap,self.settings.chart_months),2)
        self._render_quota(); self._render_history()
        self._check_alerts()
        created = fmt_datetime(self.snap.interface.created) if self.snap.interface.created else t("label.unknown")
        self.ov_footer.set_text(f"{t('status.sources')}: {', '.join(self.snap.sources)}  •  {t('status.recording_since')}: {created}  •  {t('status.updated')}: {datetime.now():%H:%M:%S}")


    def _check_alerts(self):
        try:
            from . import alerts
            fired = alerts.evaluate(self.snap, self.settings, self.snap.live_rx_bps, self.snap.live_tx_bps, do_notify=True)
            if fired:
                self.toast.add_toast(Adw.Toast(title=f"{t('alerts.fired')}: {fired[-1]['title']}"))
                self._render_alerts()
        except Exception:
            pass

    def _render_quota(self):
        try:
            from .quota import evaluate
            q=evaluate(self.snap,self.settings)
            if not self.settings.quota_enabled:
                self.q_label.set_text(t("quota.not_enabled")+" — "+t("quota.enable_hint")); self.q_bar.set_fraction(0); self.q_bar.set_text(""); self.banner.set_revealed(False); return
            frac=min(1.0,max(0.0,q.used_bytes/max(1,q.limit_bytes))); self.q_bar.set_fraction(frac)
            self.q_bar.set_text(f"{q.percent:.1f}%  •  {fmt_bytes(q.used_bytes)} / {fmt_bytes(q.limit_bytes)}")
            rem=max(0,q.limit_bytes-q.used_bytes)
            self.q_label.set_text(f"{t('quota.used')}: {fmt_bytes(q.used_bytes)}  •  {t('quota.remaining')}: {fmt_bytes(rem)}  •  {t('settings.quota_action')}: {self.settings.quota_action}")
            if q.exceeded: self.banner.set_title(t("banner.quota_exceeded")); self.banner.set_revealed(True)
            elif q.warn: self.banner.set_title(t("banner.quota_warn")); self.banner.set_revealed(True)
            else: self.banner.set_title(t("banner.quota_ok")); self.banner.set_revealed(False)
        except Exception as e:
            self.q_label.set_text(str(e))

    def _render_history(self):
        if not self.snap: return
        sel=self.hist_period.get_selected()
        if sel==0: pts=[P(p.rx,p.tx,p.start, getattr(p,'label',str(p.start)), getattr(p,'detail',str(p.start))) for p in self.snap.fiveminute[-96:]]; step=8
        elif sel==1: pts=hour_points(self.snap,max(24,self.settings.chart_hours)); step=4
        elif sel==2: pts=day_points(self.snap,max(30,self.settings.chart_days)); step=5
        elif sel==3: pts=month_points(self.snap,max(12,self.settings.chart_months)); step=2
        elif sel==4: pts=[P(p.rx,p.tx,p.start, getattr(p,'label',str(p.start)), getattr(p,'detail',str(p.start))) for p in self.snap.year]; step=1
        else: pts=[P(p.rx,p.tx,p.start, getattr(p,'label',str(p.start)), getattr(p,'detail',str(p.start))) for p in sorted(self.snap.top, key=lambda x:x.total, reverse=True)[:15]]; step=1
        self.hist_chart.set_data(pts,step); self.hist_detail.set_text(t("chart.hint"))
        while (ch:=self.hist_list.get_first_child()): self.hist_list.remove(ch)
        show = sorted(pts,key=lambda p:p.total,reverse=True)[:20] if sel==5 else list(reversed([p for p in pts if p.total>0]))[:20]
        for p in (show or pts[-10:]):
            row=Adw.ActionRow(title=p.detail or p.label, subtitle=f"↓ {fmt_bytes(p.rx)}   ↑ {fmt_bytes(p.tx)}")
            row.add_suffix(Gtk.Label(label=fmt_bytes(p.total), css_classes=["muted"])); self.hist_list.append(row)

    def _live(self):
        if self.settings.live_speed and self.snap:
            try:
                if is_linux():
                    from .backends.linux_sysfs import read_live_rates
                    r=read_live_rates(self.snap.interface.name)
                elif is_windows():
                    from .backends.windows import read_live_rates
                    r=read_live_rates(self.snap.interface.name)
                else: r=None
                if r:
                    self.snap.live_rx_bps,self.snap.live_tx_bps=r
                    rxr = fmt_bytes(r[0]/8)+"/s" if self.settings.rate_unit=='bytes' else fmt_bytes(r[0], rate=True)
                    txr = fmt_bytes(r[1]/8)+"/s" if self.settings.rate_unit=='bytes' else fmt_bytes(r[1], rate=True)
                    self.m_live.d.set_text(f"↓ {rxr}"); self.m_live.u.set_text(f"↑ {txr}")
            except Exception: pass
        return True

    def _save_controls(self, *_):
        s=self.settings; s.quota_enabled=self.q_enable.get_active(); s.quota_daily_mb=int(self.q_mb.get_value()); s.quota_warn_percent=int(self.q_warn.get_value())
        s.quota_action=["warn","disconnect","disable_interface","throttle"][self.q_action.get_selected()]; s.quota_throttle_kbit=int(self.q_kbit.get_value()); s.save()
        self.toast.add_toast(Adw.Toast(title=t("toast.saved"))); self._render_quota()

    def _confirm(self, action, extra=None):
        iface=self._iface() or "?"
        if action=="throttle":
            kbit=extra() if callable(extra) else self.settings.quota_throttle_kbit
            title=t("confirm.throttle.title"); body=t("confirm.throttle.body", kbit=kbit, iface=iface); cb=lambda: self._do_control("throttle", kbit=kbit)
        elif action=="restore": title=t("confirm.restore.title"); body=t("confirm.restore.body", iface=iface); cb=lambda: self._do_control("restore")
        elif action=="disconnect": title=t("confirm.disconnect.title"); body=t("confirm.disconnect.body", iface=iface); cb=lambda: self._do_control("disconnect")
        elif action=="connect": title=t("action.connect"); body=iface; cb=lambda: self._do_control("connect")
        else: return
        dlg=Adw.AlertDialog(heading=title, body=body)
        dlg.add_response("cancel", t("action.cancel")); dlg.add_response("ok", t("action.confirm"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE if action=="disconnect" else Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("cancel"); dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d,resp: cb() if resp=="ok" else None)
        dlg.present(self)

    def _do_control(self, action, kbit=None):
        from . import controls
        iface=self._iface()
        if action=="throttle": res=controls.throttle_linux(iface, kbit or self.settings.quota_throttle_kbit)
        elif action=="restore": res=controls.restore_linux(iface)
        elif action=="disconnect": res=controls.disconnect_linux(iface)
        elif action=="connect": res=controls.connect_linux(iface)
        else: return
        if not res.ok and res.needs_privilege and is_linux():
            import shutil, subprocess
            exe=shutil.which('netscope') or sys.executable
            cmd=['pkexec', exe, '--cli', 'control', action] + (['--iface',iface] if iface else []) + (['--kbit',str(kbit)] if action=='throttle' else [])
            try: subprocess.Popen(cmd); self.toast.add_toast(Adw.Toast(title=t("toast.action_started")+" — "+t("label.needs_permission"))); return
            except Exception: pass
        self.toast.add_toast(Adw.Toast(title=(res.message or action)[:120])); self.refresh(); self.refresh_diag()

    def refresh_diag(self):
        try:
            from .permissions import scan
            from .accuracy import collect
            iface=self._iface() or "eno1"
            acc=collect(iface); perm=scan(); self.diag={"accuracy":acc.as_dict(),"permissions":perm.as_dict()}
            # accuracy card
            self._clear_box(self.diag_acc)
            conf = acc.confidence
            hint = t(f"accuracy.confidence.{conf}_hint", default=t("status.accuracy"))
            row=Gtk.Box(spacing=8); row.append(pill(t(f"accuracy.confidence.{conf}", default=conf), {"high":"good","medium":"warn","low":"bad"}.get(conf,""))); row.append(Gtk.Label(label=hint, xalign=0, wrap=True, hexpand=True, css_classes=["muted","small"]))
            self.diag_acc.append(row)
            for p in acc.probes[:8]:
                val = f"↓{fmt_bytes(p.rx_bytes)} ↑{fmt_bytes(p.tx_bytes)}" if p.rx_bytes is not None else (p.error[:80] if p.error else "—")
                row=Gtk.Box(spacing=10); meta=(f"link={'up' if p.link_up else 'down'}" if p.link_up is not None else "") + (f" {p.speed_mbps}Mbps" if p.speed_mbps else "")
                left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True); left.append(Gtk.Label(label=p.source, xalign=0)); 
                if meta: left.append(Gtk.Label(label=meta.strip(), xalign=0, css_classes=["muted","small"]))
                row.append(left); row.append(Gtk.Label(label=val, wrap=True, max_width_chars=34, css_classes=["small","muted"])); self.diag_acc.append(row)
            # permissions
            self._clear_box(self.diag_perm)
            flags=[("vnStat",perm.has_vnstat),("vnStat DB read",perm.can_read_vnstat_db),("nmcli",perm.has_nmcli),("tc",perm.has_tc),("nft",perm.has_nft),("pkexec",perm.has_pkexec),("admin/root",perm.is_admin)]
            flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, homogeneous=True, column_spacing=8, row_spacing=8)
            for name, ok in flags:
                flow.append(pill(f"{name}: {t('label.available') if ok else t('label.unavailable')}", "good" if ok else "muted"))
            self.diag_perm.append(flow)
            for n in perm.notes: self.diag_perm.append(Gtk.Label(label="• "+n, xalign=0, wrap=True, css_classes=["muted","small"]))
            caps = f"tc={'yes' if perm.has_tc else 'no'} nmcli={'yes' if perm.has_nmcli else 'no'} pkexec={'yes' if perm.has_pkexec else 'no'}"
            if hasattr(self,'ctrl_caps'): self.ctrl_caps.set_text(f"{t('label.status')}: {caps}  •  {t('controls.throttle_hint')}")
            self._clear_box(self.diag_install)
            from .installer import install_command, service_enable_command
            if not perm.has_tc:
                b=Gtk.Button(label="Install iproute-tc ("+t("action.install")+")"); b.connect("clicked", lambda *_: self._run_installer(install_command(["iproute-tc"]))); self.diag_install.append(b)
            if perm.has_vnstat and not perm.has_vnstatd_service:
                b=Gtk.Button(label="Enable vnstat service ("+t("action.install")+")"); b.connect("clicked", lambda *_: self._run_installer(service_enable_command("vnstat"))); self.diag_install.append(b)
            has_actions = any(not isinstance(c,Gtk.Label) or "h2" not in (c.get_css_classes() or []) for c in [self.diag_install.get_first_child().get_next_sibling() if self.diag_install.get_first_child() else None] if c)
            if not has_actions:
                ok=Gtk.Label(label="✓ " + t("label.available"), xalign=0, css_classes=["good","small"]); self.diag_install.append(ok)
            # sources
            self._clear_box(self.diag_src)
            if self.snap:
                for src in self.snap.sources: self.diag_src.append(pill(src, "good"))
                for note in self.snap.notes: self.diag_src.append(Gtk.Label(label="• "+note, xalign=0, wrap=True, css_classes=["muted","small"]))
        except Exception as e:
            pass

    def _clear_box(self, box):
        ch=box.get_first_child()
        while ch:
            nxt=ch.get_next_sibling()
            classes = ch.get_css_classes() or []
            if not (isinstance(ch, Gtk.Label) and ("h2" in classes or "muted" in classes and "small" in classes)):
                box.remove(ch)
            ch=nxt

    def _copy_diag(self, *_):
        text=json.dumps(getattr(self,'diag',{}), ensure_ascii=False, indent=2)
        Gdk.Display.get_default().get_clipboard().set(text)
        self.toast.add_toast(Adw.Toast(title=t("toast.copied")))

    def _export_diag(self, *_):
        from .utils import data_dir
        path = data_dir() / f"netscope-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps({"diagnostics":getattr(self,'diag',{}), "snapshot_interface":self._iface()}, ensure_ascii=False, indent=2), encoding='utf-8')
        self.toast.add_toast(Adw.Toast(title=f"{t('toast.exported')}: {path}"))

class NetScopeApp(Adw.Application):
    def __init__(self, settings): super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS); self.settings=settings
    def do_activate(self):
        try:
            w=self.props.active_window
            if not w:
                # avoid duplicates
                wins = self.get_windows()
                w = wins[0] if wins else MainWindow(self,self.settings)
            try: w.set_visible(True)
            except Exception: pass
            w.present()
        except Exception as e:
            try:
                import traceback, pathlib
                log = pathlib.Path.home()/'.cache/netscope/startup-error.log'
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(traceback.format_exc())
            except Exception: pass
            print(f"NetScope failed to start: {e}", file=sys.stderr)
            raise

def run_gui(argv=None):
    if not GTK_AVAILABLE: print("GTK/libadwaita is not available. Use --cli mode.", file=sys.stderr); return 1
    settings=Settings.load(); init_i18n(settings.language)
    Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR)
    app=NetScopeApp(settings); return app.run(argv or [sys.argv[0]])
