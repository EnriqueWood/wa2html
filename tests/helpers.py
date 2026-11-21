"""Builders for synthetic WhatsApp exports. Everything here is made up."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Dict, List

NNBSP = " "
LRM = "‎"


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def jpeg_header(width: int, height: int, orientation: int = 1) -> bytes:
    """Enough of a JPEG for the size reader: SOI, EXIF APP1, SOF0."""
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1) + struct.pack("<HHIHH", 0x0112, 3, 1, orientation, 0)
    app1 = b"Exif\x00\x00" + tiff
    sof = struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return (
        b"\xff\xd8"
        + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
        + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
        + b"\xff\xd9"
    )


def webp_vp8x(width: int, height: int, animated: bool = False) -> bytes:
    flags = 0x02 if animated else 0
    payload = bytes([flags, 0, 0, 0]) + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    body = b"WEBP" + b"VP8X" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def mp4(width: int, height: int, seconds: float, rotate: bool = False) -> bytes:
    timescale = 1000
    mvhd = bytes(4) + bytes(8) + struct.pack(">II", timescale, int(seconds * timescale)) + bytes(80)
    matrix = [0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000]
    if rotate:
        matrix = [0, 0x00010000, 0, -0x00010000, 0, 0, 0, 0, 0x40000000]
    tkhd = (
        bytes(4) + bytes(4 * 5) + bytes(8) + bytes(8)
        + b"".join(struct.pack(">i", v) for v in matrix)
        + struct.pack(">II", width << 16, height << 16)
    )
    moov = _box(b"moov", _box(b"mvhd", mvhd) + _box(b"trak", _box(b"tkhd", tkhd)))
    return _box(b"ftyp", b"mp42" + bytes(4) + b"mp42isom") + _box(b"mdat", b"\x00" * 64) + moov


def _ogg_page(packets: List[bytes], granule: int, seq: int, header_type: int = 0) -> bytes:
    table = b""
    for p in packets:
        n = len(p)
        table += b"\xff" * (n // 255) + bytes([n % 255])
    head = b"OggS" + bytes([0, header_type]) + struct.pack("<qIII", granule, 1234, seq, 0) + bytes([len(table)])
    return head + table + b"".join(packets)


def ogg_opus(seconds: float, packet_sizes: List[int]) -> bytes:
    pre_skip = 312
    head = b"OpusHead" + bytes([1, 1]) + struct.pack("<HIhB", pre_skip, 48000, 0, 0)
    tags = b"OpusTags" + struct.pack("<I", 4) + b"test" + struct.pack("<I", 0)
    audio = [bytes([0xFC]) + b"\x00" * (size - 1) for size in packet_sizes]
    granule = int(seconds * 48000) + pre_skip
    return _ogg_page([head], 0, 0, 2) + _ogg_page([tags], 0, 1) + _ogg_page(audio, granule, 2, 4)


def was_sticker() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("animation/animation.json", '{"v":"5.7.4","fr":30,"ip":0,"op":30,"w":512,"h":512,"layers":[]}')
        z.writestr("animation/animation.json.trust_token", "x")
    return buf.getvalue()


def make_zip(path: Path, transcript: str, files: Dict[str, bytes], transcript_name: str = "_chat.txt") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(transcript_name, transcript.encode("utf-8"))
        for name, data in files.items():
            z.writestr(name, data)
    return path


def ios_line(date: str, time: str, sender: str, body: str, lrm: bool = False) -> str:
    prefix = LRM if lrm else ""
    return f"{prefix}[{date}, {time}] {sender}: {body}"


IOS_CHAT = "\r\n".join(
    [
        ios_line("03-01-25", f"9:12:01{NNBSP}AM", "Bob", f"{LRM}Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them."),
        ios_line("03-01-25", f"9:12:01{NNBSP}AM", "Alice", "Hi *Bob*! See https://example.org/a_b_c"),
        ios_line("03-01-25", f"9:13:10{NNBSP}AM", "Bob", "Hello Alice"),
        "this is a second line",
        "[03/01, 09:10] Carol: a pasted message stays inside",
        ios_line("03-01-25", f"9:14:00{NNBSP}AM", "Bob", f"{LRM}<attached: 00000001-AUDIO-2025-01-03-09-14-00.opus>", lrm=True),
        ios_line("03-01-25", f"9:15:00{NNBSP}AM", "Alice", f"{LRM}<attached: 00000002-PHOTO-2025-01-03-09-15-00.jpg>", lrm=True),
        ios_line("03-01-25", f"9:16:00{NNBSP}AM", "Bob", f"Look at this {LRM}<attached: 00000003-PHOTO-2025-01-03-09-16-00.png>", lrm=True),
        ios_line("03-01-25", f"9:17:00{NNBSP}AM", "Bob", f"{LRM}<attached: 00000004-STICKER-2025-01-03-09-17-00.webp>", lrm=True),
        ios_line("03-01-25", f"9:18:00{NNBSP}AM", "Alice", f"{LRM}<attached: 00000005-VIDEO-2025-01-03-09-18-00.mp4>", lrm=True),
        ios_line("03-01-25", f"9:19:00{NNBSP}AM", "Bob", f"{LRM}<attached: 00000006-STICKER-2025-01-03-09-19-00.was>", lrm=True),
        ios_line("03-01-25", f"9:20:00{NNBSP}AM", "Alice", f"report.pdf • {LRM}2 pages {LRM}<attached: 00000007-report.pdf>", lrm=True),
        ios_line("03-01-25", f"9:21:00{NNBSP}AM", "Bob", f"{LRM}<attached: 00000008-PHOTO-2025-01-03-09-21-00.jpg>", lrm=True),
        ios_line("13-01-25", f"1:05:00{NNBSP}PM", "Bob", f"{LRM}image omitted", lrm=True),
        ios_line("13-01-25", f"1:06:00{NNBSP}PM", "Bob", f"Nice day {LRM}video omitted", lrm=True),
        ios_line("13-01-25", f"1:07:00{NNBSP}PM", "Alice", f"{LRM}You deleted this message.", lrm=True),
        ios_line("13-01-25", f"1:08:00{NNBSP}PM", "Bob", f"{LRM}This message was deleted.", lrm=True),
        ios_line("13-01-25", f"1:09:00{NNBSP}PM", "Alice", f"{LRM}Missed voice call. {LRM}Tap to call back", lrm=True),
        ios_line("13-01-25", f"1:10:00{NNBSP}PM", "Bob", f"{LRM}Video call. {LRM}12 min", lrm=True),
        ios_line("13-01-25", f"1:11:00{NNBSP}PM", "Bob", f"{LRM}Location: https://maps.google.com/?q=-33.4489,-70.6693", lrm=True),
        ios_line("13-01-25", f"1:12:00{NNBSP}PM", "Alice", f"Fixed typo {LRM}<This message was edited>"),
        ios_line("13-01-25", f"1:13:00{NNBSP}PM", "Bob", "😂😂"),
        ios_line("13-01-25", f"1:14:00{NNBSP}PM", "Bob", f"{LRM}<attached: 00000010-STICKER-2025-01-13-13-14-00.webp>", lrm=True),
        ios_line("13-01-25", f"1:15:00{NNBSP}PM", "Bob", f"{LRM}<attached: 00000011-STICKER-2025-01-13-13-15-00.was>", lrm=True),
        f"[13-01-25, 12:31:00{NNBSP}AM] Alice:",
        "a message whose text starts on the next line",
        ios_line("13-01-25", f"12:32:00{NNBSP}AM", "Bob", "<b>not html</b> & co"),
    ]
) + "\r\n"

IOS_FILES = {
    "00000001-AUDIO-2025-01-03-09-14-00.opus": ogg_opus(4.2, [100, 280, 300, 2, 2, 290, 310, 250]),
    "00000002-PHOTO-2025-01-03-09-15-00.jpg": jpeg_header(4000, 3000, orientation=6),
    "00000003-PHOTO-2025-01-03-09-16-00.png": png(8, 4),
    "00000004-STICKER-2025-01-03-09-17-00.webp": webp_vp8x(512, 512, animated=True),
    "00000005-VIDEO-2025-01-03-09-18-00.mp4": mp4(1920, 1080, 12.5, rotate=True),
    "00000006-STICKER-2025-01-03-09-19-00.was": was_sticker(),
    "00000007-report.pdf": b"%PDF-1.4 fake",
    # The same sticker sent again: embedded once, still verified for both.
    "00000010-STICKER-2025-01-13-13-14-00.webp": webp_vp8x(512, 512, animated=True),
    "00000011-STICKER-2025-01-13-13-15-00.was": was_sticker(),
    "00000099-PHOTO-unreferenced.jpg": jpeg_header(10, 20),
}

ANDROID_CHAT = "\n".join(
    [
        "27/10/26, 11:55 - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.",
        "27/10/26, 11:55 - Alice: PTT-20261027-WA0001.opus (file attached)",
        "27/10/26, 11:56 - Bob: IMG-20261027-WA0002.jpg (file attached)",
        "a caption",
        "on two lines",
        "27/10/26, 11:57 - Bob: <Media omitted>",
        "27/10/26, 11:58 - Alice: DOC-20261027-WA0003.pdf (file attached)",
        "27/10/26, 23:59 - Alice: good night",
    ]
) + "\n"

ANDROID_FILES = {
    "PTT-20261027-WA0001.opus": ogg_opus(2.0, [120, 130]),
    "IMG-20261027-WA0002.jpg": jpeg_header(100, 50),
}
