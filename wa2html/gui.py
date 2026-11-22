"""The wa2html window: choose an export, pick a few options, create the page.

Built with Tkinter (part of Python), so it adds no dependencies. The work
runs in a background thread; the window only talks to it through a queue.
The window speaks every language in ``wa2html/locales``; the choice is
remembered in a small settings file.
"""

from __future__ import annotations

import base64
import gc
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Tuple

from . import __version__, i18n, icon
from .convert import Job, Outcome, Preview, default_output, free_path, preview_export, read_image, run_job
from .render import RenderOptions

README_URL = "https://github.com/EnriqueWood/wa2html"
_WINDOWS_LANGIDS = {0x09: "en", 0x0A: "es", 0x16: "pt", 0x0C: "fr", 0x07: "de", 0x10: "it"}


# -- language and settings -------------------------------------------------------


def detect_language() -> str:
    """The system's language if wa2html speaks it, else English."""
    if sys.platform == "win32":
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            code = _WINDOWS_LANGIDS.get(langid & 0x3FF)
            if code in i18n.LANGUAGES:
                return code
        except Exception:
            pass
    names = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")]
    try:
        import locale

        names.append(locale.getlocale()[0] or "")
    except Exception:
        pass
    for name in names:
        code = name[:2].lower()
        if code in i18n.LANGUAGES:
            return code
    return "en"


def settings_path() -> Path:
    override = os.environ.get("WA2HTML_CONFIG_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home()) / "wa2html"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "wa2html"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "wa2html"
    return base / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass  # not being able to remember the language is not worth an error


def short_path(path: Path, limit: int = 60) -> str:
    """Shorten a long folder path in the middle: C:\\Users\\...\\Downloads\\chats."""
    text = str(path)
    if len(text) <= limit:
        return text
    sep = "\\" if "\\" in text else "/"
    parts = text.split(sep)
    head, tail = parts[:2], parts[2:]
    while tail and len(sep.join(head + ["…"] + tail)) > limit:
        tail = tail[1:]
    if not tail:
        return "…" + text[-(limit - 1):]
    return sep.join(head + ["…"] + tail)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def human_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def open_with_system(path: Path, reveal: bool = False) -> None:
    if sys.platform == "win32":
        if reveal:
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if reveal else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent if reveal else path)])


# -- the window --------------------------------------------------------------------


class App:
    def __init__(self, root, lang: Optional[str] = None, popups: bool = True):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.popups = popups  # the "page ready" dialog; off for automated runs
        self.started = 0.0
        self.persist = lang is None  # tests pass a language and must not touch the settings file
        self.lang = lang or load_settings().get("lang") or detect_language()
        if self.lang not in i18n.LANGUAGES:
            self.lang = "en"
        self.events: "queue.Queue[tuple]" = queue.Queue()

        # State that survives rebuilding the window in another language.
        self.input: Optional[Path] = None
        self.preview: Optional[Preview] = None
        self.preview_error: Optional[str] = None
        self.me: str = ""
        self.mode: str = "single"
        self.custom_output: Optional[Path] = None
        self.force_output = False
        self.avatar: Optional[Path] = None
        # The owner's photo is the same for every chat: remembered between runs.
        remembered = load_settings().get("my_avatar") if self.persist else None
        self.my_avatar: Optional[Path] = Path(remembered) if remembered and Path(remembered).is_file() else None
        self.busy = False
        self.outcome: Optional[Outcome] = None
        self.status: Tuple[str, bool, str] = ("", True, "")  # (text key, ok, extra)
        self.log_lines: list = []

        # Tk objects with a finalizer (fonts, variables, images) are created once and
        # kept for the life of the window. If they were dropped, Python's garbage
        # collector could finalize them in the worker thread, and Tk must only be used
        # from the main thread (on macOS that deadlocks the window).
        from tkinter import font as tkfont

        base = tkfont.nametofont("TkDefaultFont")
        self.heading_font = base.copy()
        self.heading_font.configure(size=base.cget("size") + 1, weight="bold")
        self.title_font = base.copy()
        self.title_font.configure(size=base.cget("size") + 6, weight="bold")
        self.mode_var = tk.StringVar(value=self.mode)
        self._background = 0  # worker threads running
        try:
            self._icon = tk.PhotoImage(data=base64.b64encode(icon.png(64)).decode("ascii"))
            root.iconphoto(True, self._icon)
        except Exception:  # cosmetic
            pass
        root.minsize(680, 600)
        self.body = None
        self._build()
        self._poll_job = root.after(100, self._poll)

    # -- building -----------------------------------------------------------

    def _build(self) -> None:
        tk = self.tk
        from tkinter import ttk

        if self.body is not None:
            self.body.destroy()
        self.t = i18n.app_text(self.lang)
        self.root.title(self.t["title"])

        # Wrap lengths are in pixels: scale them with the screen (Tk scaling is 1.33 at 100 %).
        try:
            scale = max(1.0, float(self.root.tk.call("tk", "scaling")) / (96 / 72))
        except Exception:
            scale = 1.0
        wide, narrow = int(640 * scale), int(430 * scale)

        heading, title_font = self.heading_font, self.title_font
        gray = "#5f6368"

        frame = ttk.Frame(self.root, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        self.body = frame

        row = 0
        top = ttk.Frame(frame)
        top.grid(row=row, column=0, columnspan=3, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="wa2html", font=title_font).grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=self.t["language"]).grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.lang_box = ttk.Combobox(top, state="readonly", width=12, values=[i18n.NAMES[c] for c in i18n.LANGUAGES])
        self.lang_box.set(i18n.NAMES[self.lang])
        self.lang_box.grid(row=0, column=2, sticky="e")
        self.lang_box.bind("<<ComboboxSelected>>", self._on_language)
        row += 1
        ttk.Label(frame, text=self.t["intro"], wraplength=wide, justify="left").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 14)
        )

        # 1. Exported chat
        row += 1
        ttk.Label(frame, text=self.t["step1"], font=heading).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.input_name = ttk.Label(frame, text="", wraplength=narrow)
        self.input_name.grid(row=row, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=2, rowspan=2, sticky="ne")
        ttk.Button(buttons, text=self.t["choose_zip"], command=self.choose_zip).pack(side="left")
        ttk.Button(buttons, text=self.t["choose_folder"], command=self.choose_folder).pack(side="left", padx=(6, 0))
        row += 1
        self.input_dir = ttk.Label(frame, text="", foreground=gray, wraplength=narrow)
        self.input_dir.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.summary = ttk.Label(frame, text="", foreground=gray, wraplength=wide)
        self.summary.grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1
        link = ttk.Label(frame, text=self.t["how_export"], foreground="#0b6bcb", cursor="hand2")
        link.grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 14))
        link.bind("<Button-1>", lambda _e: webbrowser.open(f"{README_URL}#{self.lang}"))

        # 2. Options
        row += 1
        ttk.Label(frame, text=self.t["step2"], font=heading).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        ttk.Label(frame, text=self.t["right"]).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))
        self.me_box = ttk.Combobox(frame, state="disabled", width=36)
        self.me_box.grid(row=row, column=1, columnspan=2, sticky="w", pady=3)
        self.me_box.bind("<<ComboboxSelected>>", self._on_me)
        row += 1
        # Photos: the contact's (header + their voice messages) and the owner's (their voice messages).
        self.photo_title = ttk.Label(frame, text="")
        self.photo_title.grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))
        self.avatar_label = ttk.Label(frame, text="")
        self.avatar_label.grid(row=row, column=1, sticky="w", pady=3)
        photo_buttons = ttk.Frame(frame)
        photo_buttons.grid(row=row, column=2, sticky="e")
        ttk.Button(photo_buttons, text=self.t["choose"], command=self.choose_avatar).pack(side="left")
        ttk.Button(photo_buttons, text=self.t["remove"], command=self.remove_avatar).pack(side="left", padx=(6, 0))
        row += 1
        self.my_photo_title = ttk.Label(frame, text="")
        self.my_photo_title.grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))
        self.my_avatar_label = ttk.Label(frame, text="")
        self.my_avatar_label.grid(row=row, column=1, sticky="w", pady=3)
        my_photo_buttons = ttk.Frame(frame)
        my_photo_buttons.grid(row=row, column=2, sticky="e")
        ttk.Button(my_photo_buttons, text=self.t["choose"], command=self.choose_my_avatar).pack(side="left")
        ttk.Button(my_photo_buttons, text=self.t["remove"], command=self.remove_my_avatar).pack(side="left", padx=(6, 0))
        row += 1
        ttk.Label(frame, text=self.t["photo_hint"], foreground=gray, wraplength=wide).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        row += 1
        ttk.Label(frame, text=self.t["save_as"]).grid(row=row, column=0, sticky="nw", pady=3, padx=(0, 12))
        self.mode_var.set(self.mode)
        modes = ttk.Frame(frame)
        modes.grid(row=row, column=1, columnspan=2, sticky="w", pady=3)
        for value in ("single", "folder"):
            ttk.Radiobutton(modes, text=self.t[value], value=value, variable=self.mode_var,
                            command=self._on_mode).pack(anchor="w")
        row += 1
        ttk.Label(frame, text=self.t["save_to"]).grid(row=row, column=0, sticky="nw", pady=3, padx=(0, 12))
        self.output_name = ttk.Label(frame, text="", wraplength=narrow)
        self.output_name.grid(row=row, column=1, sticky="w", pady=(3, 0))
        self.change_button = ttk.Button(frame, text=self.t["change"], command=self.choose_output)
        self.change_button.grid(row=row, column=2, sticky="ne", pady=3)
        row += 1
        self.output_dir = ttk.Label(frame, text="", foreground=gray, wraplength=narrow)
        self.output_dir.grid(row=row, column=1, sticky="w")

        # 3. Create
        row += 1
        ttk.Label(frame, text=self.t["step3"], font=heading).grid(row=row, column=0, columnspan=3, sticky="w", pady=(14, 0))
        row += 1
        actions = ttk.Frame(frame)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 6))
        actions.columnconfigure(1, weight=1)
        self.create_button = ttk.Button(actions, text=self.t["create"], command=self.create)
        self.create_button.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=10)
        self.open_button = ttk.Button(actions, text=self.t["open_page"], command=self.open_page)
        self.open_button.grid(row=0, column=2)
        self.folder_button = ttk.Button(actions, text=self.t["show_folder"], command=self.show_folder)
        self.folder_button.grid(row=0, column=3, padx=(6, 0))
        row += 1
        self.status_label = ttk.Label(frame, text="", wraplength=wide, font=heading)
        self.status_label.grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        ttk.Label(frame, text=self.t["details"], foreground=gray).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 2))
        row += 1
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=row, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=8, wrap="word", font="TkFixedFont", state="disabled",
                           relief="solid", borderwidth=1)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_configure("error", foreground="#c62828")
        self.log.tag_configure("warning", foreground="#a15c00")
        ttk.Label(frame, text=f"wa2html {__version__}", foreground="#888").grid(
            row=row + 1, column=0, columnspan=3, sticky="e", pady=(6, 0)
        )
        self._refresh()

    def _refresh(self) -> None:
        """Show the current state in the widgets (after a choice or a rebuild)."""
        t = self.t
        if self.input is None:
            self.input_name.configure(text=t["no_file"])
            self.input_dir.configure(text="")
        else:
            self.input_name.configure(text=self.input.name)
            self.input_dir.configure(text=t["in_folder"].format(folder=short_path(self.input.parent)))
        if self.busy and self.preview is None:
            self.summary.configure(text=t["reading"])
        elif self.preview is not None:
            p = self.preview
            period = f"{p.first:%Y-%m-%d} – {p.last:%Y-%m-%d}" if p.first and p.last else ""
            text = t["summary"].format(messages=f"{p.messages:,}", period=period, attachments=f"{p.attachments:,}")
            if p.missing:
                text += t["missing"].format(n=p.missing)
            if p.omitted:
                text += t["omitted"].format(n=p.omitted)
            self.summary.configure(text=text)
        else:
            self.summary.configure(text="")
        names = self.preview.participants if self.preview else []
        self.me_box.configure(values=names, state="readonly" if names else "disabled")
        self.me_box.set(self.me if self.me in names else "")
        contact = self.preview.title if self.preview else ""
        self.photo_title.configure(text=t["photo"].format(name=contact) if contact else t["photo_plain"])
        self.my_photo_title.configure(text=t["my_photo"].format(name=self.me) if self.me else t["my_photo_plain"])
        self.avatar_label.configure(text=self.avatar.name if self.avatar else t["none"])
        self.my_avatar_label.configure(text=self.my_avatar.name if self.my_avatar else t["none"])
        self.mode_var.set(self.mode)
        output = self.output_path()
        if output is None:
            self.output_name.configure(text="")
            self.output_dir.configure(text="")
        else:
            self.output_name.configure(text=output.name)
            self.output_dir.configure(text=t["in_folder"].format(folder=short_path(output.parent)))
        ready = self.preview is not None and not self.busy
        self.create_button.configure(state="normal" if ready else "disabled")
        self.change_button.configure(state="normal" if ready else "disabled")
        has_page = (not self.busy) and self.outcome is not None and self.outcome.page is not None and self.outcome.page.exists()
        self.open_button.configure(state="normal" if has_page else "disabled")
        self.folder_button.configure(state="normal" if has_page else "disabled")
        key, ok, extra = self.status
        text = (t[key] + (" " + extra if extra else "")) if key else ""
        self.status_label.configure(text=text, foreground="#1b7f3b" if ok else "#c62828")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for level, line in self.log_lines:
            self.log.insert("end", line + "\n", level)
        self.log.see("end")
        self.log.configure(state="disabled")
        # An idle indeterminate bar keeps showing its moving block on Windows: switch modes.
        if self.busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(40)  # a calm animation; very short intervals flood slow redraws
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def _on_language(self, _event=None) -> None:
        name = self.lang_box.get()
        code = next((c for c in i18n.LANGUAGES if i18n.NAMES[c] == name), "en")
        self.set_language(code)

    def set_language(self, code: str) -> None:
        if code == self.lang or code not in i18n.LANGUAGES:
            return
        self.lang = code
        if self.persist:
            settings = load_settings()
            settings["lang"] = code
            save_settings(settings)
        self._build()

    def _on_me(self, _event=None) -> None:
        self.me = self.me_box.get()
        self._refresh()  # "Your photo (name)" follows the choice

    def _on_mode(self) -> None:
        self.mode = self.mode_var.get()
        if self.custom_output is not None:  # a chosen file name does not fit the other mode
            self.custom_output = None
            self.force_output = False
        self._refresh()

    # -- background work ------------------------------------------------------

    def _run_in_background(self, work: Callable[[], None]) -> None:
        """Run `work` in a thread, with the garbage collector unable to touch Tk objects.

        Pending garbage is collected here, in the main thread, and everything that
        exists is frozen until the work ends, so a collection triggered inside the
        worker never finalizes a Tk object there (Tk must stay on the main thread).
        """
        if self._background == 0:
            gc.collect()
            gc.freeze()
        self._background += 1
        threading.Thread(target=work, daemon=True).start()

    def _background_finished(self) -> None:
        self._background = max(0, self._background - 1)
        if self._background == 0:
            gc.unfreeze()

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                getattr(self, "_on_" + event[0])(*event[1:])
        except queue.Empty:
            pass
        self._poll_job = self.root.after(100, self._poll)

    def close(self) -> None:
        """Stop the event polling (before destroying the root window)."""
        job = getattr(self, "_poll_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _on_log(self, level: str, text: str) -> None:
        prefix = {"error": "error: ", "warning": "warning: "}.get(level, "")
        line = prefix + text
        self.log_lines.append((level, line))
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n", level)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_preview(self, path: Path, preview: Optional[Preview], error: Optional[str]) -> None:
        self._background_finished()
        if path != self.input:
            return  # a newer choice replaced this one
        self.busy = False
        self.preview = preview
        if preview is None:
            self.status = ("cant_read", False, error or "")
        else:
            self.me = preview.me or (preview.participants[0] if preview.participants else "")
        self._refresh()

    def _on_done(self, outcome: Outcome) -> None:
        self._background_finished()
        self.busy = False
        self.outcome = outcome
        self.status = ("ok", True, "") if outcome.code == 0 and outcome.verified else ("failed", False, "")
        # The next page must not replace this one.
        self.custom_output = None
        self.force_output = False
        self._refresh()
        if self.popups:
            self.root.after(50, self._announce)

    def completion_message(self) -> Tuple[str, str, bool]:
        """(title, text, ok) of the dialog shown when the work ends."""
        t = self.t
        outcome = self.outcome
        elapsed = human_duration(time.time() - self.started) if self.started else ""
        if outcome is not None and outcome.code == 0 and outcome.verified and outcome.page is not None:
            lines = [outcome.page.name, human_size(outcome.size) + ("  ·  " + t["done_time"].format(elapsed=elapsed) if elapsed else ""), ""]
            lines.append(t["done_checked"].format(messages=f"{outcome.messages:,}", files=f"{outcome.files:,}"))
            for key, n in (("done_omitted", outcome.omitted), ("done_missing", outcome.missing)):
                if n == 1:
                    lines.append(t[key + "_1"])
                elif n:
                    lines.append(t[key].format(n=f"{n:,}"))
            lines += ["", t["ask_open"]]
            return t["done_title"], "\n".join(lines), True
        detail = outcome.error if outcome is not None and outcome.error else ""
        text = t["fail_body"] + ("\n\n" + detail if detail else "")
        return t["fail_title"], text, False

    def _announce(self) -> None:
        from tkinter import messagebox

        # Bring the window forward: the work may have finished while the user was elsewhere.
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass
        title, text, ok = self.completion_message()
        if ok:
            if messagebox.askyesno(title, text, icon="info", parent=self.root):
                self.open_page()
        else:
            messagebox.showerror(title, text, parent=self.root)

    # -- actions -------------------------------------------------------------

    def set_input(self, path: Path) -> None:
        self.input = Path(path)
        self.preview = None
        self.custom_output = None
        self.force_output = False
        self.outcome = None
        self.status = ("", True, "")
        self.log_lines = []
        self.busy = True
        self._refresh()

        def work(path=self.input):
            try:
                self.events.put(("preview", path, preview_export(path), None))
            except Exception as exc:  # shown in the window
                self.events.put(("preview", path, None, str(exc)))

        self._run_in_background(work)

    def choose_zip(self) -> None:
        from tkinter import filedialog

        name = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[(self.t["export_files"], "*.zip *.txt"), (self.t["all_files"], "*.*")],
        )
        if name:
            self.set_input(Path(name))

    def choose_folder(self) -> None:
        from tkinter import filedialog

        name = filedialog.askdirectory(parent=self.root, mustexist=True)
        if name:
            self.set_input(Path(name))

    def choose_avatar(self) -> None:
        from tkinter import filedialog

        name = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[(self.t["images"], "*.jpg *.jpeg *.png *.webp *.gif"), (self.t["all_files"], "*.*")],
        )
        if name:
            self.avatar = Path(name)
            self._refresh()

    def remove_avatar(self) -> None:
        self.avatar = None
        self._refresh()

    def _choose_image(self) -> Optional[Path]:
        from tkinter import filedialog

        name = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[(self.t["images"], "*.jpg *.jpeg *.png *.webp *.gif"), (self.t["all_files"], "*.*")],
        )
        return Path(name) if name else None

    def set_my_avatar(self, path: Optional[Path]) -> None:
        self.my_avatar = path
        if self.persist:
            settings = load_settings()
            if path is None:
                settings.pop("my_avatar", None)
            else:
                settings["my_avatar"] = str(path)
            save_settings(settings)
        self._refresh()

    def choose_my_avatar(self) -> None:
        path = self._choose_image()
        if path:
            self.set_my_avatar(path)

    def remove_my_avatar(self) -> None:
        self.set_my_avatar(None)

    def output_path(self) -> Optional[Path]:
        if self.custom_output is not None:
            return self.custom_output
        if self.input is None:
            return None
        return free_path(default_output(self.input, self.mode))

    def choose_output(self) -> None:
        from tkinter import filedialog

        current = self.output_path()
        if current is None:
            return
        if self.mode == "single":
            name = filedialog.asksaveasfilename(
                parent=self.root,
                initialdir=str(current.parent),
                initialfile=current.name,
                defaultextension=".html",
                filetypes=[("HTML", "*.html")],
            )
            if name:
                self.custom_output = Path(name)
                # The save dialog already asked before replacing an existing file.
                self.force_output = self.custom_output.exists()
        else:
            name = filedialog.askdirectory(parent=self.root, initialdir=str(current.parent))
            if name:
                self.custom_output = free_path(Path(name) / current.name)
                self.force_output = False
        self._refresh()

    def create(self) -> None:
        if self.busy or self.input is None or self.preview is None:
            return
        from tkinter import messagebox

        try:
            avatar = read_image(str(self.avatar)) if self.avatar else None
            my_avatar = read_image(str(self.my_avatar)) if self.my_avatar else None
        except (ValueError, OSError) as exc:
            messagebox.showerror(self.t["error"], str(exc), parent=self.root)
            return
        job = Job(
            input=self.input,
            output=self.output_path(),
            mode=self.mode,
            force=self.force_output,
            me=self.me or None,
            options=RenderOptions(avatar=avatar, my_avatar=my_avatar),
        )
        self.busy = True
        self.outcome = None
        self.log_lines = []
        self.status = ("working", True, "")
        self.started = time.time()
        self._refresh()

        def work():
            try:
                outcome = run_job(job, lambda level, text: self.events.put(("log", level, text)))
            except BaseException as exc:  # unexpected (even MemoryError): report it instead of losing it
                message = f"{type(exc).__name__}: {exc}"
                self.events.put(("log", "error", message))
                outcome = Outcome(1, error=message)
            self.events.put(("done", outcome))

        self._run_in_background(work)

    def open_page(self) -> None:
        if self.outcome and self.outcome.page:
            open_with_system(self.outcome.page)

    def show_folder(self) -> None:
        if self.outcome and self.outcome.page:
            open_with_system(self.outcome.page, reveal=True)


# -- entry points ------------------------------------------------------------------


def _make_root():
    """A Tk root window, or None when no window can be shown here."""
    try:
        import tkinter as tk
    except ImportError:
        return None
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]  # sharp text
        except Exception:
            pass
    try:
        return tk.Tk()
    except tk.TclError:  # no display
        return None


def open_window(initial: Optional[Path] = None) -> Optional[int]:
    """Show the window until it is closed. None if no window can be shown."""
    root = _make_root()
    if root is None:
        return None
    app = App(root)
    if initial is not None:
        app.set_input(initial)
    root.mainloop()
    return 0


def main(argv: Optional[list] = None) -> int:
    """Entry point of ``wa2html-gui`` and of the Windows window-only executable."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["--gui-selftest"] and len(args) > 1:
        return selftest(Path(args[1]))
    initial = next((Path(a) for a in args if not a.startswith("-")), None)
    code = open_window(initial)
    if code is None:
        if sys.stderr is not None:
            print("wa2html: no window can be opened here; use the wa2html command instead.", file=sys.stderr)
        return 1
    return code


def run_until(root, condition: Callable[[], bool], timeout: float) -> bool:
    """Run the real event loop until `condition()` is true or `timeout` seconds pass.

    For automated runs (self-test, tests). It uses mainloop() like the real program
    instead of looping on update(): update() means "process events until none are
    left", which never ends on macOS while the progress bar keeps scheduling redraws.
    """
    deadline = time.time() + timeout
    met = [False]

    def check() -> None:
        if condition():
            met[0] = True
            root.quit()
        elif time.time() > deadline:
            root.quit()
        else:
            root.after(25, check)

    root.after(0, check)
    root.mainloop()
    return met[0]


def selftest(export: Path, timeout: float = 300.0, master=None) -> int:
    """Drive the window without a person: choose `export`, create the page, check it.

    Used by the release workflow to make sure each executable can show its
    window (Tk is bundled) and convert through it. The result is the exit
    code (the window-only Windows program has no console to print to).
    `master`: an existing Tk root to open the window in (tests), so the process
    keeps a single Tcl interpreter; creating and destroying several crashes
    Tk on macOS.
    """
    def say(text: str) -> None:
        if sys.stdout is not None:
            print(text)

    if master is not None:
        import tkinter

        root = tkinter.Toplevel(master)
    else:
        root = _make_root()
    if root is None:
        say("gui selftest: no window can be opened (no display or no Tk)")
        return 1
    try:
        app = App(root, lang="en", popups=False)

        def wait(condition: Callable[[], bool]) -> bool:
            return run_until(root, condition, timeout)

        for code in i18n.LANGUAGES:  # every translation must build the window
            app.set_language(code)
        app.set_language("en")
        app.set_input(export)
        if not wait(lambda: not app.busy):
            say("gui selftest: reading the export timed out")
            return 1
        if app.preview is None:
            say("gui selftest: the export could not be read")
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            app.custom_output = Path(tmp) / "selftest.html"
            app.create()
            if not wait(lambda: app.outcome is not None):
                say("gui selftest: creating the page timed out")
                return 1
            say("\n".join(line for _, line in app.log_lines))
            ok = app.outcome.code == 0 and app.outcome.verified and (Path(tmp) / "selftest.html").exists()
        say("gui selftest passed" if ok else "gui selftest FAILED")
        app.close()
        return 0 if ok else 1
    finally:
        root.destroy()
