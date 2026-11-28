import re

from .identity_context import DISQUALIFYING_WORDS, named_clause_span
from .matcher import BOUNDARY, CONTINUATION, Match, sentence_candidates

PROSE_CONTEXT_VERSION = "bounded-referential-prose-v1"
MAX_EVIDENCE_CUES = 4
MAX_EVIDENCE_MS = 30000
MAX_EVIDENCE_GAP_MS = 1000

REFERENCE = re.compile(
    r"(?:the[ \t]+)?(?:equation|expression|formula|identity)[ \t]+"
    r"(?:written[ \t]+as[ \t]+|expressed[ \t]+as[ \t]+|represented[ \t]+by[ \t]+)?",
    re.IGNORECASE | re.ASCII,
)
THEOREM = re.compile(r"\bpythagorean[ \t]+theorem\b", re.IGNORECASE | re.ASCII)
TRIANGLE = re.compile(r"\bright[ \t]+triangles?\b", re.IGNORECASE | re.ASCII)
LEAD_IN = re.compile(
    r"\b(?:as(?:[ \t]+(?:something[ \t]+like|follows))?|namely|given[ \t]+by|written[ \t]+as)"
    r"[ \t]*[:,]?[ \t]*$",
    re.IGNORECASE | re.ASCII,
)
QUESTION = re.compile(
    r"what[ \t]+(?:is|about)[ \t]+the[ \t]+"
    r"(?:(?:geometric|physical|mathematical|algebraic)[ \t]+)?"
    r"(?:interpretation|meaning|significance)[ \t]+of[ \t]+"
    r"(?P<reference>euler['’]s[ \t]+(?:identity|formula)|(?:the[ \t]+)?pythagorean[ \t]+theorem|"
    r"the[ \t]+(?:equation|formula|expression|identity))[ \t]+"
    r"(?:(?:expressed|written|stated)[ \t]+(?:as[ \t]+|in[ \t]+the[ \t]+(?:usual|standard)[ \t]+(?:way|form),[ \t]+))?"
    r"(?P<phrase>.+)",
    re.IGNORECASE | re.ASCII,
)

EULER = "algebra.euler:standard"
PYTHAGORAS = "geometry.pythagoras:standard"


def preceding(cues, index):
    first = index
    while first > max(0, index - MAX_EVIDENCE_CUES + 1):
        prior = cues[first - 1]
        if (cues[first].start_ms - prior.end_ms > MAX_EVIDENCE_GAP_MS
                or cues[index].end_ms - prior.start_ms > MAX_EVIDENCE_MS
                or any(c in prior.text for c in "\r\n")):
            break
        first -= 1
    return first


def selected_match(text, start, end, named, hybrid):
    if not 0 <= start < end <= len(text):
        return None
    phrase = text[start:end]
    if phrase != phrase.strip():
        return None
    try:
        candidates = hybrid.resolve(phrase, named)
    except ValueError:
        return None
    if len(candidates) != 1:
        return None
    identity, latex = next(iter(candidates))
    return Match(start, end, phrase, identity, latex)


def reference_clause(text, hybrid):
    found = []
    for offset, fragment in sentence_candidates(text):
        trimmed = fragment.strip()
        prefix = REFERENCE.match(trimmed)
        if prefix is None or DISQUALIFYING_WORDS.search(trimmed):
            continue
        phrase = trimmed[prefix.end():]
        boundary = named_clause_span(phrase)
        if boundary is None:
            continue
        start = offset + len(fragment) - len(fragment.lstrip()) + prefix.end()
        match = selected_match(text, start, start + boundary, None, hybrid)
        if match is not None:
            found.append(match)
    return found


def named_triangle_clause(cues, index, first, hybrid):
    if first == index:
        return None
    text = cues[index].text
    prior = " ".join(cue.text for cue in cues[first:index])
    names = tuple(THEOREM.finditer(prior))
    if not names or not TRIANGLE.search(prior) or not LEAD_IN.search(prior):
        return None
    evidence = prior[names[-1].start():]
    if (DISQUALIFYING_WORDS.search(prior) or any(c in evidence for c in "?;")
            or re.search(r"\b(?:suppose|assume|if|whether|incorrectly|rather[ \t]+than|counterexample)\b",
                         prior, re.IGNORECASE)):
        return None
    trimmed = text.strip()
    candidates = tuple(sentence_candidates(trimmed))
    if len(candidates) != 1 or candidates[0][0] != 0:
        return None
    fragment = candidates[0][1].strip()
    if trimmed[len(candidates[0][1]):].strip() not in ("", ".", "!"):
        return None
    boundary = named_clause_span(fragment)
    if boundary is None:
        return None
    start = len(text) - len(text.lstrip())
    return selected_match(text, start, start + boundary, PYTHAGORAS, hybrid)


def interpretation_question(cues, index, first, hybrid):
    text = cues[index].text
    boundary = BOUNDARY.search(text)
    if (boundary is None or boundary.group() != "?" or CONTINUATION.match(text, boundary.end())
            or DISQUALIFYING_WORDS.search(text[boundary.end():])):
        return None
    fragment = text[:boundary.start()]
    prefixes = [("", index)]
    if first < index:
        previous = cues[index - 1].text
        boundaries = tuple(BOUNDARY.finditer(previous))
        tail = previous[boundaries[-1].end():] if boundaries else previous
        if tail.strip():
            prefixes.append((tail.strip() + " ", index - 1))
    for prefix, evidence_start in prefixes:
        combined = prefix + fragment
        match = QUESTION.fullmatch(combined.strip())
        if match is None or DISQUALIFYING_WORDS.search(combined):
            continue
        leading = len(combined) - len(combined.lstrip())
        start = leading + match.start("phrase") - len(prefix)
        end = leading + match.end("phrase") - len(prefix)
        reference = match.group("reference").lower()
        named = EULER if reference.startswith("euler") else PYTHAGORAS if "pythagorean" in reference else None
        result = selected_match(text, start, end, named, hybrid)
        if result is not None:
            return result, evidence_start
    return None


def recognize_prose(cues, index, hybrid):
    text = cues[index].text
    if any(c in text for c in "\r\n") or len(text) > 1200:
        return ()
    first = preceding(cues, index)
    found = [(match, index) for match in reference_clause(text, hybrid)]
    triangle = named_triangle_clause(cues, index, first, hybrid)
    if triangle is not None:
        found.append((triangle, first))
    question = interpretation_question(cues, index, first, hybrid)
    if question is not None:
        found.append(question)
    unique = {(match.start, match.end, match.dictionary_id, match.latex): (match, evidence)
              for match, evidence in found}
    return tuple(unique.values()) if len(unique) == 1 else ()
