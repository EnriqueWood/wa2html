"""Command line interface: ``wa2html CHAT.zip``.

Without arguments the standalone executables open the window instead
(see wa2html.gui); so does ``wa2html --gui``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .convert import Job, default_output, free_path, read_image, report, run_job  # noqa: F401 (re-exported)
from .render import RenderOptions

DRAG_AND_DROP_HELP = """\
This is the command-line version of wa2html. For the window, download
wa2html-windows-x64.exe from https://github.com/EnriqueWood/wa2html/releases/latest

Esta es la version de linea de comandos de wa2html. Para la ventana, descarga
wa2html-windows-x64.exe desde https://github.com/EnriqueWood/wa2html/releases/latest

You can also drag the .zip exported from WhatsApp onto this program: the page
is saved next to the .zip. All options: run it with --help in a terminal.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wa2html",
        description="Turn a WhatsApp chat export into a WhatsApp-style HTML page with "
        "playable voice notes, photos, stickers and videos. The export is only read, never changed. "
        "Run with --gui (or, for the downloadable programs, without arguments) to use the window.",
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
    p.add_argument("--gui", action="store_true", help="open the window (optionally with INPUT already chosen)")
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
    g.add_argument(
        "--lang",
        default="auto",
        help="default language of the page: auto (the reader's browser), en, es, pt, fr, de or it",
    )
    g.add_argument("--theme", choices=("auto", "light", "dark"), default="auto")
    g.add_argument("--time-format", choices=("auto", "12", "24"), default="auto")
    g.add_argument("--wallpaper", default="default", help="'default' or a CSS colour/gradient, e.g. '#dfe7ec'")
    g.add_argument("--wallpaper-image", metavar="IMAGE", help="an image to use as wallpaper")
    g.add_argument("--no-pattern", action="store_true", help="no doodle pattern over the wallpaper")
    g.add_argument("--avatar", metavar="IMAGE", help="the contact's picture: chat header and their voice messages")
    g.add_argument("--my-avatar", metavar="IMAGE", help="your own picture, for your voice messages")
    g.add_argument("--lottie-js", metavar="FILE", help="lottie-web build to embed for animated (.was) stickers")
    p.add_argument("--version", action="version", version=f"wa2html {__version__}")
    return p


def launched_by_double_click() -> bool:
    """True when Windows opened a console just for this program.

    That happens when the .exe is double-clicked or a file is dropped on it.
    A console opened by a shell also lists the shell process.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    try:
        if not sys.stdin.isatty():
            return False
        import ctypes

        processes = (ctypes.c_uint * 8)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(processes, 8)  # type: ignore[attr-defined]
        # A one-file PyInstaller program runs as two processes: bootloader and Python.
        return 0 < count <= 2
    except Exception:  # pragma: no cover - best effort only
        return False


def _hide_own_console() -> None:
    """Hide the console Windows opened for us (never a terminal the user opened)."""
    try:
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()  # type: ignore[attr-defined]
        if window:
            ctypes.windll.user32.ShowWindow(window, 0)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - cosmetic
        pass


def _pause() -> None:
    try:
        input("\nPress Enter to close this window / Presiona Enter para cerrar esta ventana...")
    except (EOFError, KeyboardInterrupt):
        pass


def _print_log(level: str, text: str) -> None:
    if level == "error":
        print(f"error: {text}", file=sys.stderr)
    elif level == "warning":
        print(f"warning: {text}")
    else:
        print(text)


def main(argv: Optional[Sequence[str]] = None, allow_window: bool = True) -> int:
    """Run the command line.

    `allow_window=False` (the Windows command-line executable) only opens the
    window when asked with --gui; the other executables open it when started
    without arguments, e.g. by a double-click.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args_list = sys.argv[1:] if argv is None else [str(a) for a in argv]

    if args_list[:1] == ["--gui-selftest"]:  # used by the release workflow on each executable
        from .gui import selftest

        return selftest(Path(args_list[1]))

    double_click = launched_by_double_click()
    frozen = getattr(sys, "frozen", False)
    want_gui = "--gui" in args_list or (
        allow_window and ((double_click and len(args_list) <= 1) or (frozen and not args_list))
    )
    if want_gui:
        from .gui import open_window

        initial = next((Path(a) for a in args_list if a != "--gui"), None)
        if double_click:
            _hide_own_console()
        code = open_window(initial)
        if code is not None:
            return code
        # No window possible (no display or no Tk): carry on as a console program.

    if double_click and not args_list:
        print(DRAG_AND_DROP_HELP)
        _pause()
        return 0
    try:
        code = run([a for a in args_list if a != "--gui"])
    except SystemExit as exc:  # argparse errors, --help, --version
        code = exc.code if isinstance(exc.code, int) else 1
    if double_click:
        _pause()
    return code


def run(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        options = RenderOptions(
            lang=args.lang,
            theme=args.theme,
            time_format=args.time_format,
            wallpaper=args.wallpaper,
            pattern=not args.no_pattern,
            wallpaper_image=read_image(args.wallpaper_image),
            avatar=read_image(args.avatar),
            my_avatar=read_image(args.my_avatar),
            lottie_js=args.lottie_js,
        )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    job = Job(
        input=Path(args.input),
        output=Path(args.output) if args.output else None,
        mode=args.mode,
        check_only=args.check,
        force=args.force,
        verify=not args.no_verify,
        me=args.me,
        title=args.title,
        date_order=args.date_order,
        options=options,
    )
    return run_job(job, _print_log).code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
