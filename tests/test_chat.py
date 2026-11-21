import tempfile
import unittest
from pathlib import Path

from wa2html import probe
from wa2html.chat import build_chat
from wa2html.source import ExportSource, title_from_filename

from .helpers import (ANDROID_CHAT, ANDROID_FILES, IOS_CHAT, IOS_FILES, jpeg_header, make_zip, mp4, ogg_opus,
                      png, webp_vp8x)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class IOSChat(TempDirTest):
    def setUp(self):
        super().setUp()
        path = make_zip(self.tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)
        self.source = ExportSource(path)
        self.chat = build_chat(self.source)
        self.by_time = {m.raw_time.replace(" ", " "): m for m in self.chat.messages}

    def tearDown(self):
        self.source.close()
        super().tearDown()

    def msg(self, time):
        return self.by_time[time]

    def test_title_and_me(self):
        self.assertEqual(self.chat.title, "Bob")
        self.assertEqual([s.name for s in self.chat.senders], ["Alice", "Bob"])
        alice = self.chat.sender_by_name("Alice")
        self.assertEqual(self.chat.me, alice.id)

    def test_system_notice(self):
        self.assertEqual(self.chat.messages[0].kind, "system")

    def test_attachments(self):
        voice = self.msg("9:14:00 AM")
        self.assertEqual(voice.kind, "media")
        self.assertEqual(self.chat.media[voice.attachment].kind, "voice")
        photo = self.msg("9:16:00 AM")
        self.assertEqual(photo.text, "Look at this")
        self.assertEqual(self.chat.media[self.msg("9:19:00 AM").attachment].kind, "lottie")
        doc = self.msg("9:20:00 AM")
        self.assertEqual(doc.doc_meta, "2 pages")

    def test_missing_and_unreferenced(self):
        missing = self.msg("9:21:00 AM")
        self.assertTrue(missing.attachment_missing)
        self.assertEqual([n for _, n in self.chat.missing], ["00000008-PHOTO-2025-01-03-09-21-00.jpg"])
        self.assertEqual(self.chat.unreferenced, ["00000099-PHOTO-unreferenced.jpg"])

    def test_omitted(self):
        self.assertEqual(self.msg("1:05:00 PM").omitted, "image")
        captioned = self.msg("1:06:00 PM")
        self.assertEqual((captioned.kind, captioned.omitted, captioned.text), ("omitted", "video", "Nice day"))
        self.assertEqual(dict(self.chat.omitted), {"image": 1, "video": 1})

    def test_deleted_calls_location_edited(self):
        self.assertEqual(self.msg("1:07:00 PM").kind, "deleted")
        self.assertEqual(self.msg("1:08:00 PM").kind, "deleted")
        missed = self.msg("1:09:00 PM").call
        self.assertTrue(missed["missed"])
        self.assertFalse(missed["video"])
        video = self.msg("1:10:00 PM").call
        self.assertEqual((video["video"], video["detail"]), (True, "12 min"))
        loc = self.msg("1:11:00 PM").location
        self.assertEqual(loc["coords"], "-33.4489, -70.6693")
        edited = self.msg("1:12:00 PM")
        self.assertTrue(edited.edited)
        self.assertEqual(edited.text, "Fixed typo")

    def test_media_probing(self):
        media = self.chat.media
        jpg = media["00000002-PHOTO-2025-01-03-09-15-00.jpg"]
        self.assertEqual((jpg.width, jpg.height), (3000, 4000))  # EXIF orientation 6 swaps them
        sticker = media["00000004-STICKER-2025-01-03-09-17-00.webp"]
        self.assertEqual((sticker.kind, sticker.animated), ("sticker", True))
        video = media["00000005-VIDEO-2025-01-03-09-18-00.mp4"]
        self.assertEqual((video.width, video.height, video.duration), (1080, 1920, 12.5))
        voice = media["00000001-AUDIO-2025-01-03-09-14-00.opus"]
        self.assertAlmostEqual(voice.duration, 4.2, places=2)
        self.assertEqual(len(voice.waveform), 40)


class AndroidChat(TempDirTest):
    def test_android_export(self):
        path = make_zip(self.tmp / "WhatsApp Chat with Bob.zip", ANDROID_CHAT, ANDROID_FILES,
                        transcript_name="WhatsApp Chat with Bob.txt")
        with ExportSource(path) as source:
            chat = build_chat(source)
        kinds = [m.kind for m in chat.messages]
        self.assertEqual(kinds, ["system", "media", "media", "omitted", "media", "text"])
        self.assertEqual(chat.messages[2].text, "a caption\non two lines")
        self.assertTrue(chat.messages[4].attachment_missing)
        self.assertEqual(chat.title, "Bob")
        self.assertEqual(chat.me, chat.sender_by_name("Alice").id)

    def test_folder_and_bare_transcript(self):
        folder = self.tmp / "export"
        folder.mkdir()
        (folder / "_chat.txt").write_text(ANDROID_CHAT, encoding="utf-8")
        for name, data in ANDROID_FILES.items():
            (folder / name).write_bytes(data)
        with ExportSource(folder) as source:
            chat = build_chat(source, me="Bob")
        self.assertEqual(chat.me, chat.sender_by_name("Bob").id)
        self.assertEqual(len(chat.missing), 1)
        with ExportSource(folder / "_chat.txt") as source:
            chat = build_chat(source)
        self.assertEqual(len(chat.missing), 3)

    def test_unknown_me(self):
        path = make_zip(self.tmp / "chat.zip", ANDROID_CHAT, ANDROID_FILES)
        with ExportSource(path) as source:
            with self.assertRaises(ValueError):
                build_chat(source, me="Nobody")


class Titles(unittest.TestCase):
    def test_title_patterns(self):
        self.assertEqual(title_from_filename("WhatsApp Chat - Ana María"), "Ana María")
        self.assertEqual(title_from_filename("WhatsApp Chat with Bob (1)"), "Bob")
        self.assertEqual(title_from_filename("Chat de WhatsApp con Familia"), "Familia")
        self.assertIsNone(title_from_filename("holiday photos"))


class Probes(unittest.TestCase):
    def test_images(self):
        self.assertEqual(probe.image_size(png(7, 3)), (7, 3))
        self.assertEqual(probe.image_size(jpeg_header(640, 480)), (640, 480))
        self.assertEqual(probe.image_size(webp_vp8x(300, 200)), (300, 200))
        self.assertIsNone(probe.image_size(b"not an image"))

    def test_mp4(self):
        self.assertEqual(probe.mp4_info(mp4(640, 360, 3.0)), ((640, 360), 3.0))
        self.assertIsNone(probe.mp4_info(b"garbage"))

    def test_opus(self):
        duration, wave = probe.opus_info(ogg_opus(1.5, [50] * 10 + [2] * 10))
        self.assertAlmostEqual(duration, 1.5, places=2)
        self.assertEqual(len(wave), 40)
        self.assertEqual(max(wave), 100)
        self.assertEqual(wave[-1], 8)  # silence stays at the minimum height
        self.assertIsNone(probe.opus_info(b"not ogg"))


if __name__ == "__main__":
    unittest.main()
