"""Translations for the window and the generated page.

Each language is one JSON file in ``wa2html/locales/`` with three parts:
``name`` (the language's own name), ``app`` (the window), ``page`` (the
generated page) and ``date`` (names used for the date labels written into the
page). English is the reference: a key missing in another language falls back
to English. To add a language, copy ``en.json`` to ``<code>.json`` and
translate the values; it shows up in the window and in the page.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict, List

LOCALES = Path(__file__).with_name("locales")
PREFERRED_ORDER = ["en", "es", "pt", "fr", "de", "it"]


def _load() -> Dict[str, dict]:
    data = {}
    for file in LOCALES.glob("*.json"):
        data[file.stem] = json.loads(file.read_text(encoding="utf-8"))
    return data


_DATA = _load()

LANGUAGES: List[str] = [c for c in PREFERRED_ORDER if c in _DATA] + sorted(c for c in _DATA if c not in PREFERRED_ORDER)
NAMES: Dict[str, str] = {code: _DATA[code].get("name", code) for code in LANGUAGES}

# Page strings, as embedded in every generated page (all languages).
STRINGS: Dict[str, Dict[str, str]] = {
    code: {"_name": NAMES[code], **_DATA[code].get("page", {})} for code in LANGUAGES
}


def t(lang: str, key: str) -> str:
    """A string of the generated page."""
    return STRINGS.get(lang, STRINGS["en"]).get(key) or STRINGS["en"].get(key, key)


def app_text(lang: str) -> Dict[str, str]:
    """All window strings for a language, completed with English."""
    texts = dict(_DATA["en"].get("app", {}))
    texts.update(_DATA.get(lang, {}).get("app", {}))
    return texts


def format_day(lang: str, day: date) -> str:
    """Static date label; the page re-renders it with the browser's Intl API."""
    names = _DATA.get(lang, _DATA["en"]).get("date") or _DATA["en"]["date"]
    text = names["format"].format(
        weekday=names["weekdays"][day.weekday()],
        day=day.day,
        month=names["months"][day.month - 1],
        year=day.year,
    )
    return text[0].upper() + text[1:]
