from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
import zipfile

from epub_inventory import EpubError, archive_members, inspect_epub, read_xml


SCHEMA = "fitbaus.epub-alignment-preview/v1"
ANCHOR_WORDS = 8
MAX_WORDS = 500000
MAX_TEXT_BYTES = 32 * 1024 * 1024
MAX_CUES = 100000
MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024
XHTML = "{http://www.w3.org/1999/xhtml}"
BLOCKS = frozenset("address article blockquote br dd div dl dt h1 h2 h3 h4 h5 h6 hr li ol p pre section table td th tr ul".split())
SKIP = frozenset("aside audio canvas figure figcaption iframe nav noscript script style video".split())
WORD = re.compile(r"[^\W_]+", re.UNICODE)


class AlignmentError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    spine_index: int
    path: str
    words: tuple[str, ...]


def words(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(WORD.findall(normalized))


def body_text(body):
    pieces = []
    stack = [(body, False)]
    while stack:
        node, leaving = stack.pop()
        local = node.tag.removeprefix(XHTML)
        block = local in BLOCKS
        if leaving:
            if block:
                pieces.append(" ")
            if node is not body and node.tail:
                pieces.append(node.tail)
            continue
        if (not node.tag.startswith(XHTML) or local in SKIP
                or "hidden" in node.attrib or node.get("aria-hidden") == "true"):
            pieces.append(" ")
            if node.tail:
                pieces.append(node.tail)
            continue
        if block:
            pieces.append(" ")
        if node.text:
            pieces.append(node.text)
        stack.append((node, True))
        stack.extend((child, False) for child in reversed(node))
    return "".join(pieces)


def read_sections(stream):
    inventory = inspect_epub(stream)
    sections = []
    total_bytes = total_words = 0
    try:
        with zipfile.ZipFile(stream) as archive:
            members = archive_members(archive)
            for index, row in enumerate(inventory["spine"]):
                if not row["linear"] or row["media_type"] != "application/xhtml+xml":
                    continue
                path = row["path"]
                total_bytes += members[path].file_size
                if total_bytes > MAX_TEXT_BYTES:
                    raise AlignmentError("EPUB reading-order text exceeds preview limit")
                root = read_xml(archive, members, path)
                body = root.find(XHTML + "body")
                if root.tag != XHTML + "html" or body is None:
                    raise AlignmentError("Unsupported XHTML reading-order document")
                tokens = words(body_text(body))
                total_words += len(tokens)
                if total_words > MAX_WORDS:
                    raise AlignmentError("EPUB word count exceeds preview limit")
                sections.append(Section(index, path, tokens))
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError):
        raise EpubError("Invalid or unsupported EPUB reading-order archive") from None
    return inventory, sections


def shingles(tokens):
    for index in range(len(tokens) - ANCHOR_WORDS + 1):
        yield index, tokens[index:index + ANCHOR_WORDS]


def unique_transcript(windows):
    digest = hashlib.sha256()
    cues, unique = [], {}
    total_words = total_bytes = 0
    for window in windows:
        encoded = json.dumps(window, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        total_bytes += len(encoded)
        if total_bytes > MAX_TRANSCRIPT_BYTES:
            raise AlignmentError("Retained transcript exceeds preview size limit")
        digest.update(encoded + b"\n")
        for cue in window["cues"]:
            tokens = words(cue["text"])
            total_words += len(tokens)
            if total_words > MAX_WORDS or len(cues) >= MAX_CUES:
                raise AlignmentError("Retained transcript exceeds preview word or cue limit")
            cue_index = len(cues)
            cues.append((cue["start_ms"], cue["end_ms"], len(tokens)))
            for offset, key in shingles(tokens):
                unique[key] = None if key in unique else (cue_index, offset)
    return cues, unique, digest.hexdigest()


def match_anchors(sections, windows):
    cues, transcript, digest = unique_transcript(windows)
    occurrences = {}
    for section in sections:
        for offset, key in shingles(section.words):
            if transcript.get(key) is not None:
                occurrences[key] = None if key in occurrences else (section.spine_index, offset)
    by_cue = {}
    conflicts = set()
    for key, location in occurrences.items():
        if location is None:
            continue
        cue_index, cue_offset = transcript[key]
        section, offset = location
        diagonal = (section, offset - cue_offset)
        previous = by_cue.get(cue_index)
        if previous is None:
            by_cue[cue_index] = (diagonal, [cue_offset])
        elif previous[0] != diagonal:
            conflicts.add(cue_index)
        else:
            previous[1].append(cue_offset)

    candidates = []
    for cue_index, (diagonal, offsets) in sorted(by_cue.items()):
        if cue_index in conflicts:
            continue
        offsets.sort()
        runs = []
        for offset in offsets:
            if runs and offset <= runs[-1][1]:
                runs[-1] = (runs[-1][0], offset + ANCHOR_WORDS)
            else:
                runs.append((offset, offset + ANCHOR_WORDS))
        first, last = max(runs, key=lambda run: (run[1] - run[0], -run[0]))
        section, shift = diagonal
        candidates.append((cue_index, (section, shift + first), (section, shift + last), first, last))

    rejected = set()
    furthest = None
    for cue_index, start, end, _, _ in candidates:
        if furthest is not None and start < furthest:
            rejected.add(cue_index)
        furthest = end if furthest is None else max(furthest, end)
    earliest = None
    for cue_index, start, end, _, _ in reversed(candidates):
        if earliest is not None and end > earliest:
            rejected.add(cue_index)
        earliest = start if earliest is None else min(earliest, start)

    anchors = []
    paths = {section.spine_index: section.path for section in sections}
    for cue_index, start, end, first, last in candidates:
        if cue_index in rejected:
            continue
        start_ms, end_ms, _ = cues[cue_index]
        anchors.append({"cue_index": cue_index, "start_ms": start_ms, "end_ms": end_ms,
                        "spine_index": start[0], "path": paths[start[0]],
                        "ebook_word_start": start[1], "ebook_word_end": end[1],
                        "cue_word_start": first, "cue_word_end": last})
    return {"transcript_sha256": digest, "cue_count": len(cues),
            "eligible_cue_count": sum(count >= ANCHOR_WORDS for _, _, count in cues),
            "matched_cue_count": len(anchors), "conflicting_cue_count": len(conflicts | rejected),
            "anchors": anchors}


def preview(stream, windows):
    inventory, sections = read_sections(stream)
    result = match_anchors(sections, windows)
    matched_sections = {anchor["spine_index"] for anchor in result["anchors"]}
    return {"schema": SCHEMA, "epub_sha256": inventory["sha256"],
            "edition_verified": False, "anchor_words": ANCHOR_WORDS,
            "ebook_word_count": sum(len(section.words) for section in sections),
            "section_count": len(sections), "matched_section_count": len(matched_sections),
            **result}
