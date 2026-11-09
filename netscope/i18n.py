# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight i18n for NetScope.

Uses built-in dictionaries so the app works without gettext toolchain.
Translations live in ``locales/<lang>.json`` and are merged over English.
"""

from __future__ import annotations

import json
import locale
import os
from pathlib import Path
from typing import Any

_lang = "en"
_strings: dict[str, str] = {}
_DIR = Path(__file__).resolve().parent / "data" / "locales"


def init(lang: str | None = None) -> str:
    global _lang, _strings
    if lang and lang not in ("system", "auto"):
        _lang = _normalize(lang)
    else:
        _lang = detect_system_language()
    _strings = _load("en")
    if _lang != "en":
        _strings.update(_load(_lang))
    return _lang


def _normalize(value: str) -> str:
    value = (value or "en").replace("-", "_").split(".")[0].lower()
    if value.startswith("ar"):
        return "ar"
    return "en"


def detect_system_language() -> str:
    for var in ("NETSCOPE_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var)
        if value:
            return _normalize(value)
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0]
        if loc:
            return _normalize(loc)
    except Exception:
        pass
    return "en"


def _load(lang: str) -> dict[str, str]:
    path = _DIR / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_language(lang: str) -> str:
    return init(lang)


def get_language() -> str:
    return _lang


def is_rtl() -> bool:
    return _lang == "ar"


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    text = _strings.get(key) or _load("en").get(key) or default or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
