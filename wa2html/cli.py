"""Command line interface: ``wa2html CHAT.zip``."""

from __future__ import annotations

import argparse
import mimetypes
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import __version__
from .chat import Chat, build_chat
from .parser import TranscriptFormatError
from .render import RenderOptions, render
from .source import ExportError, ExportSource
from .verify import verify_page

SINGLE_FILE_WARN = 500 * 1024 * 1024


def _image_arg(path: Optional[str]) -> Optional[Tuple[bytes, str]]:
    if not path:
        return None
    file = Path(path)
    mime = mimetypes.guess_type(file.name)[0] or ""
    if not mime.startswith("image/"):
        raise SystemExit(f"error: {path} does not look like an image")
    return file.read_bytes(), mime


def default_output(source: Path, mode: str) -> Path:
    base = source.with_suffix("") if source.is_file() else source
    if mode == "folder":
        return base.parent / (base.name + " (viewer)")
    return base.parent / (base.name + ".html")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wa2html",
        description="Turn a WhatsApp chat export into a WhatsApp-style HTML page with "
        "playable voice notes, photos, stickers and videos. The export is only read, never changed.",
    )
    p.add_argument("input", help="the .zip exported by WhatsApp, the folder it was extracted to, or the chat .txt")
    p.add_argument("-o", "--output", help="output .html file (or folder, with --mode folder)")
    p.add_argument(
        "--mode",
        choices=("single", "folder"),
        default="single",
        help="single: one .html with everything inside (default). folder: index.html plus a media/ folder, "
        "better for very large chats",
    )
    p.add_argument("--check", action="store_true", help="only read the export and print the report; write nothing")
    p.add_argument("--force", action="store_true", help="overwrite the output if it already exists")
    p.add_argument(
        "--no-verify",
        action="store_true",
        help="skip re-reading the result to check that every file and message made it in",
    )
    g = p.add_argument_group("chat")
    g.add_argument("--me", metavar="NAME", help="your name as it appears in the chat (shown on the right)")
    g.add_argument("--title", help="chat title (default: taken from the file name)")
    g.add_argument(
        "--date-order",
        choices=("auto", "dmy", "mdy", "ymd"),
        default="auto",
        help="order of day, month and year in the transcript (default: detected)",
    )
    g = p.add_argument_group("appearance (all can also be changed later in the page)")
    g.add_argument("--lang", default="auto", help="interface language: auto, en or es (default: auto)")
    g.add_argument("--theme", choices=("auto", "light", "dark"), default="auto")
    g.add_argument("--time-format", choices=("auto", "12", "24"), default="auto")
    g.add_argument("--wallpaper", default="default", help="'default' or a CSS colour/gradient, e.g. '#dfe7ec'")
    g.add_argument("--wallpaper-image", metavar="IMAGE", help="an image to use as wallpaper")
    g.add_argument("--no-pattern", action="store_true", help="no doodle pattern over the wallpaper")
    g.add_argument("--avatar", metavar="IMAGE", help="a picture for the chat header")
    g.add_argument("--lottie-js", metavar="FILE", help="lottie-web build to embed for animated (.was) stickers")
    p.add_argument("--version", action="version", version=f"wa2html {__version__}")
    return p


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


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    source_path = Path(args.input)

    try:
        source = ExportSource(source_path)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with source:
        try:
            chat = build_chat(source, title=args.title, me=args.me, date_order=args.date_order)
        except (TranscriptFormatError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(f"wa2html {__version__}")
        for line in report(chat):
            print(line)
        for warning in chat.warnings:
            print(f"warning: {warning}")
        if args.check:
            return 0

        output = Path(args.output) if args.output else default_output(source_path, args.mode)
        target = output / "index.html" if args.mode == "folder" else output
        if target.exists() and not args.force:
            print(f"error: {target} already exists (use --force to overwrite)", file=sys.stderr)
            return 1
        if args.mode == "single":
            total = sum(item.size for item in chat.media.values())
            if total * 4 // 3 > SINGLE_FILE_WARN:
                print(
                    f"warning: the page will be about {total * 4 // 3 // (1024 * 1024):,} MB; browsers may be slow "
                    "to open it. Consider --mode folder."
                )

        options = RenderOptions(
            mode=args.mode,
            lang=args.lang,
            theme=args.theme,
            time_format=args.time_format,
            wallpaper=args.wallpaper,
            pattern=not args.no_pattern,
            wallpaper_image=_image_arg(args.wallpaper_image),
            avatar=_image_arg(args.avatar),
            lottie_js=args.lottie_js,
        )
        result = render(chat, source, output, options)

    for warning in result.warnings:
        print(f"warning: {warning}")
    if result.messages_rendered != len(chat.messages):  # pragma: no cover - safety net
        print(f"error: rendered {result.messages_rendered} of {len(chat.messages)} messages", file=sys.stderr)
        return 1
    size_mb = result.bytes_written / (1024 * 1024)
    extra = f" + {result.media_files:,} files in media/" if result.media_files else ""
    print(f"Written       {result.path} ({size_mb:,.1f} MB{extra})")
    if args.no_verify:
        return 0
    check = verify_page(chat, result.path, args.mode)
    if not check.ok:
        for problem in check.problems:
            print(f"error: {problem}", file=sys.stderr)
        print("error: verification FAILED; keep using the original export", file=sys.stderr)
        return 1
    print(
        f"Verified      all {len(chat.messages):,} messages, the original transcript and "
        f"{check.files_checked:,} files are in the result, identical to the export"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
