"""Re-read a generated page and check that nothing from the export was lost.

Every media file is compared by SHA-256 with the original in the export, and
the original transcript must be embedded byte for byte.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .chat import Chat

_BLOCK_RE = re.compile(r'<script type="application/(?:octet-stream|json)" id="([^"]+)"[^>]*>([^<]*)</script>')


@dataclass
class Verification:
    files_checked: int = 0
    problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_page(chat: Chat, page: Path, mode: str) -> Verification:
    result = Verification()
    text = page.read_text(encoding="utf-8")
    blocks = {block_id: data for block_id, data in _BLOCK_RE.findall(text)}

    transcript = blocks.get("wa-transcript")
    if transcript is None or base64.b64decode(transcript) != chat.transcript_bytes:
        result.problems.append("the original transcript is not embedded intact")

    rendered = len(re.findall(r'<div class="(?:msg [^"]*|sys)" id="m\d+"', text))
    if rendered != len(chat.messages):
        result.problems.append(f"{rendered} of {len(chat.messages)} messages found in the page")

    hashes = {}
    for item in chat.media.values():
        result.files_checked += 1
        if item.kind == "lottie":
            if item.block not in blocks or blocks[item.block] == "null":
                result.problems.append(f"{item.name}: animation not embedded")
            if mode == "folder" and not _folder_file_ok(page, item):
                result.problems.append(f"{item.name}: copy in media/ is missing or different")
            continue
        if mode == "single":
            data = blocks.get(item.block)
            if data is None:
                result.problems.append(f"{item.name}: not embedded")
                continue
            if item.block not in hashes:
                hashes[item.block] = hashlib.sha256(base64.b64decode(data)).hexdigest()
            if hashes[item.block] != item.sha256:
                result.problems.append(f"{item.name}: embedded copy differs from the original")
        elif not _folder_file_ok(page, item):
            result.problems.append(f"{item.name}: copy in media/ is missing or different")
    return result


def _folder_file_ok(page: Path, item) -> bool:
    if not item.copied_as:
        return False
    path = page.parent / "media" / item.copied_as
    return path.is_file() and _sha256_file(path) == item.sha256
