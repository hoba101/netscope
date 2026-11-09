# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import sys
from datetime import date, datetime

from . import __version__
from .backends.collector import collect_snapshot, list_interfaces
from .i18n import init as init_i18n, t
from .settings import Settings
from .utils import fmt_bytes


def _c(text, code):
    if not sys.stdout.isatty(): return text
    return f"\033[{code}m{text}\033[0m"


def _point_dict(p):
    s = p.start.isoformat() if hasattr(p.start, 'isoformat') else str(p.start)
    return {"start": s, "label": p.label, "detail": p.detail, "rx": p.rx, "tx": p.tx, "total": p.total}


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    settings = Settings.load()
    init_i18n(settings.language)
    if not argv or argv == ["summary"]: argv = ["summary"]
    if argv[0] in ("-h", "--help", "help"):
        print(t("cli.usage"))
        print("  netscope --gui           Launch graphical interface")
        print("  netscope --cli doctor|permissions|accuracy|quota|control-status")
        print("  netscope --cli control throttle --iface IFACE --kbit N  (may need root/pkexec)")
        print("  netscope --cli control restore|disconnect|connect [--iface IFACE]")
        return 0
    if argv[0] == "doctor" or argv[0] == "permissions":
        from .permissions import scan
        print(json.dumps(scan().as_dict(), ensure_ascii=False, indent=2)); return 0
    if argv[0] == "accuracy":
        from .accuracy import collect
        snap = collect_snapshot(settings=settings)
        iface = snap.interface.name if snap else settings.selected_interface
        print(json.dumps(collect(iface).as_dict(), ensure_ascii=False, indent=2)); return 0
    if argv[0] == "quota":
        from .quota import evaluate
        snap = collect_snapshot(settings=settings)
        q = evaluate(snap, settings)
        print(json.dumps(q.__dict__, ensure_ascii=False, indent=2)); return 0
    if argv[0] == "monitor-once":
        from .quota import evaluate
        from . import controls, alerts, storage
        snap = collect_snapshot(settings=settings)
        q = evaluate(snap, settings)
        fired = alerts.evaluate(snap, settings, snap.live_rx_bps, snap.live_tx_bps, do_notify=True)
        result = {"quota": q.__dict__, "alerts_fired": fired, "action_result": None}
        if settings.quota_enabled and (q.warn or q.exceeded):
            if q.exceeded and settings.quota_action == "throttle":
                result["action_result"] = controls.throttle_linux(q.interface or snap.interface.name, settings.quota_throttle_kbit).__dict__
            elif q.exceeded and settings.quota_action in ("disconnect", "disable_interface"):
                result["action_result"] = controls.disconnect_linux(q.interface or snap.interface.name).__dict__
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if not q.exceeded else 2
    if argv[0] == "alerts":
        from . import storage
        print(json.dumps(storage.list_alerts(200), ensure_ascii=False, indent=2)); return 0

    if argv[0] == "control-status":
        from . import controls
        snap = collect_snapshot(settings=settings)
        iface = snap.interface.name if snap else settings.selected_interface
        print(json.dumps(controls.status_linux(iface), ensure_ascii=False, indent=2)); return 0
    if argv[0] == "control":
        from . import controls
        if len(argv) < 2: print("control: throttle|restore|disconnect|connect", file=sys.stderr); return 2
        sub = argv[1]; args = argv[2:]
        iface = settings.selected_interface
        kbit = settings.quota_throttle_kbit
        i = 0
        while i < len(args):
            if args[i] == "--iface" and i+1 < len(args): iface = args[i+1]; i += 2
            elif args[i] == "--kbit" and i+1 < len(args): kbit = int(args[i+1]); i += 2
            else: i += 1
        if sub == "throttle": res = controls.throttle_linux(iface, kbit)
        elif sub == "restore": res = controls.restore_linux(iface)
        elif sub == "disconnect": res = controls.disconnect_linux(iface)
        elif sub == "connect": res = controls.connect_linux(iface)
        else: print("unknown control", file=sys.stderr); return 2
        print(json.dumps(res.__dict__, ensure_ascii=False, indent=2)); return 0 if res.ok else 1

    if argv[0] == "interfaces":
        for name in list_interfaces(settings): print(name)
        return 0
    snap = collect_snapshot(settings=settings)
    if not snap:
        print(t("cli.no_data"), file=sys.stderr); return 1
    if "--panel" in argv:
        today = date.today()
        day = next((p for p in snap.day if getattr(p.start,'year',None)==today.year and getattr(p.start,'month',None)==today.month and getattr(p.start,'day',None)==today.day), None)
        rx = day.rx if day else 0; tx = day.tx if day else 0
        print(f"↓{fmt_bytes(rx, compact=True)} ↑{fmt_bytes(tx, compact=True)}"); return 0
    if "export-json" in argv or "--json" in argv:
        data = {
            "app": "NetScope", "version": __version__, "generated_at": datetime.now().isoformat(),
            "interface": {"name": snap.interface.name, "created": snap.interface.created.isoformat() if snap.interface.created else None, "updated": snap.interface.updated.isoformat() if snap.interface.updated else None, "source": snap.interface.source},
            "sources": snap.sources, "notes": snap.notes,
            "hour": [_point_dict(p) for p in snap.hour], "day": [_point_dict(p) for p in snap.day], "month": [_point_dict(p) for p in snap.month], "year": [_point_dict(p) for p in snap.year], "top": [_point_dict(p) for p in snap.top], "fiveminute": [_point_dict(p) for p in snap.fiveminute],
        }
        print(json.dumps(data, ensure_ascii=False, indent=2)); return 0
    cmd = argv[0]
    if cmd == "summary":
        today = date.today(); now = datetime.now()
        month = next((p for p in reversed(snap.month) if getattr(p.start,'month',None)==today.month and getattr(p.start,'year',None)==today.year), None)
        day = next((p for p in reversed(snap.day) if getattr(p.start,'day',None)==today.day and getattr(p.start,'month',None)==today.month and getattr(p.start,'year',None)==today.year), None)
        hour = next((p for p in reversed(snap.hour) if getattr(p.start,'hour',None)==now.hour and getattr(p.start,'day',None)==today.day), None)
        print(_c(f"NetScope — {snap.interface.name}", "1"))
        print(f"{t('status.sources')}: {', '.join(snap.sources) if snap.sources else '-'}")
        if snap.interface.created: print(f"{t('status.recording_since')}: {snap.interface.created}")
        for label, p in ((t('summary.month'), month), (t('summary.today'), day), (t('summary.hour'), hour)):
            rx = p.rx if p else 0; tx = p.tx if p else 0
            print(f"  {label:<16} {fmt_bytes(rx+tx):>10}  {_c('↓'+fmt_bytes(rx),'34')}  {_c('↑'+fmt_bytes(tx),'33')}")
        print()
        if "hours" not in argv: _table(snap.hour[-24:], t("chart.hours", count=24))
        for note in snap.notes[:3]: print(_c(note, "2"))
        return 0
    mapping = {"hours": ("hour", 24), "days": ("day", 30), "months": ("month", 12), "years": ("year", 10), "top": ("top", 15), "5min": ("fiveminute", 48), "fiveminute": ("fiveminute", 48)}
    if cmd in mapping:
        attr, n = mapping[cmd]
        pts = getattr(snap, attr)
        if cmd == "top": pts = sorted(pts, key=lambda p: p.total, reverse=True)
        _table(pts[-n:] if cmd != "top" else pts[:n], cmd)
        return 0
    print(t("cli.usage"), file=sys.stderr); return 2


def _table(points, title):
    active = [p for p in points if p.total > 0]
    print(f"{title}:")
    if not active: print("  -"); return
    mx = max(p.total for p in active) or 1
    for p in active:
        bar = "█" * max(1, round(20 * p.total / mx))
        label = p.label or (p.start.isoformat() if hasattr(p.start,'isoformat') else str(p.start))
        print(f"  {label:<16} {bar:<20} {fmt_bytes(p.total):>10}  {_c('↓'+fmt_bytes(p.rx),'34')} {_c('↑'+fmt_bytes(p.tx),'33')}")
    print()
