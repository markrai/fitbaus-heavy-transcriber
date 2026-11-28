from dataclasses import dataclass
import math
from pathlib import PurePosixPath
import re

FORMATS = frozenset({"epub", "pdf", "mobi", "azw", "azw3", "fb2", "cbz", "cbr"})
MAX_FILES = 4096
FILE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}", re.ASCII)


class CompanionError(ValueError):
    pass


def choose_epub(rows):
    epubs = [row for row in rows if row.format == "epub"]
    primary = [row for row in epubs if row.role == "primary"]
    if len(primary) == 1:
        return primary[0]
    if len(epubs) > 1:
        raise CompanionError("Multiple EPUB companions without a unique primary; no automatic selection")
    return epubs[0] if epubs else None


@dataclass(frozen=True, slots=True)
class Companion:
    file_id: str
    filename: str
    format: str
    size: int
    mtime_ms: int | float
    role: str

    def public(self):
        return {"file_id": self.file_id, "filename": self.filename, "format": self.format,
                "size": self.size, "role": self.role}


def parse_file(row, role, *, primary=False):
    if not isinstance(row, dict) or not isinstance(row.get("metadata"), dict):
        raise CompanionError("Invalid companion file metadata")
    meta = row["metadata"]
    ext = meta.get("ext")
    if not isinstance(ext, str):
        if primary or row.get("fileType") == "ebook":
            raise CompanionError("Missing companion format")
        return None
    fmt = ext.lower().removeprefix(".")
    if fmt not in FORMATS:
        return None
    if not primary and row.get("fileType") not in (None, "ebook", "unknown", "text"):
        raise CompanionError("Conflicting companion file type")
    file_id, filename, size, mtime = row.get("ino"), meta.get("filename"), meta.get("size"), meta.get("mtimeMs")
    if (not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id)
            or not isinstance(filename, str) or not 1 <= len(filename) <= 255
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or c in "/\\" for c in filename)
            or PurePosixPath(filename).suffix.lower() != "." + fmt
            or type(size) is not int or not 0 < size <= 2**53 - 1
            or type(mtime) not in (int, float) or not 0 <= mtime <= 2**53 - 1
            or not math.isfinite(mtime)):
        raise CompanionError("Invalid companion identity or metadata")
    if not primary and row.get("isSupplementary") not in (None, True, False):
        raise CompanionError("Invalid supplementary flag")
    return Companion(file_id, filename, fmt, size, mtime, role)


def discover(item, item_id):
    if (not isinstance(item, dict) or item.get("id") != item_id
            or item.get("mediaType") != "book" or item.get("isMissing") or item.get("isInvalid")
            or not isinstance(item.get("media"), dict)):
        raise CompanionError("Invalid Audiobookshelf item")
    rows = item.get("libraryFiles")
    if not isinstance(rows, list) or len(rows) > MAX_FILES:
        raise CompanionError("Invalid expanded library file list")
    primary = item["media"].get("ebookFile")
    first = parse_file(primary, "primary", primary=True) if primary is not None else None
    found = {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CompanionError("Invalid library file row")
        candidate = parse_file(row, "supplementary" if row.get("isSupplementary") is True else "attached")
        if candidate is None:
            continue
        if candidate.file_id in seen:
            raise CompanionError("Duplicate companion file ID")
        seen.add(candidate.file_id)
        if first and first.file_id == candidate.file_id:
            if (first.filename, first.format, first.size, first.mtime_ms) != (
                    candidate.filename, candidate.format, candidate.size, candidate.mtime_ms):
                raise CompanionError("Conflicting primary companion metadata")
            if candidate.role == "supplementary":
                raise CompanionError("Conflicting primary companion role")
            candidate = first
        found[candidate.file_id] = candidate
    if first:
        found[first.file_id] = first
    return tuple(sorted(found.values(), key=lambda row: (row.role != "primary", row.filename.casefold(), row.file_id)))
