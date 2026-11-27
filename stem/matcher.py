from dataclasses import dataclass
import re

from .dictionary import Dictionary, normalize_alias

MATCHER_VERSION = "sentence-v1"
BOUNDARY = re.compile(r"[^.!?;\r\n]+")
INTRO = re.compile(r"(?:^|[ \t])(?:equation is|formula is|given by|showed that|states that)\s+", re.IGNORECASE)


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    source_text: str
    dictionary_id: str
    latex: str


def recognize(text: str, dictionary: Dictionary) -> tuple[Match, ...]:
    if not isinstance(text, str):
        raise ValueError("Narration must be text")
    matches = []
    for sentence in BOUNDARY.finditer(text):
        fragment = sentence.group()
        starts = [0]
        starts.extend(m.end() for m in INTRO.finditer(fragment))
        starts.extend(m.end() for m in re.finditer(r":\s+", fragment))
        found = []
        for offset in sorted(set(starts)):
            tail = fragment[offset:]
            trimmed = tail.strip()
            if not trimmed:
                continue
            try:
                entry = dictionary.aliases.get(normalize_alias(trimmed))
            except ValueError:
                continue
            if entry is None:
                continue
            start = sentence.start() + offset + len(tail) - len(tail.lstrip())
            end = start + len(trimmed)
            found.append(Match(start, end, text[start:end], entry.id, entry.latex))
        if len(found) == 1:
            matches.append(found[0])
    return tuple(matches)
