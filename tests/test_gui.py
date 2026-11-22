import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wa2html import gui, i18n, icon
from wa2html.convert import preview_export

from .helpers import IOS_CHAT, IOS_FILES, make_zip, png


def make_root():
    try:
        import tkinter as tk

        root = tk.Tk()
    except Exception:  # no Tk or no display (e.g. a Linux server without Xvfb)
        return None
    root.withdraw()
    return root


class Translations(unittest.TestCase):
    def test_every_language_is_complete(self):
        reference_page = set(i18n.STRINGS["en"])
        reference_app = set(i18n.app_text("en"))
        self.assertGreaterEqual(len(i18n.LANGUAGES), 6)
        for code in i18n.LANGUAGES:
            with self.subTest(code):
                self.assertEqual(set(i18n.STRINGS[code]), reference_page)
                self.assertEqual(set(i18n._DATA[code]["app"]), reference_app)
                for key in ("summary", "missing", "omitted", "in_folder"):
                    text = i18n.app_text(code)[key]
                    text.format(messages=1, period="p", attachments=2, n=3, folder="f")  # placeholders intact
                self.assertEqual(len(i18n._DATA[code]["date"]["months"]), 12)
                self.assertEqual(len(i18n._DATA[code]["date"]["weekdays"]), 7)

    def test_detect_language_from_environment(self):
        with mock.patch.object(gui.sys, "platform", "linux"), mock.patch.dict(os.environ, {"LANG": "fr_FR.UTF-8", "LC_ALL": ""}):
            self.assertEqual(gui.detect_language(), "fr")
        with mock.patch.object(gui.sys, "platform", "linux"), mock.patch.dict(os.environ, {"LANG": "ja_JP.UTF-8", "LC_ALL": ""}):
            with mock.patch("locale.getlocale", return_value=(None, None)):
                self.assertEqual(gui.detect_language(), "en")

    def test_short_path(self):
        long = Path("C:\\Users\\someone\\AppData\\Local\\Temp\\a\\very\\deep\\folder\\with\\chats")
        short = gui.short_path(long, 40)
        self.assertLessEqual(len(short), 40)
        self.assertTrue(short.startswith("C:\\Users\\…"))
        self.assertTrue(short.endswith("chats"))
        self.assertEqual(gui.short_path(Path("D:\\Downloads"), 40), "D:\\Downloads")

    def test_icon(self):
        data = icon.png(32)
        self.assertTrue(data.startswith(b"\x89PNG"))
        ico = icon.ico((32, 16))
        self.assertEqual(ico[:6], b"\x00\x00\x01\x00\x02\x00")


class Preview(unittest.TestCase):
    def test_preview_is_quick_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_zip(Path(tmp) / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)
            preview = preview_export(path)
        self.assertEqual(preview.title, "Bob")
        self.assertEqual(preview.participants, ["Alice", "Bob"])
        self.assertEqual(preview.me, "Alice")
        self.assertEqual(preview.missing, 1)
        self.assertEqual(preview.omitted, 2)


class Window(unittest.TestCase):
    # One Tk interpreter for all window tests: creating and destroying a Tk() per
    # test made the process crash (segfault) on macOS. Each test gets a Toplevel.
    tk_root = None

    @classmethod
    def setUpClass(cls):
        cls.tk_root = make_root()
        if cls.tk_root is None:
            raise unittest.SkipTest("no display available for Tk")

    @classmethod
    def tearDownClass(cls):
        if cls.tk_root is not None:
            cls.tk_root.destroy()
            cls.tk_root = None

    def new_window(self):
        import tkinter

        window = tkinter.Toplevel(self.tk_root)
        window.withdraw()
        return window

    def setUp(self):
        self.root = self.new_window()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = make_zip(self.tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)
        self.env = mock.patch.dict(os.environ, {"WA2HTML_CONFIG_DIR": str(self.tmp / "config")})
        self.env.start()

    def tearDown(self):
        import gc

        self.env.stop()
        # Cancel pending callbacks at the Tcl level only: their Python commands are
        # deleted by the window that registered them when it is destroyed.
        for job in self.tk_root.tk.call("after", "info"):
            self.tk_root.tk.call("after", "cancel", job)
        if self.root.winfo_exists():
            self.root.destroy()
        gc.collect()  # finalize this test's Tk objects here, on the main thread
        self._tmp.cleanup()

    def wait(self, condition, timeout=60):
        # The real event loop (see gui.run_until), never an update() loop.
        if not gui.run_until(self.root, condition, timeout):
            self.fail("timed out")

    def test_choose_then_create(self):
        app = gui.App(self.root, lang="es", popups=False)
        self.assertEqual(str(app.create_button["state"]), "disabled")
        self.assertEqual(app.input_name["text"], i18n.app_text("es")["no_file"])
        app.set_input(self.zip)
        self.wait(lambda: not app.busy)
        self.assertEqual(app.me, "Alice")
        self.assertEqual(list(app.me_box["values"]), ["Alice", "Bob"])
        self.assertEqual(app.output_name["text"], "WhatsApp Chat - Bob.html")
        self.assertIn("23 mensajes", app.summary["text"])
        app.me = "Bob"
        app.create()
        self.wait(lambda: app.outcome is not None)
        self.assertEqual(app.outcome.code, 0)
        self.assertTrue(app.outcome.verified)
        self.assertEqual(app.outcome.page, self.tmp / "WhatsApp Chat - Bob.html")
        self.assertTrue(any("Verified" in line for _, line in app.log_lines))
        self.assertEqual(app.status_label["text"], i18n.app_text("es")["ok"])
        self.assertEqual(str(app.open_button["state"]), "normal")
        # The next page would get a new name instead of replacing this one.
        self.assertEqual(app.output_name["text"], "WhatsApp Chat - Bob (2).html")
        page = app.outcome.page.read_text(encoding="utf-8")
        self.assertIn('"me":"s1"', page)  # Bob on the right

    def test_language_switch_keeps_state(self):
        app = gui.App(self.root, lang="en", popups=False)
        app.set_input(self.zip)
        self.wait(lambda: not app.busy)
        app.mode = "folder"
        app._refresh()
        for code in i18n.LANGUAGES:
            app.set_language(code)
            self.assertEqual(self.root.title(), i18n.app_text(code)["title"])
            self.assertEqual(app.input_name["text"], "WhatsApp Chat - Bob.zip")
            self.assertEqual(app.output_name["text"], "WhatsApp Chat - Bob (viewer)")
            self.assertEqual(app.mode_var.get(), "folder")
            self.assertEqual(app.me_box.get(), "Alice")
        self.assertFalse(gui.settings_path().exists())  # tests pass a language: nothing saved

    def test_language_choice_is_remembered(self):
        app = gui.App(self.root, popups=False)  # no language given: uses and saves the settings
        app.set_language("de" if app.lang != "de" else "it")
        saved = json.loads(gui.settings_path().read_text(encoding="utf-8"))["lang"]
        self.assertEqual(saved, app.lang)
        app.close()
        self.root.destroy()
        self.root = self.new_window()
        self.assertEqual(gui.App(self.root, popups=False).lang, saved)

    def test_completion_message(self):
        app = gui.App(self.root, lang="es", popups=False)
        app.set_input(self.zip)
        self.wait(lambda: not app.busy)
        app.create()
        self.wait(lambda: app.outcome is not None)
        title, text, ok = app.completion_message()
        t = i18n.app_text("es")
        self.assertTrue(ok)
        self.assertEqual(title, t["done_title"])
        self.assertIn("WhatsApp Chat - Bob.html", text)
        self.assertIn(t["done_checked"].format(messages="23", files="10"), text)
        self.assertIn(t["done_omitted"].format(n="2"), text)
        self.assertIn(t["done_missing_1"], text)  # singular for one file
        self.assertTrue(text.endswith(t["ask_open"]))
        # A failed run says so, with the reason.
        app.outcome = gui.Outcome(1, error="verification FAILED; keep using the original export")
        title, text, ok = app.completion_message()
        self.assertFalse(ok)
        self.assertEqual(title, t["fail_title"])
        self.assertIn("verification FAILED", text)

    def test_announce_shows_a_dialog(self):
        app = gui.App(self.root, lang="en")
        app.outcome = gui.Outcome(1, error="boom")
        with mock.patch("tkinter.messagebox.showerror") as showerror:
            app._announce()
        showerror.assert_called_once()
        self.assertIn("boom", showerror.call_args[0][1])

    def test_both_photos(self):
        theirs, mine = self.tmp / "bob.png", self.tmp / "me.png"
        theirs.write_bytes(png(6, 6))
        mine.write_bytes(png(7, 7))
        app = gui.App(self.root, lang="es", popups=False)
        t = i18n.app_text("es")
        self.assertEqual(app.photo_title["text"], t["photo_plain"])
        app.set_input(self.zip)
        self.wait(lambda: not app.busy)
        self.assertEqual(app.photo_title["text"], t["photo"].format(name="Bob"))
        self.assertEqual(app.my_photo_title["text"], t["my_photo"].format(name="Alice"))
        app.avatar = theirs
        app.set_my_avatar(mine)
        self.assertEqual(app.my_avatar_label["text"], "me.png")
        app.create()
        self.wait(lambda: app.outcome is not None)
        self.assertTrue(app.outcome.verified)
        page = app.outcome.page.read_text(encoding="utf-8")
        self.assertIn('.msg[data-s="s0"] .v-avatar:not(.music) { background: var(--my-avatar)', page)
        self.assertIn('.msg[data-s="s1"] .v-avatar:not(.music) { background: var(--chat-avatar)', page)
        self.assertFalse(gui.settings_path().exists())  # tests pass a language: nothing saved

    def test_owner_photo_is_remembered(self):
        mine = self.tmp / "me.png"
        mine.write_bytes(png(7, 7))
        app = gui.App(self.root, popups=False)
        app.set_my_avatar(mine)
        self.assertEqual(gui.load_settings()["my_avatar"], str(mine))
        self.assertEqual(gui.App(self.root, popups=False).my_avatar, mine)
        app.remove_my_avatar()
        self.assertNotIn("my_avatar", gui.load_settings())

    def test_tk_objects_are_finalized_on_the_main_thread(self):
        # Tk must only be used from the main thread; on macOS a font or variable
        # finalized by a garbage collection inside the worker thread froze the window.
        import gc
        import threading
        import tkinter
        import tkinter.font

        on_main = []

        def spy(original):
            def finalizer(obj):
                on_main.append(threading.current_thread() is threading.main_thread())
                original(obj)
            return finalizer

        with mock.patch.object(tkinter.font.Font, "__del__", spy(tkinter.font.Font.__del__)), \
                mock.patch.object(tkinter.Variable, "__del__", spy(tkinter.Variable.__del__)), \
                mock.patch.object(tkinter.Image, "__del__", spy(tkinter.Image.__del__)):
            app = gui.App(self.root, lang="en", popups=False)
            for code in i18n.LANGUAGES:  # switching language must not leave Tk objects behind
                app.set_language(code)
            # Garbage with Tk objects inside a reference cycle, like a closed window.
            other = tkinter.Toplevel(self.root)
            junk = [tkinter.StringVar(other), tkinter.font.Font(other, size=9), tkinter.PhotoImage(master=other)]
            junk.append(junk)
            other.destroy()
            del junk, other
            finished = threading.Event()

            def work():
                gc.collect()  # what the conversion's allocations trigger inside the worker
                finished.set()

            app._run_in_background(work)
            self.assertTrue(finished.wait(10))
            app._background_finished()
            gc.collect()
        self.assertTrue(on_main)
        self.assertTrue(all(on_main), "a Tk object was finalized outside the main thread")
        self.assertEqual(app._background, 0)

    def test_bad_input(self):
        app = gui.App(self.root, lang="en", popups=False)
        bogus = self.tmp / "notes.md"
        bogus.write_text("hello", encoding="utf-8")
        app.set_input(bogus)
        self.wait(lambda: not app.busy)
        self.assertIsNone(app.preview)
        self.assertEqual(str(app.create_button["state"]), "disabled")
        self.assertIn("WhatsApp export", app.status_label["text"])

    def test_selftest(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gui.selftest(self.zip, master=self.tk_root)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("gui selftest passed", out.getvalue())


if __name__ == "__main__":
    unittest.main()
