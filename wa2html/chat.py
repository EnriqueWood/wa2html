"""Build a chat model from an export: messages, participants and media."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from . import probe
from .parser import Message, Transcript, TranscriptFormat, parse_transcript
from .source import BIDI_MARKS, ExportSource, normalize_name

# -- phrases WhatsApp writes into transcripts -------------------------------
# The phone's language decides these. English and Spanish are covered best;
# others are partial. Anything unrecognised is still shown, as plain text.

ATTACH_LABELS = {
    "attached", "adjunto", "archivo adjunto", "anexado", "arquivo anexado", "allegato",
    "angehängt", "datei angehängt", "pièce jointe", "fichier joint", "bijlage", "ekli", "załączono",
    "file attached",
}

_IOS_ATTACH_RE = re.compile(r"‎?<(?P<label>[^<>:\n]{1,40}):[  ](?P<name>[^<>\n]+?)>")
_ANDROID_ATTACH_RE = re.compile(r"^‎?(?P<name>[^\n]+?\.[A-Za-z0-9]{1,6})[  ]\((?P<label>[^()\n]{1,40})\)$")

_OMITTED_RE = re.compile(
    r"^<?\s*(?P<what>[^<>\n]{1,40}?)\s+(?:omitted|omitid[oa]s?|ocult[oa]|ocultad[oa]|omess[oa]|"
    r"weggelassen|ausgelassen|omise?|omis)\s*>?$",
    re.IGNORECASE,
)
_OMITTED_KINDS = [
    ("sticker", ("sticker", "pegatina", "figurinha")),
    ("gif", ("gif",)),
    ("video", ("video", "vídeo")),
    ("audio", ("audio", "áudio", "voice", "voz")),
    ("image", ("image", "imagen", "imagem", "photo", "foto", "bild")),
    ("contact", ("contact", "contacto", "contato", "kontakt")),
    ("document", ("document", "documento", "file", "archivo", "arquivo", "datei")),
]

_DELETED_RE = re.compile(
    r"^(?:this message was deleted|you deleted this message|se eliminó este mensaje|"
    r"eliminaste este mensaje|este mensaje fue eliminado|mensaje eliminado|"
    r"esta mensagem foi apagada|você apagou esta mensagem|mensagem apagada)\.?$",
    re.IGNORECASE,
)
_YOU_DELETED_RE = re.compile(
    r"^(?:you deleted this message|eliminaste este mensaje|você apagou esta mensagem)", re.IGNORECASE
)
_EDITED_RE = re.compile(
    r"[  ]*‎?<[^<>\n]*(?:edited|edit[óo]|editad[oa]|editou|bearbeitet|modifié|modificato)[^<>\n]*>[  ]*$",
    re.IGNORECASE,
)
# "Voice call. 12 min", "Missed video call. Tap to call back": a short label,
# then an optional detail after a second LRM mark.
_CALL_RE = re.compile(
    r"^‎(?P<label>[^‎\n.]{0,30}?(?:call|llamada|chamada|anruf|appel|chiamata)[^‎\n.]{0,20}?)"
    r"\.?(?:\s*‎(?P<detail>[^\n]{0,60}))?$",
    re.IGNORECASE,
)
_MISSED_RE = re.compile(r"missed|perdida|silenced|silenciada|no answer|sin respuesta|rechazada|declined", re.IGNORECASE)
_MAPS_RE = re.compile(
    r"https?://(?:maps\.google\.[a-z.]+|www\.google\.[a-z.]+/maps|goo\.gl/maps|maps\.app\.goo\.gl|maps\.apple\.com)\S*",
    re.IGNORECASE,
)
_COORDS_RE = re.compile(r"[?&](?:q|ll)=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)")
_SYSTEM_HINTS = re.compile(
    r"end-to-end encrypted|cifrad[oa]s? de extremo a extremo|criptografia de ponta a ponta|"
    r"is a contact|es un contacto|é um contato|security code|código de seguridad|código de segurança|"
    r"created (?:this )?group|cre[óo] (?:el|este) grupo|added|añadió|agregó|removed|left$|salió|"
    r"changed (?:the|this|their)|cambió|joined using|se unió|disappearing messages|mensajes temporales|"
    r"blocked this|bloqueaste|desbloqueaste|unblocked|pinned a message|fijó un mensaje|"
    r"now an admin|business account|cuenta de empresa|message timer|"
    r"waiting for this message|esperando (?:este|el) mensaje",
    re.IGNORECASE,
)

MEDIA_TYPES: Dict[str, Tuple[str, str]] = {
    # extension: (kind, mime)
    "opus": ("voice", "audio/ogg"),
    "ogg": ("voice", "audio/ogg"),
    "oga": ("voice", "audio/ogg"),
    "m4a": ("audio", "audio/mp4"),
    "aac": ("audio", "audio/aac"),
    "mp3": ("audio", "audio/mpeg"),
    "wav": ("audio", "audio/wav"),
    "amr": ("audio", "audio/amr"),
    "flac": ("audio", "audio/flac"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    "png": ("image", "image/png"),
    "gif": ("image", "image/gif"),
    "webp": ("image", "image/webp"),
    "heic": ("image", "image/heic"),
    "avif": ("image", "image/avif"),
    "bmp": ("image", "image/bmp"),
    "mp4": ("video", "video/mp4"),
    "m4v": ("video", "video/mp4"),
    "mov": ("video", "video/quicktime"),
    "3gp": ("video", "video/3gpp"),
    "webm": ("video", "video/webm"),
    "was": ("lottie", "application/json"),
    "vcf": ("contact", "text/vcard"),
    "pdf": ("document", "application/pdf"),
}

SENDER_COLORS = [
    "#1f7aec", "#e5484d", "#2b9a66", "#c2410c", "#8b5cf6", "#0e9aa7",
    "#d6409f", "#a16207", "#3e63dd", "#12a594", "#e54666", "#6e56cf",
]


@dataclass
class Sender:
    id: str
    name: str
    count: int = 0
    color: str = ""


@dataclass
class MediaItem:
    name: str
    kind: str  # voice audio image sticker lottie video gif contact document
    mime: str
    size: int
    sha256: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    waveform: Optional[List[int]] = None
    animated: bool = False
    vcard: Optional[dict] = None
    referenced: bool = False
    block: str = ""  # id of the embedded data block (single-file mode)
    ref: str = ""  # what the HTML points at: "#block-id" or a relative path
    copied_as: str = ""  # file name inside media/ (folder mode)


@dataclass
class Chat:
    title: str
    source_name: str
    format: TranscriptFormat
    messages: List[Message]
    line_count: int
    senders: List[Sender]
    me: Optional[str]  # sender id shown on the right
    me_reason: str
    media: Dict[str, MediaItem]
    missing: List[Tuple[int, str]]
    unreferenced: List[str]
    omitted: Counter
    transcript_name: str
    transcript_bytes: bytes
    encoding: str
    warnings: List[str] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return len(self.senders) > 2

    def sender_by_name(self, name: Optional[str]) -> Optional[Sender]:
        if name is None:
            return None
        key = _clean(name)
        for s in self.senders:
            if _clean(s.name) == key:
                return s
        return None

    @property
    def first_timestamp(self) -> Optional[datetime]:
        return next((m.timestamp for m in self.messages if m.timestamp), None)

    @property
    def last_timestamp(self) -> Optional[datetime]:
        return next((m.timestamp for m in reversed(self.messages) if m.timestamp), None)


def _clean(text: str) -> str:
    return text.strip(BIDI_MARKS + " \t").casefold()


def _strip_marks(text: str) -> str:
    return text.strip(BIDI_MARKS + " \t\n")


def media_type(name: str) -> Tuple[str, str]:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    kind, mime = MEDIA_TYPES.get(ext, ("document", "application/octet-stream"))
    upper = name.upper()
    if kind == "image" and ("STICKER" in upper or upper.startswith("STK-")):
        kind = "sticker"
    elif kind == "video" and "-GIF-" in upper:
        kind = "gif"
    elif kind == "voice" and not ("AUDIO" in upper or upper.startswith("PTT-")) and ext != "opus":
        kind = "audio"
    return kind, mime


def _omitted_kind(what: str) -> str:
    what = what.lower()
    for kind, words in _OMITTED_KINDS:
        if any(w in what for w in words):
            return kind
    return "media"


def classify_message(msg: Message, resolve: Callable[[str], Optional[str]]) -> None:
    """Work out what a message is (text, photo, call...) from its text."""
    body = msg.body

    edited = _EDITED_RE.search(body)
    if edited:
        msg.edited = True
        body = body[: edited.start()] + body[edited.end():]

    if msg.sender is None:
        msg.kind = "system"
        msg.text = _strip_marks(body)
        return

    # Attachments, iOS style: "<attached: 00000012-PHOTO-2026-10-27-11-55-22.jpg>"
    for m in _IOS_ATTACH_RE.finditer(body):
        name = m.group("name").strip()
        found = resolve(name)
        if found or m.group("label").strip().lower() in ATTACH_LABELS:
            msg.attachment = found or normalize_name(name)
            msg.attachment_missing = found is None
            caption = body[: m.start()] + body[m.end():]
            _set_caption(msg, caption)
            return

    # Attachments, Android style: "IMG-20261027-WA0001.jpg (file attached)"
    first, _, after = body.partition("\n")
    m = _ANDROID_ATTACH_RE.match(first)
    if m:
        found = resolve(m.group("name"))
        if found or m.group("label").strip().lower() in ATTACH_LABELS:
            msg.attachment = found or normalize_name(m.group("name"))
            msg.attachment_missing = found is None
            _set_caption(msg, after)
            return
    bare = resolve(_strip_marks(body)) if "\n" not in body.strip() and "." in body else None
    if bare:
        msg.attachment = bare
        _set_caption(msg, "")
        return

    plain = _strip_marks(body)

    # Media WhatsApp left out of the export. On iOS the marker is the last
    # piece of text after an invisible LRM mark; anything before it is the
    # caption (or "Name.pdf • 3 pages" for documents).
    head, lrm, marker = body.rpartition("‎")
    m = _OMITTED_RE.match(_strip_marks(marker) if lrm else plain)
    if m:
        msg.kind = "omitted"
        msg.omitted = _omitted_kind(m.group("what"))
        msg.text = "\n".join(line.strip(BIDI_MARKS + " ") for line in head.split("\n")).strip() if lrm else ""
        return

    if _DELETED_RE.match(plain):
        msg.kind = "deleted"
        msg.text = plain
        return

    if body.startswith("‎") and _SYSTEM_HINTS.search(plain):
        msg.kind = "system"
        msg.text = plain
        return

    m = _CALL_RE.match(body)
    if m:
        msg.kind = "call"
        label = m.group("label").strip().rstrip(".")
        detail = (m.group("detail") or "").strip()
        msg.call = {
            "label": label,
            "detail": detail,
            "video": "video" in label.lower() or "vídeo" in label.lower(),
            "missed": bool(_MISSED_RE.search(label) or _MISSED_RE.search(detail)),
        }
        msg.text = plain
        return

    maps = _MAPS_RE.search(body)
    if maps and re.match(r"^‎?[^:\n]{1,40}:\s*https?://", body.lstrip()):
        url = maps.group(0)
        coords = _COORDS_RE.search(url)
        rest = _strip_marks(body[maps.end():])
        msg.kind = "location"
        msg.location = {
            "url": url,
            "coords": f"{coords.group(1)}, {coords.group(2)}" if coords else "",
            "label": rest,
        }
        msg.text = rest
        return

    if body.startswith("‎"):
        # Some other note written by WhatsApp itself (poll, view-once...).
        msg.kind = "notice"
        msg.text = "\n".join(line.strip(BIDI_MARKS) for line in body.split("\n")).strip()
        return

    msg.kind = "text"
    msg.text = body


def _set_caption(msg: Message, caption: str) -> None:
    lines = [line.strip(BIDI_MARKS + " ") for line in caption.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    # iOS puts document details before the attachment: "Report.pdf • 3 pages"
    if lines and "•" in lines[0] and msg.attachment and media_type(msg.attachment)[0] == "document":
        msg.doc_meta = lines.pop(0).split("•", 1)[1].strip(BIDI_MARKS + " ")
    msg.kind = "media"
    msg.text = "\n".join(lines)


def _decode_transcript(raw: bytes) -> Tuple[str, str]:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252 (not UTF-8: check special characters)"


PROBE_LIMIT = 300 * 1024 * 1024  # larger files are only hashed, in chunks


def _probe_media(item: MediaItem, source: ExportSource) -> None:
    digest = hashlib.sha256()
    with source.open(item.name) as stream:
        if item.kind == "document" or item.size > PROBE_LIMIT:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
            item.sha256 = digest.hexdigest()
            return
        data = stream.read()
    digest.update(data)
    item.sha256 = digest.hexdigest()
    if item.kind in ("image", "sticker"):
        size = probe.image_size(data)
        if size:
            item.width, item.height = size
        item.animated = probe.webp_is_animated(data)
    elif item.kind in ("video", "gif"):
        info = probe.mp4_info(data)
        if info:
            size, item.duration = info
            if size:
                item.width, item.height = size
    elif item.kind in ("voice", "audio"):
        info = probe.opus_info(data)
        if info:
            item.duration, item.waveform = info
    elif item.kind == "contact":
        item.vcard = probe.vcard_summary(data)


def _guess_me(chat_title: Optional[str], senders: List[Sender], messages: List[Message]) -> Tuple[Optional[str], str]:
    for m in messages:
        if m.sender and _YOU_DELETED_RE.match(_strip_marks(m.body)):
            for s in senders:
                if _clean(s.name) == _clean(m.sender):
                    return s.id, "author of a 'You deleted this message' notice"
    if chat_title and len(senders) == 2:
        others = [s for s in senders if _clean(s.name) != _clean(chat_title)]
        if len(others) == 1:
            return others[0].id, "the participant the chat is not named after"
    return None, ""


def build_chat(
    source: ExportSource,
    title: Optional[str] = None,
    me: Optional[str] = None,
    date_order: str = "auto",
) -> Chat:
    raw = source.read_transcript()
    text, encoding = _decode_transcript(raw)
    transcript: Transcript = parse_transcript(text, date_order)

    for msg in transcript.messages:
        classify_message(msg, source.resolve)

    # Only people who wrote something count as participants: on iOS, notices
    # such as "Messages are end-to-end encrypted" carry the chat's name.
    senders: Dict[str, Sender] = {}
    for msg in transcript.messages:
        if msg.sender is None or msg.kind == "system":
            continue
        key = _clean(msg.sender)
        if key not in senders:
            senders[key] = Sender(id=f"s{len(senders)}", name=_strip_marks(msg.sender))
        senders[key].count += 1
    sender_list = list(senders.values())
    for i, s in enumerate(sender_list):
        s.color = SENDER_COLORS[i % len(SENDER_COLORS)]

    guessed_title = source.guessed_title
    chat_title = title or guessed_title
    if not chat_title:
        if len(sender_list) == 2:
            chat_title = sender_list[1].name
        else:
            chat_title = "WhatsApp chat"

    warnings: List[str] = []
    if me:
        me_sender = senders.get(_clean(me))
        if me_sender is None:
            raise ValueError(
                f"--me {me!r} is not one of the participants: " + ", ".join(s.name for s in sender_list)
            )
        me_id, me_reason = me_sender.id, "given with --me"
    else:
        me_id, me_reason = _guess_me(guessed_title or title, sender_list, transcript.messages)
        if me_id is None:
            warnings.append(
                "could not tell which participant is you; every message is shown on the left. "
                "Use --me NAME (or the settings panel in the page) to choose."
            )

    media: Dict[str, MediaItem] = {}
    for name in source.media_names():
        kind, mime = media_type(name)
        media[name] = MediaItem(name=name, kind=kind, mime=mime, size=source.size(name))

    missing: List[Tuple[int, str]] = []
    omitted: Counter = Counter()
    for msg in transcript.messages:
        if msg.attachment:
            if msg.attachment_missing:
                missing.append((msg.index, msg.attachment))
            else:
                media[msg.attachment].referenced = True
        if msg.kind == "omitted":
            omitted[msg.omitted] += 1

    for item in media.values():
        _probe_media(item, source)

    if transcript.format.date_order_guessed:
        warnings.append(
            "every date in the chat has a day of 12 or less, so the date order was guessed "
            f"({transcript.format.date_order}); use --date-order if dates look wrong"
        )
    if source.duplicate_names:
        warnings.append("files with the same name in different folders were skipped: " + ", ".join(source.duplicate_names))
    if not encoding.startswith("utf"):
        warnings.append(f"the transcript is not UTF-8; read it as {encoding}")

    return Chat(
        title=chat_title,
        source_name=source.path.name,
        format=transcript.format,
        messages=transcript.messages,
        line_count=transcript.line_count,
        senders=sender_list,
        me=me_id,
        me_reason=me_reason,
        media=media,
        missing=missing,
        unreferenced=sorted(n for n, item in media.items() if not item.referenced),
        omitted=omitted,
        transcript_name=source.transcript_name,
        transcript_bytes=raw,
        encoding=encoding,
        warnings=warnings,
    )
