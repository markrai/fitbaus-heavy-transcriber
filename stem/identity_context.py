import re

from .tokenizer import Kind, tokenize

CONTEXT_VERSION = "identity-context-v1"
MAX_CONTEXT_CHARS = 4096
NAMED_CLAUSE = re.compile(r",[ \t]+(?:where|which)[ \t]+", re.IGNORECASE | re.ASCII)
RESTATEMENT = re.compile(r",[ \t]+or[ \t]+", re.IGNORECASE | re.ASCII)
PROSE_TAIL = re.compile(r",[ \t]+(?:into|in|as|for|with)[ \t]+([a-zA-Z]+(?:[ \t]+[a-zA-Z]+){0,11}),?$",
                        re.IGNORECASE | re.ASCII)
EULER_RESTATEMENT = (
    (Kind.SYMBOL, "e"), (Kind.POWER_HINT, "^"), (Kind.SYMBOL, "i"),
    (Kind.SYMBOL, "pi"), (Kind.RELATION, "="), (Kind.OPERATOR, "-"),
    (Kind.NUMBER, "1"),
)


def signature(text):
    tokens = tokenize(text)
    if any(t.kind == Kind.WHITESPACE and any(c not in " \t" for c in t.source_text)
           for t in tokens):
        return None
    return tuple((t.kind, t.value) for t in tokens if t.kind != Kind.WHITESPACE)


def prose_words(text):
    tokens = signature(text)
    return bool(tokens) and all(kind is Kind.WORD for kind, value in tokens)


def named_clause_span(phrase):
    if len(phrase) > MAX_CONTEXT_CHARS:
        return None
    separators = list(NAMED_CLAUSE.finditer(phrase))
    if len(separators) != 1:
        return None
    marker = separators[0]
    tail = phrase[marker.end():]
    if not tail or not tail.strip() or any(c in tail for c in "\r\n;?!"):
        return None
    tokens = signature(tail)
    if not tokens or not any(kind is Kind.WORD for kind, value in tokens):
        return None
    if any(kind in (Kind.RELATION, Kind.OPERATOR, Kind.POWER, Kind.POWER_HINT, Kind.UNKNOWN)
           for kind, value in tokens):
        return None
    if tokens[0][0] not in (Kind.WORD, Kind.SYMBOL):
        return None
    return marker.start()


def corroborated_euler_span(phrase, first_signature):
    if len(phrase) > MAX_CONTEXT_CHARS:
        return None
    separators = list(RESTATEMENT.finditer(phrase))
    if len(separators) != 1:
        return None
    marker = separators[0]
    if signature(phrase[:marker.start()]) != first_signature:
        return None
    rest = phrase[marker.end():]
    if signature(rest) == EULER_RESTATEMENT:
        return marker.start()
    tail = PROSE_TAIL.search(rest)
    if tail is not None and prose_words(tail.group(1)):
        if signature(rest[:tail.start()]) == EULER_RESTATEMENT:
            return marker.start()
    return None
