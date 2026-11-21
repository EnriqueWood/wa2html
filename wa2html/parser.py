"""Parsing of the plain-text transcript inside a WhatsApp chat export.

WhatsApp writes one of two header layouts, depending on the platform::

    iOS:      [27-10-26, 11:55:22 AM] Alice: Hello
    Android:  27/10/26, 11:55 - Alice: Hello

Date order, separators, seconds and the AM/PM marker follow the phone's region
settings, so the exact layout is detected from the file itself and then used
strictly: a line only starts a new message if its header has exactly that
layout. Everything else (including WhatsApp messages that someone copied and
pasted into a message, which use a shorter header) belongs to the previous
message. No line is ever dropped; :func:`parse_transcript` checks that.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

_SP = "[ \\t\\u00a0\\u202f]"
_DATE = r"(?P<date>\d{1,4}(?P<sep>[./-])\d{1,2}(?P=sep)\d{1,4})"
_TIME = r"(?P<time>\d{1,2}[:.]\d{2}(?P<sec>[:.]\d{2})?)"
_AMPM = r"(?:" + _SP + r"*(?P<ampm>[AaPp]\.?" + _SP + r"?[Mm]\.?))?"
_LEAD = r"^[‎‏]?"

HEADER_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "ios": re.compile(
        _LEAD + r"\[" + _DATE + r",?" + _SP + r"+" + _TIME + _AMPM + r"\]" + _SP + r"?(?P<rest>.*)$"
    ),
    "android": re.compile(
        _LEAD + _DATE + r",?" + _SP + r"+" + _TIME + _AMPM + _SP + r"+[-–]" + _SP + r"(?P<rest>.*)$"
    ),
}

# "Alice: text" or "Alice:" (message whose text starts on the next line).
_SENDER_RE = re.compile(r"^(?P<sender>[^:\n]{1,100}?):(?:[  ](?P<body>.*))?$", re.DOTALL)

DATE_ORDERS = ("dmy", "mdy", "ymd")


class TranscriptFormatError(Exception):
    """The transcript does not look like a WhatsApp chat export."""


@dataclass
class TranscriptFormat:
    platform: str  # "ios" or "android"
    separator: str  # date separator: "/", "-" or "."
    has_seconds: bool
    has_ampm: bool
    date_order: str  # "dmy", "mdy" or "ymd"
    date_order_guessed: bool = False

    def describe(self) -> str:
        order = {"dmy": "day-first", "mdy": "month-first", "ymd": "year-first"}[self.date_order]
        guess = ", guessed" if self.date_order_guessed else ""
        clock = "12-hour" if self.has_ampm else "24-hour"
        return f"{self.platform} layout, {order} dates{guess}, {clock} clock"


@dataclass
class Message:
    index: int
    line_no: int  # 1-based line in the transcript where the message starts
    raw_date: str
    raw_time: str
    timestamp: Optional[datetime]
    sender: Optional[str]
    body: str
    raw_lines: List[str] = field(default_factory=list)

    # Filled in by wa2html.chat.classify_message
    kind: str = "text"
    text: str = ""
    attachment: Optional[str] = None
    attachment_missing: bool = False
    omitted: Optional[str] = None
    edited: bool = False
    call: Optional[Dict[str, object]] = None
    location: Optional[Dict[str, str]] = None
    doc_meta: str = ""


@dataclass
class Transcript:
    format: TranscriptFormat
    messages: List[Message]
    line_count: int


def _signature(match: "re.Match[str]") -> Tuple[str, bool, bool]:
    return (match.group("sep"), match.group("sec") is not None, match.group("ampm") is not None)


def _date_parts(raw_date: str) -> List[str]:
    return re.split(r"[./-]", raw_date)


def _to_datetime(raw_date: str, raw_time: str, ampm: Optional[str], order: str) -> Optional[datetime]:
    try:
        parts = [int(p) for p in _date_parts(raw_date)]
        if order == "ymd":
            year, month, day = parts
        elif order == "mdy":
            month, day, year = parts
        else:
            day, month, year = parts
        if year < 100:
            year += 2000
        tparts = [int(p) for p in re.split(r"[:.]", raw_time)]
        hour, minute = tparts[0], tparts[1]
        second = tparts[2] if len(tparts) > 2 else 0
        if ampm:
            marker = ampm.strip().lower()[0]
            if marker == "p" and hour < 12:
                hour += 12
            elif marker == "a" and hour == 12:
                hour = 0
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return None


def _backwards_steps(matches: Sequence["re.Match[str]"], order: str) -> int:
    steps = 0
    previous = None
    for m in matches:
        ts = _to_datetime(m.group("date"), m.group("time"), m.group("ampm"), order)
        if ts is None:
            steps += 1
            continue
        if previous is not None and ts < previous:
            steps += 1
        previous = ts
    return steps


def detect_format(lines: Sequence[str], date_order: str = "auto") -> TranscriptFormat:
    best = None
    for platform, pattern in HEADER_PATTERNS.items():
        signatures: Counter = Counter()
        for line in lines:
            m = pattern.match(line)
            if m:
                signatures[_signature(m)] += 1
        total = sum(signatures.values())
        if total and (best is None or total > best[1]):
            best = (platform, total, signatures.most_common(1)[0][0])
    if best is None:
        raise TranscriptFormatError(
            "no WhatsApp message headers found (expected lines such as "
            "'[27-10-26, 11:55:22 AM] Name: text' or '27/10/26, 11:55 - Name: text')"
        )
    platform, _, (sep, has_seconds, has_ampm) = best
    pattern = HEADER_PATTERNS[platform]
    matches = [m for m in map(pattern.match, lines) if m and _signature(m) == (sep, has_seconds, has_ampm)]

    guessed = False
    if date_order != "auto":
        if date_order not in DATE_ORDERS:
            raise ValueError(f"date order must be one of {DATE_ORDERS} or 'auto'")
        order = date_order
    elif any(len(_date_parts(m.group("date"))[0]) == 4 for m in matches):
        order = "ymd"
    else:
        firsts = [int(_date_parts(m.group("date"))[0]) for m in matches]
        seconds = [int(_date_parts(m.group("date"))[1]) for m in matches]
        if max(firsts) > 12:
            order = "dmy"
        elif max(seconds) > 12:
            order = "mdy"
        else:
            # Every day so far is <= 12: pick the order that keeps the
            # messages in chronological order.
            guessed = True
            order = min(("dmy", "mdy"), key=lambda o: _backwards_steps(matches, o))
    return TranscriptFormat(platform, sep, has_seconds, has_ampm, order, guessed)


def _split_lines(text: str) -> List[str]:
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_transcript(text: str, date_order: str = "auto") -> Transcript:
    lines = _split_lines(text)
    fmt = detect_format(lines, date_order)
    pattern = HEADER_PATTERNS[fmt.platform]
    wanted = (fmt.separator, fmt.has_seconds, fmt.has_ampm)

    messages: List[Message] = []
    current: Optional[Message] = None
    for line_no, line in enumerate(lines, 1):
        m = pattern.match(line)
        if m and _signature(m) == wanted:
            rest = m.group("rest")
            sm = _SENDER_RE.match(rest)
            if sm:
                sender: Optional[str] = sm.group("sender")
                body = sm.group("body") or ""
            else:
                sender, body = None, rest
            current = Message(
                index=len(messages),
                line_no=line_no,
                raw_date=m.group("date"),
                raw_time=m.group("time") + ((" " + m.group("ampm").strip()) if m.group("ampm") else ""),
                timestamp=_to_datetime(m.group("date"), m.group("time"), m.group("ampm"), fmt.date_order),
                sender=sender,
                body=body,
                raw_lines=[line],
            )
            messages.append(current)
        elif current is None:
            # Text before the first header: keep it as a notice without date.
            current = Message(len(messages), line_no, "", "", None, None, line, [line])
            messages.append(current)
        else:
            current.raw_lines.append(line)
            current.body += "\n" + line

    rebuilt = [line for msg in messages for line in msg.raw_lines]
    if rebuilt != lines:  # pragma: no cover - guards the invariant above
        raise AssertionError("internal error: transcript lines were lost while parsing")
    return Transcript(fmt, messages, len(lines))
