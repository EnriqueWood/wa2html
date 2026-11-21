"""Small, dependency-free readers for media metadata.

They read only what the viewer needs to lay out the page before the media
loads (image and video sizes, durations) and to draw voice-note waveforms.
Every function returns ``None`` instead of raising on data it does not
understand.
"""

from __future__ import annotations

import io
import struct
import zipfile
from typing import Iterator, List, Optional, Tuple

Size = Tuple[int, int]


# -- images --------------------------------------------------------------


def _jpeg_orientation(app1: bytes) -> int:
    if not app1.startswith(b"Exif\x00\x00"):
        return 1
    tiff = app1[6:]
    if len(tiff) < 8:
        return 1
    endian = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack(endian + "I", tiff[4:8])
        (count,) = struct.unpack(endian + "H", tiff[ifd : ifd + 2])
        for i in range(count):
            entry = tiff[ifd + 2 + 12 * i : ifd + 14 + 12 * i]
            tag, _type, _n = struct.unpack(endian + "HHI", entry[:8])
            if tag == 0x0112:
                return struct.unpack(endian + "H", entry[8:10])[0]
    except struct.error:
        pass
    return 1


def _jpeg_size(data: bytes) -> Optional[Size]:
    pos = 2
    orientation = 1
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            pos += 1 if marker == 0xFF else 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if marker == 0xE1:
            orientation = _jpeg_orientation(data[pos + 4 : pos + 2 + length])
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
            if orientation in (5, 6, 7, 8):
                width, height = height, width
            return (width, height)
        pos += 2 + length
    return None


def image_size(data: bytes) -> Optional[Size]:
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:2] == b"\xff\xd8":
            return _jpeg_size(data)
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8X":
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
                return (width, height)
            if chunk == b"VP8 ":
                width, height = struct.unpack("<HH", data[26:30])
                return (width & 0x3FFF, height & 0x3FFF)
            if chunk == b"VP8L":
                b = data[21:25]
                width = 1 + (((b[1] & 0x3F) << 8) | b[0])
                height = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                return (width, height)
    except (struct.error, IndexError):
        pass
    return None


def webp_is_animated(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[12:16] == b"VP8X" and bool(data[20] & 0x02)


# -- MP4 / MOV -------------------------------------------------------------


def _boxes(data: bytes, start: int, end: int) -> Iterator[Tuple[bytes, int, int]]:
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        header = 8
        if size == 1:
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind, pos + header, pos + size
        pos += size


def mp4_info(data: bytes) -> Optional[Tuple[Optional[Size], Optional[float]]]:
    """Return ((width, height), duration_seconds) of the first video track."""
    try:
        for kind, start, end in _boxes(data, 0, len(data)):
            if kind != b"moov":
                continue
            size: Optional[Size] = None
            duration: Optional[float] = None
            for kind2, s2, e2 in _boxes(data, start, end):
                if kind2 == b"mvhd":
                    if data[s2] == 1:
                        timescale, length = struct.unpack(">IQ", data[s2 + 20 : s2 + 32])
                    else:
                        timescale, length = struct.unpack(">II", data[s2 + 12 : s2 + 20])
                    if timescale:
                        duration = length / timescale
                elif kind2 == b"trak" and size is None:
                    for kind3, s3, _e3 in _boxes(data, s2, e2):
                        if kind3 != b"tkhd":
                            continue
                        matrix = s3 + (52 if data[s3] == 1 else 40)
                        width, height = struct.unpack(">II", data[matrix + 36 : matrix + 44])
                        width, height = width >> 16, height >> 16
                        (b,) = struct.unpack(">i", data[matrix + 4 : matrix + 8])
                        if b != 0:  # rotated by 90 or 270 degrees
                            width, height = height, width
                        if width and height:
                            size = (width, height)
            return size, duration
    except (struct.error, IndexError):
        pass
    return None


# -- Ogg Opus (voice notes) --------------------------------------------------


def _ogg_packets(data: bytes) -> Tuple[List[int], int]:
    """Return the size of every packet and the last granule position."""
    packets: List[int] = []
    pending = 0
    last_granule = 0
    pos = 0
    while True:
        page = data.find(b"OggS", pos)
        if page < 0 or page + 27 > len(data):
            break
        segments = data[page + 26]
        table = data[page + 27 : page + 27 + segments]
        (granule,) = struct.unpack("<q", data[page + 6 : page + 14])
        for lacing in table:
            pending += lacing
            if lacing < 255:
                packets.append(pending)
                pending = 0
        if granule > 0:
            last_granule = granule
        pos = page + 27 + segments + sum(table)
    return packets, last_granule


def opus_info(data: bytes, bars: int = 40) -> Optional[Tuple[float, List[int]]]:
    """Duration and a waveform for an Ogg Opus file, without decoding it.

    Opus is a variable-bitrate codec: speech produces large packets and
    silence tiny ones, so packet sizes over time give a faithful-looking
    loudness envelope. Returns (duration_seconds, bars of 0..100).
    """
    if data[:4] != b"OggS":
        return None
    head = data.find(b"OpusHead")
    if head < 0:
        return None
    try:
        (pre_skip,) = struct.unpack("<H", data[head + 10 : head + 12])
        packets, granule = _ogg_packets(data)
    except (struct.error, IndexError):
        return None
    duration = max(0.0, (granule - pre_skip) / 48000.0)
    audio = packets[2:]  # the first two packets are the OpusHead and OpusTags headers
    if not audio:
        return duration, [8] * bars
    # Resample the packet sizes to a fixed number of bars (linear interpolation
    # when there are fewer packets than bars, averaging when there are more).
    values = []
    n = len(audio)
    for i in range(bars):
        start = i * n / bars
        end = (i + 1) * n / bars
        if end - start >= 1:
            chunk = audio[int(start) : max(int(start) + 1, int(end))]
            values.append(sum(chunk) / len(chunk))
        else:
            pos = min(n - 1.0, (start + end) / 2)
            left = int(pos)
            right = min(n - 1, left + 1)
            frac = pos - left
            values.append(audio[left] * (1 - frac) + audio[right] * frac)
    peak = max(values) or 1.0
    # Speech packets are all fairly large; a cubic curve brings out the
    # differences between them while silence stays at the minimum height.
    wave = [round(8 + 92 * (v / peak) ** 3) for v in values]
    return duration, wave


# -- WhatsApp animated stickers (.was) --------------------------------------


def was_animation_json(data: bytes) -> Optional[bytes]:
    """Return the Lottie JSON stored inside a WhatsApp animated sticker."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            names = [n for n in inner.namelist() if n.lower().endswith(".json")]
            names.sort(key=lambda n: (not n.lower().endswith("animation.json"), len(n)))
            if names:
                return inner.read(names[0])
    except (zipfile.BadZipFile, KeyError, OSError):
        pass
    return None


# -- vCard -----------------------------------------------------------------


def vcard_summary(data: bytes) -> dict:
    text = data.decode("utf-8", errors="replace")
    # Unfold continuation lines (RFC 6350 section 3.2).
    text = text.replace("\r\n ", "").replace("\n ", "")
    name = ""
    phones: List[str] = []
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.split(";")[0].upper()
        if key.endswith("FN") and not name:
            name = value.strip()
        elif key.endswith("TEL") and value.strip():
            phones.append(value.strip())
    return {"name": name, "phones": phones}
