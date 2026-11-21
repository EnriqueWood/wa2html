import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wa2html import gui, i18n, icon
from wa2html.convert import preview_export

from .helpers import IOS_CHAT, IOS_FILES, make_zip


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
    def setUp(self):
        self.root = make_root()
        if self.root is None:
            self.skipTest("no display available for Tk")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = make_zip(self.tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)
        self.env = mock.patch.dict(os.environ, {"WA2HTML_CONFIG_DIR": str(self.tmp / "config")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.root.destroy()
        self._tmp.cleanup()

    def wait(self, condition, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if condition():
                return
            time.sleep(0.02)
        self.fail("timed out")

    def test_choose_then_create(self):
        app = gui.App(self.root, lang="es")
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
        app = gui.App(self.root, lang="en")
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
        app = gui.App(self.root)  # no language given: uses and saves the settings
        app.set_language("de" if app.lang != "de" else "it")
        saved = json.loads(gui.settings_path().read_text(encoding="utf-8"))["lang"]
        self.assertEqual(saved, app.lang)
        self.root.destroy()
        self.root = make_root()
        self.assertEqual(gui.App(self.root).lang, saved)

    def test_bad_input(self):
        app = gui.App(self.root, lang="en")
        bogus = self.tmp / "notes.md"
        bogus.write_text("hello", encoding="utf-8")
        app.set_input(bogus)
        self.wait(lambda: not app.busy)
        self.assertIsNone(app.preview)
        self.assertEqual(str(app.create_button["state"]), "disabled")
        self.assertIn("WhatsApp export", app.status_label["text"])

    def test_selftest(self):
        self.root.destroy()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gui.selftest(self.zip)
        self.root = make_root()  # for tearDown
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("gui selftest passed", out.getvalue())


if __name__ == "__main__":
    unittest.main()
