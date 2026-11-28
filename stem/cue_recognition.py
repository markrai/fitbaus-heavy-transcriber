from dataclasses import dataclass
import re

from transcriber.contract import Cue, TranscriptWindow

from .hybrid import NAMED_INTRO, HybridRecognizer
from .matcher import INTRO, sentence_candidates
from .tokenizer import Kind, tokenize

CUE_RECOGNITION_VERSION = "bounded-cue-assembly-v1"
MAX_JOIN_CUES = 3
MAX_GAP_MS = 1000
MAX_JOIN_DURATION_MS = 30000
MAX_JOIN_CHARS = 3602

LEADING_CONTEXT = re.compile(r"(?:or|where|which)[ \t]+", re.IGNORECASE | re.ASCII)
TRAILING_SCOPE = frozenset({"quantity", "subscript", "all_divided_by"})
CONTINUATION_KINDS = frozenset({Kind.OPERATOR, Kind.RELATION, Kind.POWER, Kind.POWER_HINT})


@dataclass(frozen=True, slots=True)
class CueSpan:
    cue_index: int
    start: int
    end: int
    start_ms: int
    end_ms: int
    source_text: str


@dataclass(frozen=True, slots=True)
class CueMatch:
    dictionary_id: str
    latex: str
    spans: tuple[CueSpan, ...]
    evidence_start_cue: int
    evidence_end_cue: int


@dataclass(frozen=True, slots=True)
class WindowRecognition:
    book_key: str
    window_start_ms: int
    window_end_ms: int
    policy_sha256: str
    matches: tuple[CueMatch, ...]


def significant(text):
    return tuple(token for token in tokenize(text) if token.kind != Kind.WHITESPACE)


def linked(left, right, left_tokens, right_tokens):
    if right.start_ms - left.end_ms > MAX_GAP_MS:
        return False
    lhs, rhs = left.text.strip(), right.text.strip()
    last, first = left_tokens[-1], right_tokens[0]
    if last.kind in CONTINUATION_KINDS or first.kind in CONTINUATION_KINDS:
        return True
    if last.kind is Kind.SCOPE and last.value in TRAILING_SCOPE:
        return True
    if last.kind is Kind.GROUP and last.value in ("(", "["):
        return True
    if INTRO.fullmatch(lhs + " ") or NAMED_INTRO.fullmatch(lhs + " "):
        return True
    return lhs.endswith(",") and LEADING_CONTEXT.match(rhs) is not None


def join_source(cues):
    pieces, positions = [], []
    cursor = 0
    for cue in cues:
        if pieces:
            cursor += 1
        positions.append(cursor)
        pieces.append(cue.text)
        cursor += len(cue.text)
    return " ".join(pieces), tuple(positions)


def project(match, cues, positions, first):
    spans = []
    for index, (cue, position) in enumerate(zip(cues, positions)):
        start = max(0, match.start - position)
        end = min(len(cue.text), match.end - position)
        if start < end:
            spans.append(CueSpan(first + index, start, end, cue.start_ms, cue.end_ms,
                                 cue.text[start:end]))
    if not spans:
        raise ValueError("Recognition has no source cue spans")
    return CueMatch(match.dictionary_id, match.latex, tuple(spans), first, first + len(cues) - 1)


def single_candidate(source):
    candidates = tuple((offset, fragment) for offset, fragment in sentence_candidates(source)
                       if fragment.strip())
    if len(candidates) != 1 or candidates[0][0] != 0:
        return False
    fragment = candidates[0][1]
    remainder = source[len(fragment):].strip()
    return remainder in ("", ".", "!")


def recognize_run(cues, first, hybrid):
    if len(cues) == 1:
        return tuple(project(match, cues, (0,), first) for match in hybrid.recognize(cues[0].text))
    if len(cues) > MAX_JOIN_CUES or cues[-1].end_ms - cues[0].start_ms > MAX_JOIN_DURATION_MS:
        return ()
    if any(cue.text.rstrip().endswith((".", "!", "?", ";", "…")) for cue in cues[:-1]):
        return ()
    source, positions = join_source(cues)
    if len(source) > MAX_JOIN_CHARS or any(c in source for c in "\r\n"):
        return ()
    if not single_candidate(source):
        return ()
    matches = hybrid.recognize(source)
    if len(matches) != 1:
        return ()
    return (project(matches[0], cues, positions, first),)


def recognize_window(window: TranscriptWindow, hybrid: HybridRecognizer) -> WindowRecognition:
    if type(window) is not TranscriptWindow or any(type(cue) is not Cue for cue in window.cues):
        raise ValueError("Expected a validated transcript window")
    window = TranscriptWindow(window.identity, window.start_ms, window.end_ms, window.cues)
    tokens = tuple(significant(cue.text) for cue in window.cues)
    if any(not row for row in tokens):
        raise ValueError("Empty significant cue")
    matches = []
    first = 0
    for index in range(1, len(window.cues) + 1):
        if index < len(window.cues) and linked(window.cues[index - 1], window.cues[index],
                                                tokens[index - 1], tokens[index]):
            continue
        matches.extend(recognize_run(window.cues[first:index], first, hybrid))
        first = index
    return WindowRecognition(window.identity.cache_key(), window.start_ms, window.end_ms,
                             hybrid.policy_sha256, tuple(matches))
