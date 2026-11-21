"""The conversion itself, shared by the command line and the window.

Progress and results are reported through a ``log(level, text)`` callback,
with level "info", "warning" or "error", so each front end shows them its own
way.
"""

from __future__ import annotations

import mimetypes
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import __version__
from .chat import Chat, build_chat
from .parser import TranscriptFormatError
from .render import RenderOptions, render
from .source import ExportError, ExportSource
from .verify import verify_page

SINGLE_FILE_WARN = 500 * 1024 * 1024

Log = Callable[[str, str], None]


def read_image(path: Optional[str]) -> Optional[Tuple[bytes, str]]:
    """Read an image given as an option. Raises ValueError for non-images."""
    if not path:
        return None
    file = Path(path)
    mime = mimetypes.guess_type(file.name)[0] or ""
    if not mime.startswith("image/"):
        raise ValueError(f"{path} does not look like an image")
    return file.read_bytes(), mime


def default_output(source: Path, mode: str) -> Path:
    base = source.with_suffix("") if source.is_file() else source
    if mode == "folder":
        return base.parent / (base.name + " (viewer)")
    return base.parent / (base.name + ".html")


def free_path(path: Path) -> Path:
    """`path`, or "name (2).ext", "name (3).ext"... if it is taken."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def report(chat: Chat) -> List[str]:
    lines = []
    lines.append(f"Source        {chat.source_name}")
    lines.append(f"Transcript    {chat.transcript_name}: {chat.line_count:,} lines, {chat.format.describe()}")
    kinds = Counter(m.kind for m in chat.messages)
    real = len(chat.messages) - kinds.get("system", 0)
    lines.append(
        f"Messages      {real:,} (+{kinds.get('system', 0)} WhatsApp notices); every line of the transcript is accounted for"
    )
    if chat.first_timestamp and chat.last_timestamp:
        lines.append(f"Period        {chat.first_timestamp:%Y-%m-%d %H:%M} -> {chat.last_timestamp:%Y-%m-%d %H:%M}")
    me = next((s.name for s in chat.senders if s.id == chat.me), None)
    people = ", ".join(f"{s.name} ({s.count:,})" for s in chat.senders)
    lines.append(f"Participants  {people}")
    lines.append(f"Shown right   {me or 'nobody'}" + (f"  [{chat.me_reason}]" if me else ""))
    by_kind = Counter(item.kind for item in chat.media.values())
    referenced = sum(1 for m in chat.messages if m.attachment)
    lines.append(
        f"Attachments   {referenced:,} mentioned, {referenced - len(chat.missing):,} found, {len(chat.missing):,} missing"
    )
    if by_kind:
        lines.append("              in the export: " + ", ".join(f"{n:,} {k}" for k, n in by_kind.most_common()))
    if chat.omitted:
        lines.append(
            "Not exported  " + ", ".join(f"{n:,} {k}" for k, n in chat.omitted.most_common())
            + "  (WhatsApp wrote 'omitted': the file was not on the phone when exporting)"
        )
    if chat.unreferenced:
        lines.append(f"Extra files   {_plural(len(chat.unreferenced), 'file')} in the export that no message mentions (shown at the end)")
    for _, name in chat.missing[:20]:
        lines.append(f"  missing: {name}")
    if len(chat.missing) > 20:
        lines.append(f"  ... and {len(chat.missing) - 20} more")
    return lines


# -- quick look (for the window) ----------------------------------------------


@dataclass
class Preview:
    title: str
    participants: List[str]
    me: Optional[str]
    messages: int
    first: Optional[datetime]
    last: Optional[datetime]
    attachments: int
    missing: int
    omitted: int


def preview_export(path: Path) -> Preview:
    """Read only the transcript and the file list: fast even for big exports."""
    with ExportSource(path) as source:
        chat = build_chat(source, probe_media=False)
    me = next((s.name for s in chat.senders if s.id == chat.me), None)
    return Preview(
        title=chat.title,
        participants=[s.name for s in chat.senders],
        me=me,
        messages=sum(1 for m in chat.messages if m.kind != "system"),
        first=chat.first_timestamp,
        last=chat.last_timestamp,
        attachments=sum(1 for m in chat.messages if m.attachment),
        missing=len(chat.missing),
        omitted=sum(chat.omitted.values()),
    )


# -- the conversion -----------------------------------------------------------


@dataclass
class Job:
    input: Path
    output: Optional[Path] = None
    mode: str = "single"
    check_only: bool = False
    force: bool = False
    verify: bool = True
    me: Optional[str] = None
    title: Optional[str] = None
    date_order: str = "auto"
    options: RenderOptions = field(default_factory=RenderOptions)


@dataclass
class Outcome:
    code: int  # 0 ok, 1 failed, 2 unreadable input
    page: Optional[Path] = None
    verified: bool = False


def run_job(job: Job, log: Log) -> Outcome:
    try:
        source = ExportSource(job.input)
    except ExportError as exc:
        log("error", str(exc))
        return Outcome(2)

    with source:
        try:
            chat = build_chat(source, title=job.title, me=job.me, date_order=job.date_order)
        except (TranscriptFormatError, ValueError) as exc:
            log("error", str(exc))
            return Outcome(2)

        log("info", f"wa2html {__version__}")
        for line in report(chat):
            log("info", line)
        for warning in chat.warnings:
            log("warning", warning)
        if job.check_only:
            return Outcome(0)

        if job.output:
            output = job.output
        else:
            output = default_output(job.input, job.mode)
            if not job.force:
                output = free_path(output)  # never overwrite: "name (2).html"
        target = output / "index.html" if job.mode == "folder" else output
        if target.exists() and not job.force:
            log("error", f"{target} already exists (use --force to overwrite)")
            return Outcome(1)
        if job.mode == "single":
            total = sum(item.size for item in chat.media.values())
            if total * 4 // 3 > SINGLE_FILE_WARN:
                log(
                    "warning",
                    f"the page will be about {total * 4 // 3 // (1024 * 1024):,} MB; browsers may be slow "
                    "to open it. Consider --mode folder.",
                )

        job.options.mode = job.mode
        result = render(chat, source, output, job.options)

    for warning in result.warnings:
        log("warning", warning)
    if result.messages_rendered != len(chat.messages):  # pragma: no cover - safety net
        log("error", f"rendered {result.messages_rendered} of {len(chat.messages)} messages")
        return Outcome(1, result.path)
    size_mb = result.bytes_written / (1024 * 1024)
    extra = f" + {result.media_files:,} files in media/" if result.media_files else ""
    log("info", f"Written       {result.path} ({size_mb:,.1f} MB{extra})")
    if not job.verify:
        return Outcome(0, result.path)
    check = verify_page(chat, result.path, job.mode)
    if not check.ok:
        for problem in check.problems:
            log("error", problem)
        log("error", "verification FAILED; keep using the original export")
        return Outcome(1, result.path)
    log(
        "info",
        f"Verified      all {len(chat.messages):,} messages, the original transcript and "
        f"{check.files_checked:,} files are in the result, identical to the export",
    )
    return Outcome(0, result.path, verified=True)
