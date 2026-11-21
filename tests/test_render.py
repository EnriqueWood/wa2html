import base64
import contextlib
import io
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from wa2html import cli
from wa2html.chat import build_chat
from wa2html.render import RenderOptions, format_text, is_emoji_only, render
from wa2html.source import ExportSource
from wa2html.verify import verify_page

from .helpers import IOS_CHAT, IOS_FILES, make_zip


class PageScanner(HTMLParser):
    """Collects what the tests need from a generated page."""

    def __init__(self):
        super().__init__()
        self.messages = 0
        self.notices = 0
        self.blocks = {}
        self._block = None
        self.sources = []
        self.texts = []
        self._text_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "msg" in classes and a.get("id", "").startswith("m"):
            self.messages += 1
        if "sys" in classes and a.get("id", "").startswith("m"):
            self.notices += 1
        if tag == "script" and a.get("type") == "application/octet-stream":
            self._block = a["id"]
            self.blocks[self._block] = [a.get("data-mime"), ""]
        for key in ("src", "href"):
            if key in a:
                self.sources.append((tag, key, a[key]))
        if self._text_depth:
            self._text_depth += 1
        elif "text" in classes:
            self._text_depth = 1
            self.texts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._block = None
        if self._text_depth:
            self._text_depth -= 1

    def handle_data(self, data):
        if self._block:
            self.blocks[self._block][1] += data
        elif self._text_depth:
            self.texts[-1] += data


class Formatting(unittest.TestCase):
    def test_whatsapp_styles_and_links(self):
        out = format_text("*bold* _it_ ~gone~ `x` https://example.org/a_b_c")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>it</em>", out)
        self.assertIn("<s>gone</s>", out)
        self.assertIn('href="https://example.org/a_b_c"', out)
        self.assertNotIn("<em>b</em>", out)  # underscores inside links are not italics

    def test_escaping(self):
        self.assertEqual(format_text("<b>x</b> & y"), "&lt;b&gt;x&lt;/b&gt; &amp; y")
        out = format_text('see https://x.org/?a="1"><script>')
        self.assertNotIn("<script>", out)

    def test_code_block(self):
        self.assertIn('<code class="block">a *b*</code>', format_text("```a *b*```"))

    def test_emoji_only(self):
        self.assertTrue(is_emoji_only("😂😂"))
        self.assertTrue(is_emoji_only("👨‍👩‍👧"))
        self.assertTrue(is_emoji_only("🇨🇱"))
        self.assertFalse(is_emoji_only("😂 ok"))
        self.assertFalse(is_emoji_only("😂😂😂😂"))


class RenderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = make_zip(self.tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, mode="single"):
        with ExportSource(self.zip) as source:
            chat = build_chat(source)
            out = self.tmp / ("page.html" if mode == "single" else "viewer")
            result = render(chat, source, out, RenderOptions(mode=mode))
        page = result.path.read_text(encoding="utf-8")
        scanner = PageScanner()
        scanner.feed(page)
        return chat, result, page, scanner

    def test_every_message_is_rendered(self):
        chat, result, page, scan = self.build()
        self.assertEqual(result.messages_rendered, len(chat.messages))
        system = sum(1 for m in chat.messages if m.kind == "system")
        self.assertEqual(scan.notices, system)
        self.assertEqual(scan.messages, len(chat.messages) - system)

    def test_text_survives(self):
        chat, _, _, scan = self.build()
        rendered = "\n".join(scan.texts)
        for msg in chat.messages:
            if msg.kind == "text" and msg.text.strip():
                for line in msg.text.split("\n"):
                    plain = re.sub(r"[*_~`]", "", line)
                    self.assertIn(plain, re.sub(r"[*_~`]", "", rendered))

    def test_media_is_embedded_byte_for_byte(self):
        chat, _, page, scan = self.build()
        embedded = {base64.b64decode(data) for mime, data in scan.blocks.values()}
        for name, data in IOS_FILES.items():
            if not name.endswith(".was"):
                self.assertIn(data, embedded, name)
        original = base64.b64decode(scan.blocks["wa-transcript"][1])
        self.assertEqual(original, IOS_CHAT.encode("utf-8"))
        pdf_block = next(mime for mime, data in scan.blocks.values() if base64.b64decode(data) == IOS_FILES["00000007-report.pdf"])
        self.assertEqual(pdf_block, "application/octet-stream")
        self.assertIn('"layers":[]', page)  # the .was sticker's animation

    def test_no_remote_resources(self):
        _, _, page, scan = self.build()
        for tag, key, value in scan.sources:
            if tag != "a":
                self.assertFalse(value.startswith(("http:", "https:", "//")), (tag, value))
        self.assertIn("Content-Security-Policy", page)

    def test_lottie_player_is_bundled(self):
        _, result, page, _ = self.build()
        self.assertIn("lottie-web 5.12.2", page)
        self.assertIn("data-lottie=", page)
        self.assertEqual(result.warnings, [])

    def test_warns_without_lottie_player(self):
        with mock.patch("wa2html.render.VENDOR_LOTTIE", self.tmp / "missing.js"):
            _, result, page, _ = self.build()
        self.assertNotIn("lottie-web 5.12.2", page)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("animated sticker", result.warnings[0])

    def test_verification_catches_damage(self):
        with ExportSource(self.zip) as source:
            chat = build_chat(source)
            page = self.tmp / "page.html"
            render(chat, source, page, RenderOptions())
        self.assertTrue(verify_page(chat, page, "single").ok)
        text = page.read_text(encoding="utf-8")
        audio = chat.media["00000001-AUDIO-2025-01-03-09-14-00.opus"]
        damaged = re.sub(rf'(id="{audio.block}" data-mime="[^"]*">)(....)', r"\1AAAA", text, count=1)
        self.assertNotEqual(damaged, text)
        page.write_text(damaged, encoding="utf-8")
        problems = verify_page(chat, page, "single").problems
        self.assertEqual(problems, ["00000001-AUDIO-2025-01-03-09-14-00.opus: embedded copy differs from the original"])

    def test_folder_mode(self):
        chat, result, page, scan = self.build(mode="folder")
        media = sorted(p.name for p in (self.tmp / "viewer" / "media").iterdir())
        self.assertEqual(media, sorted(IOS_FILES))  # a complete copy of the export's files
        self.assertEqual(
            (self.tmp / "viewer" / "media" / "00000003-PHOTO-2025-01-03-09-16-00.png").read_bytes(),
            IOS_FILES["00000003-PHOTO-2025-01-03-09-16-00.png"],
        )
        self.assertIn('data-src="media/00000003-PHOTO-2025-01-03-09-16-00.png"', page)
        self.assertTrue(verify_page(chat, result.path, "folder").ok)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = make_zip(self.tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_check_writes_nothing(self):
        code, out = self.run_cli(self.zip, "--check")
        self.assertEqual(code, 0)
        self.assertIn("1 missing", out)
        self.assertFalse((self.tmp / "WhatsApp Chat - Bob.html").exists())

    def test_default_output_and_no_overwrite(self):
        code, out = self.run_cli(self.zip)
        self.assertEqual(code, 0, out)
        self.assertIn("Verified", out)
        page = self.tmp / "WhatsApp Chat - Bob.html"
        self.assertTrue(page.exists())
        code, out = self.run_cli(self.zip)
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        code, _ = self.run_cli(self.zip, "--force", "--me", "Bob", "--theme", "dark")
        self.assertEqual(code, 0)

    def test_bad_input(self):
        bogus = self.tmp / "notes.md"
        bogus.write_text("hello", encoding="utf-8")
        code, out = self.run_cli(bogus)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
