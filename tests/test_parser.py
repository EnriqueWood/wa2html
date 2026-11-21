import unittest
from datetime import datetime

from wa2html.parser import TranscriptFormatError, detect_format, parse_transcript

from .helpers import ANDROID_CHAT, IOS_CHAT, NNBSP


class IOSTranscript(unittest.TestCase):
    def setUp(self):
        self.t = parse_transcript(IOS_CHAT)

    def test_layout(self):
        fmt = self.t.format
        self.assertEqual(fmt.platform, "ios")
        self.assertEqual(fmt.date_order, "dmy")
        self.assertTrue(fmt.has_seconds)
        self.assertTrue(fmt.has_ampm)

    def test_every_line_is_kept(self):
        lines = IOS_CHAT.replace("\r\n", "\n").rstrip("\n").split("\n")
        self.assertEqual(self.t.line_count, len(lines))
        self.assertEqual([l for m in self.t.messages for l in m.raw_lines], lines)
        self.assertEqual(len(self.t.messages), 24)

    def test_multiline_and_pasted_header(self):
        msg = self.t.messages[2]
        self.assertEqual(msg.sender, "Bob")
        self.assertEqual(msg.body, "Hello Alice\nthis is a second line\n[03/01, 09:10] Carol: a pasted message stays inside")

    def test_timestamps_with_narrow_space_and_ampm(self):
        self.assertEqual(self.t.messages[1].timestamp, datetime(2025, 1, 3, 9, 12, 1))
        self.assertEqual(self.t.messages[11].timestamp, datetime(2025, 1, 13, 13, 5, 0))
        midnight = next(m for m in self.t.messages if m.raw_time.startswith("12:31"))
        self.assertEqual(midnight.timestamp.hour, 0)

    def test_sender_with_text_on_next_line(self):
        msg = next(m for m in self.t.messages if m.raw_time.startswith("12:31"))
        self.assertEqual(msg.sender, "Alice")
        self.assertEqual(msg.body, "\na message whose text starts on the next line")


class AndroidTranscript(unittest.TestCase):
    def test_layout_and_system_line(self):
        t = parse_transcript(ANDROID_CHAT)
        self.assertEqual(t.format.platform, "android")
        self.assertFalse(t.format.has_seconds)
        self.assertIsNone(t.messages[0].sender)
        self.assertEqual(t.messages[-1].timestamp, datetime(2026, 10, 27, 23, 59))
        self.assertEqual(t.messages[2].body, "IMG-20261027-WA0002.jpg (file attached)\na caption\non two lines")

    def test_spanish_am_pm(self):
        text = "5/11/24, 9:05 a. m. - Ana: hola\n5/11/24, 9:06 p. m. - Luis: chao\n"
        t = parse_transcript(text)
        self.assertEqual(t.messages[0].timestamp, datetime(2024, 11, 5, 9, 5))
        self.assertEqual(t.messages[1].timestamp, datetime(2024, 11, 5, 21, 6))


class DateOrder(unittest.TestCase):
    def test_month_first_when_second_field_exceeds_12(self):
        text = "1/25/24, 10:00 - A: x\n1/26/24, 10:00 - B: y\n"
        self.assertEqual(detect_format(text.splitlines()).date_order, "mdy")

    def test_ambiguous_dates_follow_chronology(self):
        # Day-first: 5 Jan, 9 Jan, 3 Feb, 1 Mar. Month-first: May, Sep, Mar, Jan.
        text = "05/01/24, 10:00 - A: x\n09/01/24, 10:00 - B: y\n03/02/24, 10:00 - A: z\n01/03/24, 10:00 - A: w\n"
        fmt = detect_format(text.splitlines())
        self.assertTrue(fmt.date_order_guessed)
        self.assertEqual(fmt.date_order, "dmy")
        # Month-first: 5 Jan, 9 Jan, 3 Feb, 1 Mar. Day-first: May, Sep, Mar, Jan.
        text2 = "01/05/24, 10:00 - A: x\n01/09/24, 10:00 - B: y\n02/03/24, 10:00 - A: z\n03/01/24, 10:00 - A: w\n"
        self.assertEqual(detect_format(text2.splitlines()).date_order, "mdy")

    def test_forced_order(self):
        text = f"[01-02-24, 10:00:00{NNBSP}AM] A: x\n"
        t = parse_transcript(text, date_order="mdy")
        self.assertEqual(t.messages[0].timestamp, datetime(2024, 1, 2, 10, 0))


class Robustness(unittest.TestCase):
    def test_text_before_first_header_is_kept(self):
        t = parse_transcript("﻿some preamble\n27/10/26, 11:55 - A: hi\n")
        self.assertEqual(len(t.messages), 2)
        self.assertIsNone(t.messages[0].timestamp)
        self.assertEqual(t.messages[0].body, "some preamble")

    def test_not_a_chat(self):
        with self.assertRaises(TranscriptFormatError):
            parse_transcript("hello\nworld\n")


if __name__ == "__main__":
    unittest.main()
