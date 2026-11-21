"""Render a :class:`~wa2html.chat.Chat` as a WhatsApp-style HTML page.

Messages are written as static HTML, so the text stays readable even with
JavaScript disabled and the browser's own find (Ctrl+F) works. Media is
either embedded in the page (``single`` mode, base64 in inert
``<script type="application/octet-stream">`` blocks that the viewer turns
into blob URLs when they scroll into view) or copied next to it (``folder``
mode).
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import IO, Dict, List, Optional, Tuple

from . import __version__, i18n, probe
from .chat import Chat, MediaItem, Sender, media_type
from .icons import icon
from .parser import Message
from .source import ExportSource

ASSETS = Path(__file__).with_name("assets")
VENDOR_LOTTIE = ASSETS / "vendor" / "lottie.min.js"
LOTTIE_NOTICE = (
    "/*! lottie-web 5.12.2 (light build) | MIT License | Copyright (c) 2015 Bodymovin | "
    "https://github.com/airbnb/lottie-web */\n"
)


@dataclass
class RenderOptions:
    mode: str = "single"  # "single" or "folder"
    lang: str = "auto"
    theme: str = "auto"
    time_format: str = "auto"  # "auto", "12" or "24"
    wallpaper: str = "default"  # "default" (theme colour) or a CSS colour/gradient
    pattern: bool = True  # doodle pattern over the wallpaper
    wallpaper_image: Optional[Tuple[bytes, str]] = None  # (data, mime)
    avatar: Optional[Tuple[bytes, str]] = None  # the contact: header and their voice messages
    my_avatar: Optional[Tuple[bytes, str]] = None  # the owner of the export: their voice messages
    lottie_js: Optional[str] = None


@dataclass
class RenderResult:
    path: Path
    bytes_written: int = 0
    messages_rendered: int = 0
    media_files: int = 0
    media_blocks: int = 0
    warnings: List[str] = field(default_factory=list)


# -- text formatting ---------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```(.+?)```", re.DOTALL)
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)\]}¡¿…]")
_STYLE_RES = [
    (re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])"), "strong"),
    (re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])"), "em"),
    (re.compile(r"(?<![\w~])~(?=\S)([^~\n]+?)(?<=\S)~(?![\w~])"), "s"),
    (re.compile(r"(?<![\w`])`(?=\S)([^`\n]+?)(?<=\S)`(?![\w`])"), "code"),
]
_QUOTE_RE = re.compile(r"(?m)^&gt; (.*)$")


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for regex, tag in _STYLE_RES:
        out = regex.sub(lambda m, tag=tag: f"<{tag}>{m.group(1)}</{tag}>", out)
    return _QUOTE_RE.sub(r'<span class="q">\1</span>', out)


def _format_plain(text: str) -> str:
    out = []
    pos = 0
    for m in _URL_RE.finditer(text):
        out.append(_inline(text[pos : m.start()]))
        url = m.group(0)
        href = url if url.lower().startswith("http") else "http://" + url
        out.append(
            f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">'
            f"{html.escape(url, quote=False)}</a>"
        )
        pos = m.end()
    out.append(_inline(text[pos:]))
    return "".join(out)


def format_text(text: str) -> str:
    """WhatsApp formatting (*bold*, _italic_, ~strike~, ```code```) and links."""
    parts = []
    pos = 0
    for m in _CODE_BLOCK_RE.finditer(text):
        parts.append(_format_plain(text[pos : m.start()]))
        parts.append(f'<code class="block">{html.escape(m.group(1), quote=False)}</code>')
        pos = m.end()
    parts.append(_format_plain(text[pos:]))
    return "".join(parts)


def is_emoji_only(text: str, limit: int = 3) -> bool:
    """True for messages made of 1-3 emoji, which WhatsApp shows large."""
    text = text.strip()
    if not text or len(text) > 40:
        return False
    count = 0.0
    joined = False
    for ch in text:
        cp = ord(ch)
        if ch.isspace():
            continue
        if cp == 0x200D:
            joined = True
            continue
        if cp in (0xFE0F, 0xFE0E, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F:
            continue
        emoji = (
            0x1F000 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF
            or 0x2B00 <= cp <= 0x2BFF
            or 0x2300 <= cp <= 0x23FF
            or 0x2190 <= cp <= 0x21FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299)
        )
        if not emoji:
            return False
        if not joined:
            count += 0.5 if 0x1F1E6 <= cp <= 0x1F1FF else 1
        joined = False
    return 0 < count <= limit


# -- small helpers -----------------------------------------------------------


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _script_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _static_time(ts: Optional[datetime], fallback: str, twelve: bool) -> str:
    if ts is None:
        return fallback
    if twelve:
        hour = ts.hour % 12 or 12
        return f"{hour}:{ts.minute:02d} {'PM' if ts.hour >= 12 else 'AM'}"
    return f"{ts.hour:02d}:{ts.minute:02d}"


def _initials(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w and w[0].isalnum()]
    if not words:
        return "?"
    letters = words[0][0] + (words[1][0] if len(words) > 1 else "")
    return letters.upper()


def _aspect(item: MediaItem, low: float = 0.55, high: float = 1.9) -> str:
    if item.width and item.height:
        ratio = max(low, min(high, item.width / item.height))
        return f"{ratio:.4f}"
    return "1"


def display_name(name: str) -> str:
    """iOS prefixes attachment names with a counter: '00001292-report.pdf'."""
    return re.sub(r"^\d{8}-", "", name)


def _safe_filename(name: str, taken: set) -> str:
    base = re.sub(r"[^\w.\- ()]", "_", name).strip(" .") or "file"
    base = base[:150]
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    candidate = base
    n = 2
    while candidate.lower() in taken:
        candidate = f"{stem}-{n}.{ext}" if ext else f"{stem}-{n}"
        n += 1
    taken.add(candidate.lower())
    return candidate


def _wave_path(values: List[int], height: int = 32) -> Tuple[str, int]:
    step = 3.5
    parts = []
    for i, v in enumerate(values):
        x = 1.5 + i * step
        h = max(3.0, height * v / 100.0 - 3)
        y1 = (height - h) / 2
        parts.append(f"M{x:.1f} {y1:.1f}V{y1 + h:.1f}")
    return "".join(parts), int(len(values) * step + 1)


def _fake_wave(seed: str, bars: int = 40) -> List[int]:
    digest = hashlib.sha256(seed.encode()).digest()
    return [20 + digest[i % len(digest)] * 70 // 255 for i in range(bars)]


# -- the renderer ------------------------------------------------------------


class Renderer:
    def __init__(self, chat: Chat, source: ExportSource, options: RenderOptions):
        self.chat = chat
        self.source = source
        self.opt = options
        self.static_lang = options.lang if options.lang in i18n.STRINGS else "en"
        if options.time_format == "auto":
            self.time_format = "12" if chat.format.has_ampm else "24"
        else:
            self.time_format = options.time_format
        self.twelve = self.time_format == "12"
        self.senders: Dict[str, Sender] = {}
        for s in chat.senders:
            self.senders[s.name.casefold()] = s
        self.blocks: List[Tuple[str, MediaItem]] = []  # (block id, item) to embed
        self.files: List[Tuple[str, MediaItem]] = []  # (relative path, item) to copy
        self.lottie_blocks: List[Tuple[str, MediaItem]] = []
        self.lottie_included = False
        self.rendered = 0
        self.first_use: Dict[str, int] = {}
        for msg in chat.messages:
            if msg.attachment and msg.attachment not in self.first_use:
                self.first_use[msg.attachment] = msg.index

    # -- media references --------------------------------------------------

    def assign_refs(self) -> None:
        by_hash: Dict[str, str] = {}
        taken: set = set()
        counter = 0
        for name in sorted(self.chat.media, key=self._media_order):
            item = self.chat.media[name]
            # Identical files (a sticker sent many times) are embedded once.
            # In folder mode every file is copied under its own name, so the
            # media folder stays a complete copy of the export.
            key = item.kind + ":" + item.sha256 if (self.opt.mode == "single" or item.kind == "lottie") else name
            if key in by_hash:
                item.ref = by_hash[key]
                if item.ref.startswith("#"):
                    item.block = item.ref[1:]
                if self.opt.mode == "folder":  # duplicated animated sticker: keep its file too
                    self.files.append((_safe_filename(name, taken), item))
                continue
            if item.kind == "lottie":
                # The animation is always inlined: browsers refuse to fetch
                # local files, and the player needs the JSON itself.
                counter += 1
                item.block = f"b{counter}"
                item.ref = "#" + item.block
                self.lottie_blocks.append((item.block, item))
                if self.opt.mode == "folder":
                    self.files.append((_safe_filename(name, taken), item))
            elif self.opt.mode == "single":
                counter += 1
                item.block = f"b{counter}"
                item.ref = "#" + item.block
                self.blocks.append((item.block, item))
            else:
                safe = _safe_filename(name, taken)
                item.ref = "media/" + urllib.parse.quote(safe)
                self.files.append((safe, item))
            by_hash[key] = item.ref

    def _media_order(self, name: str) -> Tuple[int, str]:
        # Embed media in the order it appears in the chat.
        return (self.first_use.get(name, len(self.chat.messages)), name)

    # -- message parts -----------------------------------------------------

    def _sender(self, msg: Message) -> Optional[Sender]:
        if msg.sender is None:
            return None
        return self.chat.sender_by_name(msg.sender)

    def _meta(self, msg: Optional[Message], label: str = "") -> str:
        edited = ""
        if msg is not None and msg.edited:
            edited = f'<span class="edited" data-i18n="edited">{esc(i18n.t(self.static_lang, "edited"))}</span>'
        if msg is None:
            return f'<span class="meta"><span class="fname">{esc(label)}</span></span>'
        ts = msg.timestamp
        attr = f' data-ts="{ts.isoformat()}"' if ts else ""
        title = esc(f"{msg.raw_date} {msg.raw_time}".strip())
        return (
            f'<span class="meta">{edited}<time{attr} title="{title}">'
            f"{esc(_static_time(ts, msg.raw_time, self.twelve))}</time></span>"
        )

    def _caption(self, text: str) -> str:
        if not text:
            return ""
        return f'<div class="text caption" dir="auto">{format_text(text)}</div>'

    def _download_button(self, item: MediaItem) -> str:
        label = esc(i18n.t(self.static_lang, "download"))
        return (
            f'<a class="dl" href="{esc(item.ref if not item.block else "#")}" data-dl="{esc(item.ref)}" '
            f'data-name="{esc(display_name(item.name))}" download="{esc(display_name(item.name))}" '
            f'title="{label}" aria-label="{label}" data-i18n-title="download">{icon("download")}</a>'
        )

    def _media_html(self, item: MediaItem, sender: Optional[Sender]) -> Tuple[str, str]:
        """Return (kind class, html) for an attachment."""
        ref = esc(item.ref)
        t = lambda key: esc(i18n.t(self.static_lang, key))  # noqa: E731
        size_attrs = f' width="{item.width}" height="{item.height}"' if item.width and item.height else ""
        if item.kind == "image":
            if item.mime == "image/heic":
                return "doc", self._doc_html(item)
            return "image", (
                f'<button class="media img" type="button" style="aspect-ratio:{_aspect(item)}" '
                f'aria-label="{t("photo")}"><img data-src="{ref}" alt=""{size_attrs} decoding="async"></button>'
                + self._download_button(item)
            )
        if item.kind == "sticker":
            return "sticker", f'<div class="sticker"><img data-src="{ref}" alt="Sticker"{size_attrs} decoding="async"></div>'
        if item.kind == "lottie":
            return "sticker", (
                f'<div class="sticker lottie" data-lottie="{ref}" role="img" aria-label="{t("animatedSticker")}">'
                f'<span class="lottie-fallback">{icon("smile")}<small data-i18n="animatedSticker">{t("animatedSticker")}</small></span></div>'
            )
        if item.kind in ("video", "gif"):
            if item.kind == "gif":
                player = f'<video data-src="{ref}" muted loop playsinline autoplay preload="auto"></video><span class="badge">GIF</span>'
            else:
                badge = f'<span class="badge">{icon("videocam")}{esc(_duration(item.duration))}</span>'
                player = f'<video data-src="{ref}" preload="metadata" controls playsinline></video>{badge}'
            return item.kind, (
                f'<div class="media vid" style="aspect-ratio:{_aspect(item)}">{player}</div>' + self._download_button(item)
            )
        if item.kind in ("voice", "audio"):
            wave = item.waveform or _fake_wave(item.sha256 or item.name)
            path, width = _wave_path(wave)
            bars = (
                f'<svg class="v-bars" viewBox="0 0 {width} 32" preserveAspectRatio="none" aria-hidden="true">'
                f'<path d="{path}"/></svg>'
            )
            if item.kind == "voice" and sender is not None:
                avatar = f'<span class="v-avatar" style="--c:{sender.color}">{esc(_initials(sender.name))}<span class="v-badge">{icon("mic")}</span></span>'
            else:
                avatar = f'<span class="v-avatar music">{icon("headphones")}</span>'
            dur = item.duration if item.duration is not None else ""
            return item.kind, (
                f'<div class="voice" data-src="{ref}" data-dur="{dur}">'
                f"{avatar}"
                f'<button class="v-play" type="button" aria-label="{t("play")}" data-i18n-title="play">{icon("play", "i-play")}{icon("pause", "i-pause")}</button>'
                f'<div class="v-body"><div class="v-wave">{bars}<div class="v-fill">{bars}</div>'
                f'<input class="v-seek" type="range" min="0" max="1000" value="0" aria-label="{t("voiceMessage")}"></div>'
                f'<div class="v-foot"><span class="v-time">{esc(_duration(item.duration) or "0:00")}</span>'
                f'<button class="v-speed" type="button" title="{t("speed")}" data-i18n-title="speed">1×</button></div>'
                f'<div class="v-err" hidden><span data-i18n="cantPlay">{t("cantPlay")}</span></div></div></div>'
                + self._download_button(item)
            )
        if item.kind == "contact" and item.vcard:
            phones = "".join(f'<span class="c-phone">{esc(p)}</span>' for p in item.vcard.get("phones", [])[:3])
            name = item.vcard.get("name") or display_name(item.name)
            return "contact", (
                f'<div class="contact"><span class="c-avatar">{icon("person")}</span>'
                f'<span class="c-text"><span class="c-name">{esc(name)}</span>{phones}</span></div>'
                f'<a class="c-save" href="{esc(item.ref if not item.block else "#")}" data-dl="{ref}" '
                f'data-name="{esc(display_name(item.name))}" download="{esc(display_name(item.name))}" data-i18n="save">{t("save")}</a>'
            )
        return "doc", self._doc_html(item)

    def _doc_html(self, item: MediaItem, meta: str = "") -> str:
        name = display_name(item.name)
        ext = name.rsplit(".", 1)[-1].upper()[:4] if "." in name else "FILE"
        details = " · ".join(x for x in (_human_size(item.size), ext, meta) if x)
        return (
            f'<a class="doc" href="{esc(item.ref if not item.block else "#")}" data-dl="{esc(item.ref)}" '
            f'data-name="{esc(name)}" download="{esc(name)}">'
            f'<span class="doc-icon">{icon("doc")}<b>{esc(ext)}</b></span>'
            f'<span class="doc-text"><span class="doc-name">{esc(name)}</span><span class="doc-meta">{esc(details)}</span></span>'
            f'<span class="doc-dl">{icon("download")}</span></a>'
        )

    def render_message(self, msg: Message, first: bool) -> str:
        self.rendered += 1
        mid = f'id="m{msg.index}"'
        if msg.kind == "system":
            ts = f' data-ts="{msg.timestamp.isoformat()}"' if msg.timestamp else ""
            lock = icon("lock") if re.search(r"encrypt|cifrad|criptograf", msg.text, re.I) else ""
            return f'<div class="sys" {mid}{ts}><span>{lock}{format_text(msg.text)}</span></div>'

        sender = self._sender(msg)
        side = "out" if sender is not None and sender.id == self.chat.me else "in"
        classes = ["msg", side]
        if first:
            classes.append("first")
        if msg.edited:
            classes.append("edited")
        t = lambda key: esc(i18n.t(self.static_lang, key))  # noqa: E731

        kind = msg.kind
        content = ""
        if msg.kind == "media":
            item = self.chat.media.get(msg.attachment or "")
            if msg.attachment_missing or item is None:
                kind = "missing"
                content = (
                    f'<div class="omitted missing">{icon("warning")}<span><span data-i18n="missing">{t("missing")}</span>'
                    f"<small>{esc(msg.attachment or '')}</small></span></div>" + self._caption(msg.text)
                )
            else:
                if item.kind == "document" and msg.doc_meta:
                    kind, content = "doc", self._doc_html(item, msg.doc_meta)
                else:
                    kind, content = self._media_html(item, sender)
                caption = msg.text
                if kind == "doc" and caption.strip() == display_name(item.name):
                    caption = ""  # iOS repeats the document name as text
                content += self._caption(caption)
                if caption:
                    classes.append("captioned")
        elif msg.kind == "omitted":
            what = msg.omitted or "media"
            glyph = {"video": "videocam", "gif": "videocam", "audio": "mic", "sticker": "smile",
                     "document": "doc", "contact": "person"}.get(what, "image")
            content = (
                f'<div class="omitted" title="{esc(msg.body.strip())}">{icon(glyph)}'
                f'<span data-i18n="omitted_{what}">{t("omitted_" + what)}</span></div>' + self._caption(msg.text)
            )
        elif msg.kind == "deleted":
            content = f'<div class="deleted">{icon("ban")}<span>{esc(msg.text)}</span></div>'
        elif msg.kind == "call" and msg.call:
            call = msg.call
            extra = (" missed" if call["missed"] else "") + (" video" if call["video"] else "")
            content = (
                f'<div class="call{extra}"><span class="call-icon">{icon("videocam" if call["video"] else "phone")}</span>'
                f'<span class="call-text"><span class="call-label">{esc(call["label"])}</span>'
                f'<span class="call-detail">{esc(call["detail"])}</span></span></div>'
            )
        elif msg.kind == "location" and msg.location:
            loc = msg.location
            label = esc(loc["label"]) if loc["label"] else f'<span data-i18n="location">{t("location")}</span>'
            content = (
                f'<a class="loc" href="{esc(loc["url"])}" target="_blank" rel="noopener noreferrer">'
                f'<span class="loc-map">{icon("pin")}</span>'
                f'<span class="loc-text"><span class="loc-label">{label}</span>'
                f'<span class="loc-coords">{esc(loc["coords"])}</span>'
                f'<span class="loc-open" data-i18n="openMap">{t("openMap")}</span></span></a>'
            )
        elif msg.kind == "notice":
            content = f'<div class="notice">{icon("info")}<span class="text" dir="auto">{format_text(msg.text)}</span></div>'
        else:
            kind = "text"
            if is_emoji_only(msg.text):
                classes.append("jumbo")
            content = f'<div class="text" dir="auto">{format_text(msg.text)}</div>'

        classes.append("k-" + kind)
        name = ""
        if sender is not None and first and self.chat.is_group:
            name = f'<div class="sender" style="color:{sender.color}">{esc(sender.name)}</div>'
        data_s = f' data-s="{sender.id}"' if sender else ""
        return (
            f'<div class="{" ".join(classes)}" {mid}{data_s}><div class="bubble">'
            f"{name}{content}{self._meta(msg)}</div></div>"
        )

    def render_unreferenced(self) -> str:
        if not self.chat.unreferenced:
            return ""
        t = lambda key: esc(i18n.t(self.static_lang, key))  # noqa: E731
        rows = [f'<section class="day extra"><div class="sys"><span data-i18n="unreferenced">{t("unreferenced")}</span></div>']
        for name in self.chat.unreferenced:
            item = self.chat.media[name]
            kind, content = self._media_html(item, None)
            rows.append(
                f'<div class="msg in first k-{kind}"><div class="bubble">{content}{self._meta(None, display_name(name))}</div></div>'
            )
        rows.append("</section>")
        return "".join(rows)

    def render_messages(self) -> str:
        out: List[str] = []
        current_day: Optional[date] = None
        previous_sender: Optional[str] = None
        open_section = False
        for msg in self.chat.messages:
            day = msg.timestamp.date() if msg.timestamp else current_day
            if day != current_day or not open_section:
                if open_section:
                    out.append("</section>")
                current_day = day
                iso = day.isoformat() if day else ""
                label = i18n.format_day(self.static_lang, day) if day else ""
                out.append(
                    f'<section class="day" data-date="{iso}"><div class="day-sep">'
                    f'<span data-date="{iso}">{esc(label)}</span></div>'
                )
                open_section = True
                previous_sender = None
            sender_key = None if msg.kind == "system" or msg.sender is None else msg.sender.casefold()
            first = sender_key is None or sender_key != previous_sender
            out.append(self.render_message(msg, first))
            previous_sender = sender_key
        if open_section:
            out.append("</section>")
        out.append(self.render_unreferenced())
        return "\n".join(out)

    # -- page --------------------------------------------------------------

    def _info_panel(self) -> str:
        chat = self.chat
        t = lambda key: esc(i18n.t(self.static_lang, key))  # noqa: E731
        first, last = chat.first_timestamp, chat.last_timestamp
        period = ""
        if first and last:
            period = (
                f'<span class="dayname" data-date="{first.date().isoformat()}">{esc(first.date().isoformat())}</span> – '
                f'<span class="dayname" data-date="{last.date().isoformat()}">{esc(last.date().isoformat())}</span>'
            )
        people = "".join(
            f'<li><span class="dot" style="background:{s.color}"></span>{esc(s.name)} <small>({s.count:,})</small></li>'
            for s in chat.senders
        )
        counts: Dict[str, int] = {}
        for item in chat.media.values():
            counts[item.kind] = counts.get(item.kind, 0) + 1
        media = ", ".join(
            f'{n:,} <span data-i18n="kind_{k}">{t("kind_" + k)}</span>' for k, n in sorted(counts.items(), key=lambda kv: -kv[1])
        ) or "0"
        omitted = ", ".join(
            f'{n:,} <span data-i18n="kind_{k}">{t("kind_" + k)}</span>' for k, n in chat.omitted.most_common()
        ) or "0"
        missing = f"{len(chat.missing):,}"
        if chat.missing:
            missing += "<ul class=\"files\">" + "".join(f"<li>{esc(n)}</li>" for _, n in chat.missing[:50]) + "</ul>"
        total_messages = sum(1 for m in chat.messages if m.kind != "system")
        return (
            '<dl class="stats">'
            f'<dt data-i18n="statsMessages">{t("statsMessages")}</dt><dd>{total_messages:,}</dd>'
            f'<dt data-i18n="statsPeriod">{t("statsPeriod")}</dt><dd>{period}</dd>'
            f'<dt data-i18n="statsParticipants">{t("statsParticipants")}</dt><dd><ul class="people">{people}</ul></dd>'
            f'<dt data-i18n="statsMedia">{t("statsMedia")}</dt><dd>{media}</dd>'
            f'<dt data-i18n="statsOmitted">{t("statsOmitted")}</dt><dd>{omitted}'
            + (f'<p class="hint" data-i18n="aboutOmitted">{t("aboutOmitted")}</p>' if chat.omitted else "")
            + "</dd>"
            f'<dt data-i18n="statsMissing">{t("statsMissing")}</dt><dd>{missing}</dd>'
            f'<dt data-i18n="statsSource">{t("statsSource")}</dt><dd>{esc(chat.source_name)}<br>'
            f"<small>{esc(chat.transcript_name)} · {chat.line_count:,} lines · {esc(chat.format.describe())}</small></dd>"
            "</dl>"
            f'<button class="btn" type="button" data-dl="#wa-transcript" data-name="{esc(chat.transcript_name)}" '
            f'data-i18n="downloadTranscript">{t("downloadTranscript")}</button>'
            f'<p class="gen"><span data-i18n="generatedBy">{t("generatedBy")}</span> {__version__} · '
            f"{datetime.now().strftime('%Y-%m-%d')}</p>"
        )

    def _avatar(self) -> str:
        if self.opt.avatar:
            # The picture itself is stored once, in --chat-avatar (see _avatar_css).
            return f'<span class="avatar-img" role="img" aria-label="{esc(self.chat.title)}"></span>'
        return esc(_initials(self.chat.title))

    def photo_sender(self) -> Optional[Sender]:
        """The participant the header photo shows: the person the chat is named after."""
        if not self.opt.avatar or self.chat.is_group:
            return None
        named = self.chat.sender_by_name(self.chat.title)
        if named is not None:
            return named if named.id != self.chat.me else None
        others = [s for s in self.chat.senders if s.id != self.chat.me]
        return others[0] if len(others) == 1 and self.chat.me else None

    def _avatar_css(self) -> str:
        """Each picture is stored once, as a CSS variable, and used by its owner's voice messages.

        The rules follow the person (data-s), not the side of the screen, so
        they stay right when a reader changes who is shown on the right.
        """
        css = ""
        rule = '.msg[data-s="{id}"] .v-avatar:not(.music) {{ background: var({var}) center / cover no-repeat; color: transparent; }}\n'
        if self.opt.avatar:
            data, mime = self.opt.avatar
            css += f':root {{ --chat-avatar: url("data:{mime};base64,{base64.b64encode(data).decode()}"); }}\n'
            person = self.photo_sender()
            if person is not None:
                css += rule.format(id=person.id, var="--chat-avatar")
        if self.opt.my_avatar and self.chat.me:
            data, mime = self.opt.my_avatar
            css += f':root {{ --my-avatar: url("data:{mime};base64,{base64.b64encode(data).decode()}"); }}\n'
            css += rule.format(id=self.chat.me, var="--my-avatar")
        return css

    def _subtitle(self) -> str:
        if self.chat.is_group:
            return esc(", ".join(s.name for s in self.chat.senders))
        count = sum(1 for m in self.chat.messages if m.kind != "system")
        return f'{count:,} <span data-i18n="messages">{esc(i18n.t(self.static_lang, "messages"))}</span>'

    def _config(self) -> dict:
        chat = self.chat
        first, last = chat.first_timestamp, chat.last_timestamp
        key_src = f"{chat.title}|{first}|{len(chat.messages)}"
        wall_image = None
        if self.opt.wallpaper_image:
            data, mime = self.opt.wallpaper_image
            wall_image = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        return {
            "chatKey": hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:12],
            "title": chat.title,
            "senders": [{"id": s.id, "name": s.name, "color": s.color} for s in chat.senders],
            "me": chat.me,
            "isGroup": chat.is_group,
            "mode": self.opt.mode,
            "firstDay": first.date().isoformat() if first else "",
            "lastDay": last.date().isoformat() if last else "",
            "defaults": {
                "lang": self.opt.lang,
                "theme": self.opt.theme,
                "time": self.time_format,
                "wallpaper": "image" if wall_image else self.opt.wallpaper,
                "pattern": self.opt.pattern and not wall_image,
                "wallImage": wall_image,
            },
            "strings": i18n.STRINGS,
        }

    def _lottie_script(self) -> str:
        if not self.lottie_blocks:
            return ""
        code = None
        if self.opt.lottie_js:
            code = Path(self.opt.lottie_js).read_text(encoding="utf-8")
        elif VENDOR_LOTTIE.exists():
            code = LOTTIE_NOTICE + VENDOR_LOTTIE.read_text(encoding="utf-8")
        if not code:
            return ""
        self.lottie_included = True
        return "<script>" + code.replace("</script", "<\\/script") + "</script>"

    def page_parts(self) -> Tuple[str, str]:
        template = (ASSETS / "template.html").read_text(encoding="utf-8")
        css = (ASSETS / "viewer.css").read_text(encoding="utf-8")
        js = (ASSETS / "viewer.js").read_text(encoding="utf-8")
        t = lambda key: esc(i18n.t(self.static_lang, key))  # noqa: E731
        config = self._config()
        lottie_data = "".join(
            f'<script type="application/json" id="{block}">{self._lottie_json(item)}</script>\n'
            for block, item in self.lottie_blocks
        )
        transcript = (
            f'<script type="application/octet-stream" id="wa-transcript" data-mime="text/plain;charset=utf-8">'
            f"{base64.b64encode(self.chat.transcript_bytes).decode()}</script>"
        )
        values = {
            "LANG": self.static_lang,
            "THEME": self.opt.theme,
            "TITLE": esc(self.chat.title),
            "CHAT_KEY": config["chatKey"],
            "VERSION": __version__,
            "CSS": css,
            "AVATAR_CSS": self._avatar_css(),
            "AVATAR": self._avatar(),
            "SUBTITLE": self._subtitle(),
            "MESSAGES": self.render_messages(),
            "INFO": self._info_panel(),
            "CONFIG": _script_json(config),
            "LOTTIE_LIB": self._lottie_script(),
            "LOTTIE_DATA": lottie_data,
            "TRANSCRIPT": transcript,
            "JS": js,
        }
        for key in ("search", "searchPlaceholder", "jumpToDate", "info", "settings", "close", "prev", "next",
                    "top", "bottom", "loadingMedia", "download", "noResults"):
            values["T_" + key] = t(key)
        for name in ("search", "calendar", "info", "palette", "close", "up", "down", "left", "right", "download"):
            values["I_" + name] = icon(name)
        head, marker, tail = template.partition("<!--MEDIA-->")
        if not marker:
            raise RuntimeError("template.html lacks the <!--MEDIA--> marker")

        def fill(part: str) -> str:
            return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], part)

        return fill(head), fill(tail)

    def _lottie_json(self, item: MediaItem) -> str:
        data = probe.was_animation_json(self.source.read(item.name))
        if data is None:
            return "null"
        text = data.decode("utf-8", errors="replace")
        try:
            json.loads(text)
        except ValueError:
            return "null"
        return text.replace("<", "\\u003c")

    def write_media_blocks(self, out: IO[str]) -> int:
        written = 0
        for block, item in self.blocks:
            mime = item.mime
            if item.kind == "document":
                mime = "application/octet-stream"  # never let an attached page run inside ours
            out.write(f'<script type="application/octet-stream" id="{block}" data-mime="{esc(mime)}">')
            with self.source.open(item.name) as stream:
                while True:
                    chunk = stream.read(3 * 1024 * 1024)  # multiple of 3: no padding mid-stream
                    if not chunk:
                        break
                    encoded = base64.b64encode(chunk).decode("ascii")
                    out.write(encoded)
                    written += len(encoded)
            out.write("</script>\n")
        return written

    def copy_media_files(self, folder: Path) -> None:
        if not self.files:
            return
        media_dir = folder / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for safe, item in self.files:
            item.copied_as = safe
            target = media_dir / safe
            if target.resolve().parent != media_dir.resolve():  # pragma: no cover - defensive
                raise RuntimeError(f"unsafe media file name: {safe}")
            with self.source.open(item.name) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)


def render(chat: Chat, source: ExportSource, output: Path, options: RenderOptions) -> RenderResult:
    renderer = Renderer(chat, source, options)
    renderer.assign_refs()
    if options.mode == "folder":
        output.mkdir(parents=True, exist_ok=True)
        page = output / "index.html"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        page = output
    before, after = renderer.page_parts()
    result = RenderResult(path=page)
    tmp = page.with_name(page.name + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="") as out:
        out.write(before)
        renderer.write_media_blocks(out)
        out.write(after)
    if options.mode == "folder":
        renderer.copy_media_files(output)
    tmp.replace(page)
    result.bytes_written = page.stat().st_size
    result.messages_rendered = renderer.rendered
    result.media_blocks = len(renderer.blocks) + len(renderer.lottie_blocks)
    result.media_files = len(renderer.files)
    if renderer.lottie_blocks and not renderer.lottie_included:
        count = sum(1 for item in chat.media.values() if item.kind == "lottie")
        result.warnings.append(
            f"{count} animated sticker(s) (.was) are embedded but will show as a placeholder: "
            "no Lottie player is bundled (see README, 'Animated stickers')."
        )
    return result
