from dataclasses import dataclass
import re

from .dictionary import Dictionary, normalize_alias

MATCHER_VERSION = "sentence-v2"
BOUNDARY = re.compile(r"[.!?]+(?=\s|$)")
INTRO = re.compile(
    r"(?:(?:the[ \t]+)?(?:equation|formula)(?:[ \t]+is(?:[ \t]+given[ \t]+by)?|:)"
    r"|einstein[ \t]+showed[ \t]+that"
    r"|newton['’]s[ \t]+formula[ \t]+is)[ \t]+",
    re.IGNORECASE | re.ASCII,
)
CONTINUATION = re.compile(
    r"\s*(?:(?:plus|minus|times|divided[ \t]+by|multiplied[ \t]+by|over|"
    r"raised[ \t]+to|to[ \t]+the[ \t]+power|equals|equal[ \t]+to|"
    r"greater[ \t]+than|less[ \t]+than|and|or|close[ \t]+parenthesis)\b|[+\-*/=])",
    re.IGNORECASE,
)
INCOMPLETE = re.compile(
    r"(?:\b(?:plus|minus|times|divided[ \t]+by|multiplied[ \t]+by|over|"
    r"raised[ \t]+to|power[ \t]+of|equals|equal[ \t]+to|"
    r"greater[ \t]+than|less[ \t]+than|and|or|open[ \t]+parenthesis)|[+\-*/=])\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    source_text: str
    dictionary_id: str
    latex: str


def sentence_candidates(text):
    cursor = 0
    previous_incomplete = False
    for boundary in BOUNDARY.finditer(text):
        fragment = text[cursor:boundary.start()]
        if (boundary.group() in (".", "!") and not previous_incomplete
                and not CONTINUATION.match(text, boundary.end())):
            yield cursor, fragment
        previous_incomplete = INCOMPLETE.search(fragment) is not None
        cursor = boundary.end()
    if cursor < len(text) and not previous_incomplete:
        yield cursor, text[cursor:]


def recognize(text: str, dictionary: Dictionary) -> tuple[Match, ...]:
    if not isinstance(text, str):
        raise ValueError("Narration must be text")
    matches = []
    for offset, fragment in sentence_candidates(text):
        trimmed = fragment.strip()
        if not trimmed or "\r" in trimmed or "\n" in trimmed:
            continue
        start = offset + len(fragment) - len(fragment.lstrip())
        starts = [0]
        intro = INTRO.match(trimmed)
        if intro is not None:
            starts.append(intro.end())
        found = []
        for prefix in starts:
            phrase = trimmed[prefix:]
            try:
                entry = dictionary.aliases.get(normalize_alias(phrase))
            except ValueError:
                continue
            if entry is None:
                continue
            begin = start + prefix
            end = begin + len(phrase)
            found.append(Match(begin, end, text[begin:end], entry.id, entry.latex))
        if len(found) == 1:
            matches.append(found[0])
    return tuple(matches)
