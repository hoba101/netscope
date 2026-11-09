# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Privileged helper for whitelisted NetScope actions. Use with pkexec/sudo explicitly."""

from __future__ import annotations

import argparse
import json
import sys

from . import controls


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="netscope-helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("throttle")
    t.add_argument("--iface", required=True)
    t.add_argument("--kbit", type=int, required=True)
    r = sub.add_parser("restore")
    r.add_argument("--iface", required=True)
    d = sub.add_parser("disconnect")
    d.add_argument("--iface", default="")
    c = sub.add_parser("connect")
    c.add_argument("--iface", default="")
    sub.add_parser("capabilities")
    args = p.parse_args(argv)
    if args.cmd == "capabilities":
        print(json.dumps(controls.capabilities(), indent=2))
        return 0
    if args.cmd == "throttle":
        res = controls.throttle_linux(args.iface, args.kbit)
    elif args.cmd == "restore":
        res = controls.restore_linux(args.iface)
    elif args.cmd == "disconnect":
        res = controls.disconnect_linux(args.iface)
    elif args.cmd == "connect":
        res = controls.connect_linux(args.iface)
    else:
        print("unknown", file=sys.stderr)
        return 2
    print(json.dumps(res.__dict__, ensure_ascii=False, indent=2))
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
