"""Read-only access to the files of a WhatsApp export.

An export can be given as the ``.zip`` produced by WhatsApp, as a folder where
that zip was extracted, or as a bare transcript ``.txt`` (an export made
"without media"). The source is never modified.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Union

BIDI_MARKS = "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"
IGNORED_FILES = {".ds_store", "thumbs.db", "desktop.ini"}

# "WhatsApp Chat - Alice.zip" (iOS), "WhatsApp Chat with Alice.txt" (Android),
# and the same in other languages.
_TITLE_RE = re.compile(
    r"^(?:WhatsApp[ -]Chat|Chat de WhatsApp|Chat WhatsApp|Conversa do WhatsApp|"
    r"Discussion WhatsApp|WhatsApp-Chat|Czat WhatsApp|WhatsApp Sohbeti)"
    r"\s*(?:-|with|con|com|avec|mit|z|ile|met)\s+(?P<title>.+)$",
    re.IGNORECASE,
)


class ExportError(Exception):
    """The input is not something we can read as a WhatsApp export."""


def normalize_name(name: str) -> str:
    """Normalize a file name or a reference to one, so they can be compared.

    Strips folders, invisible direction marks and surrounding spaces, and uses
    the NFC Unicode form (iOS and macOS tend to write names in NFD).
    """
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = name.strip(BIDI_MARKS + " \t")
    return unicodedata.normalize("NFC", name)


def title_from_filename(stem: str) -> Optional[str]:
    stem = re.sub(r"\s*\(\d+\)$", "", stem.strip())  # "name (1)" from repeated downloads
    match = _TITLE_RE.match(stem)
    if match:
        return match.group("title").strip()
    return None


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not info.flag_bits & 0x800:
        # Not flagged as UTF-8: zipfile decoded it as CP437. Most phones write
        # UTF-8 anyway, so try to undo that.
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


class ExportSource:
    """The transcript and media files of one export."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._zip: Optional[zipfile.ZipFile] = None
        self._entries: Dict[str, Union[zipfile.ZipInfo, Path]] = {}
        self._folded: Dict[str, str] = {}
        self.duplicate_names: List[str] = []

        if not self.path.exists():
            raise ExportError(f"{self.path} does not exist")
        if self.path.is_dir():
            self.kind = "folder"
            for file in sorted(self.path.rglob("*")):
                if file.is_file():
                    self._add(normalize_name(file.name), file)
        elif zipfile.is_zipfile(self.path):
            self.kind = "zip"
            self._zip = zipfile.ZipFile(self.path)
            for info in self._zip.infolist():
                if info.is_dir() or info.filename.startswith("__MACOSX/"):
                    continue
                self._add(normalize_name(_zip_member_name(info)), info)
        elif self.path.suffix.lower() == ".txt":
            self.kind = "transcript"
            self._add(normalize_name(self.path.name), self.path)
        else:
            raise ExportError(f"{self.path} is not a .zip, a folder or a .txt file")

        self.transcript_name = self._pick_transcript()

    # -- setup -------------------------------------------------------------

    def _add(self, name: str, entry: Union[zipfile.ZipInfo, Path]) -> None:
        if not name or name.lower() in IGNORED_FILES or name.startswith("._"):
            return
        if name in self._entries:
            self.duplicate_names.append(name)
            return
        self._entries[name] = entry
        self._folded.setdefault(name.casefold(), name)

    def _pick_transcript(self) -> str:
        texts = [n for n in self._entries if n.lower().endswith(".txt")]
        if not texts:
            raise ExportError(f"no chat transcript (.txt) found in {self.path}")
        for name in texts:
            if name == "_chat.txt":
                return name
        for name in texts:
            if title_from_filename(name[:-4]) is not None:
                return name
        if len(texts) == 1:
            return texts[0]
        raise ExportError(
            f"several .txt files in {self.path} and none looks like the chat transcript: "
            + ", ".join(sorted(texts))
        )

    # -- queries -----------------------------------------------------------

    @property
    def guessed_title(self) -> Optional[str]:
        candidates = [self.transcript_name[:-4]]
        if self.kind in ("zip", "folder"):
            candidates.insert(0, self.path.stem if self.kind == "zip" else self.path.name)
        for stem in candidates:
            title = title_from_filename(stem)
            if title:
                return title
        return None

    def media_names(self) -> List[str]:
        return [n for n in self._entries if n != self.transcript_name]

    def resolve(self, reference: str) -> Optional[str]:
        """Return the stored name matching a reference from the transcript."""
        name = normalize_name(reference)
        if name in self._entries and name != self.transcript_name:
            return name
        folded = self._folded.get(name.casefold())
        if folded and folded != self.transcript_name:
            return folded
        return None

    def size(self, name: str) -> int:
        entry = self._entries[name]
        if isinstance(entry, zipfile.ZipInfo):
            return entry.file_size
        return entry.stat().st_size

    def read(self, name: str) -> bytes:
        entry = self._entries[name]
        if isinstance(entry, zipfile.ZipInfo):
            assert self._zip is not None
            return self._zip.read(entry)
        return entry.read_bytes()

    def open(self, name: str) -> BinaryIO:
        entry = self._entries[name]
        if isinstance(entry, zipfile.ZipInfo):
            assert self._zip is not None
            return self._zip.open(entry)
        return entry.open("rb")

    def read_transcript(self) -> bytes:
        return self.read(self.transcript_name)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def __enter__(self) -> "ExportSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
