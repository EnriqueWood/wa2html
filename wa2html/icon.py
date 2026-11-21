"""The wa2html icon (a speech bubble with three dots), drawn in code.

Used for the window and, through ``packaging/make_icon.py``, for the Windows
executable. No image files or libraries needed.
"""

from __future__ import annotations

import struct
import zlib
from typing import Iterable

BUBBLE = (31, 138, 112)  # #1f8a70
DOTS = (255, 255, 255)


def _inside_bubble(x: float, y: float) -> bool:
    if (x - 0.5) ** 2 + (y - 0.46) ** 2 <= 0.40 ** 2:
        return True
    # The tail: a triangle at the bottom left.
    (x1, y1), (x2, y2), (x3, y3) = (0.20, 0.64), (0.10, 0.93), (0.44, 0.80)
    d1 = (x - x2) * (y1 - y2) - (x1 - x2) * (y - y2)
    d2 = (x - x3) * (y2 - y3) - (x2 - x3) * (y - y3)
    d3 = (x - x1) * (y3 - y1) - (x3 - x1) * (y - y1)
    negative = d1 < 0 or d2 < 0 or d3 < 0
    positive = d1 > 0 or d2 > 0 or d3 > 0
    return not (negative and positive)


def _inside_dot(x: float, y: float) -> bool:
    return any((x - cx) ** 2 + (y - 0.46) ** 2 <= 0.058 ** 2 for cx in (0.31, 0.50, 0.69))


def _pixels(size: int, samples: int) -> Iterable[bytes]:
    step = 1.0 / (size * samples)
    for row in range(size):
        line = bytearray(b"\x00")  # PNG filter type: none
        for col in range(size):
            bubble = dots = 0
            for sy in range(samples):
                for sx in range(samples):
                    x = (col * samples + sx + 0.5) * step
                    y = (row * samples + sy + 0.5) * step
                    if _inside_bubble(x, y):
                        bubble += 1
                        if _inside_dot(x, y):
                            dots += 1
            total = samples * samples
            alpha = bubble / total
            if bubble:
                mix = dots / bubble
                rgb = [round(b * (1 - mix) + d * mix) for b, d in zip(BUBBLE, DOTS)]
            else:
                rgb = [0, 0, 0]
            line += bytes(rgb + [round(alpha * 255)])
        yield bytes(line)


def png(size: int = 64) -> bytes:
    """The icon as an RGBA PNG of `size` x `size` pixels (antialiased)."""
    samples = 4 if size <= 64 else 2

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(_pixels(size, samples))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ico(sizes=(256, 48, 32, 16)) -> bytes:
    """A Windows .ico file holding the icon as PNG images."""
    images = [png(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(sizes, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)
