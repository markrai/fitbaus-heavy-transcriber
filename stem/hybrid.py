from dataclasses import dataclass
import re

from .corpus_model import ROOT, digest
from .expression import structural_key
from .identity_context import (CONTEXT_VERSION, corroborated_euler_span, named_clause_span)
from .matcher import INTRO, Match, recognize, sentence_candidates
from .parser import MAX_PARSE_CHARS, ParseError, parse_expression
from .qualify_recognition import FIXTURES, build_review_dictionary
from .tokenizer import Kind, tokenize
from .structural_rules import EXPANDED_RULES
from .prose_context import PROSE_CONTEXT_VERSION

HYBRID_VERSION = "verified-identity-expanded-v2"
MAX_NARRATION_CHARS = 32768

EULER = "algebra.euler:standard"
PYTHAGORAS = "geometry.pythagoras:standard"
MASS_ENERGY = "physics.mass_energy:standard"

RULES = (
    (EULER, "a4e3a8c63be4bd411a2319baa72c998beb52782ffa2494e528ac12f6b5ea0775",
     r"e^{i\pi}+1=0", "e^(i*pi)+1=0"),
    (PYTHAGORAS, "8ab9fc5c5c1c502f7f8b11726b83adfd27f023521561fa9b7fa600bb95d4301d",
     "a^2+b^2=c^2", "a^2+b^2=c^2"),
    (MASS_ENERGY, "27277ed5f7e4a67ad39b1b7224f8517cdc1cc4d74b9373849c53c26fbbac4849",
     "E=mc^2", "E=m*c^2"),
) + EXPANDED_RULES

NAMED_INTRO = re.compile(
    r"(?:(?:euler['’]s identity)|(?:the pythagorean theorem))"
    r"(?:[ \t]+is(?:[ \t]+given[ \t]+by)?|:)[ \t]+",
    re.IGNORECASE | re.ASCII,
)
EULER_SHORT = (
    (Kind.SYMBOL, "e"), (Kind.POWER_HINT, "^"), (Kind.SYMBOL, "i"),
    (Kind.SYMBOL, "pi"), (Kind.OPERATOR, "+"), (Kind.NUMBER, "1"),
    (Kind.RELATION, "="), (Kind.NUMBER, "0"),
)


@dataclass(frozen=True)
class IdentityRule:
    id: str
    latex: str
    key: tuple
    mathematical_sha256: str


def pythagorean_variables(key):
    if len(key) != 3 or key[:2] != ("relation", ("=",)) or len(key[2]) != 2:
        return None
    lhs, rhs = key[2]
    if len(lhs) != 4 or lhs[:2] != ("binary", "+"):
        return None
    variables = []
    for term in (lhs[2], lhs[3], rhs):
        if (len(term) != 3 or term[0] != "power" or term[2] != ("number", "2")
                or len(term[1]) != 2 or term[1][0] != "symbol"):
            return None
        name = term[1][1]
        if not re.fullmatch(r"[a-df-hj-z]", name):
            return None
        variables.append(name)
    if len(set(variables)) != 3:
        return None
    return tuple(variables)


@dataclass(frozen=True)
class HybridRecognizer:
    dictionary: object
    rules: tuple[IdentityRule, ...]
    policy_sha256: str

    def resolve(self, phrase, named):
        try:
            tree = parse_expression(phrase)
            key = structural_key(tree, phrase)
        except ParseError:
            key = None
        candidates = set()
        for rule in self.rules:
            if named is not None and rule.id != named:
                continue
            if key == rule.key:
                candidates.add((rule.id, rule.latex))
            elif key is not None and rule.id == PYTHAGORAS and named == PYTHAGORAS:
                variables = pythagorean_variables(key)
                if variables is not None:
                    a, b, c = variables
                    candidates.add((rule.id, f"{a}^2+{b}^2={c}^2"))
            elif rule.id == EULER and named == EULER and key is None:
                tokens = tokenize(phrase)
                if (all(t.kind != Kind.WHITESPACE or all(c in " \t" for c in t.source_text)
                        for t in tokens)
                        and tuple((t.kind, t.value) for t in tokens if t.kind != Kind.WHITESPACE) == EULER_SHORT):
                    candidates.add((rule.id, rule.latex))
        return candidates

    def recognize(self, text):
        if not isinstance(text, str) or len(text) > MAX_NARRATION_CHARS:
            raise ValueError("Invalid hybrid narration source")
        if any(c == "\x00" or 0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise ValueError("Invalid hybrid narration character")
        exact = recognize(text, self.dictionary)
        matches = list(exact)
        for offset, fragment in sentence_candidates(text):
            trimmed = fragment.strip()
            if not trimmed or len(trimmed) > MAX_PARSE_CHARS or "\n" in trimmed or "\r" in trimmed:
                continue
            start = offset + len(fragment) - len(fragment.lstrip())
            end = start + len(trimmed)
            if any(start < match.end and match.start < end for match in exact):
                continue
            named = None
            intro = NAMED_INTRO.match(trimmed)
            if intro is not None:
                named = EULER if intro.group().lower().startswith("euler") else PYTHAGORAS
            else:
                intro = INTRO.match(trimmed)
            prefix = intro.end() if intro else 0
            phrase = trimmed[prefix:]
            if not phrase or not phrase.strip():
                continue
            try:
                candidates = self.resolve(phrase, named)
            except ValueError:
                continue
            if not candidates:
                try:
                    boundary = named_clause_span(phrase) if named is not None else corroborated_euler_span(phrase, EULER_SHORT)
                    if boundary is not None:
                        shortened = phrase[:boundary]
                        candidates = self.resolve(shortened, named if named is not None else EULER)
                        if candidates:
                            end = start + prefix + boundary
                except ValueError:
                    continue
            if len(candidates) == 1:
                identity, latex = next(iter(candidates))
                begin = start + prefix
                matches.append(Match(begin, end, text[begin:end], identity, latex))
        return tuple(sorted(matches, key=lambda match: (match.start, match.end)))


def build_hybrid(root=ROOT, fixtures=FIXTURES):
    dictionary, rows, binding = build_review_dictionary(root, fixtures)
    indexed = {row["id"]: row for row in rows}
    rules = []
    for identity, expected_digest, latex, canonical in RULES:
        row = indexed.get(identity)
        if (row is None or row["latex"] != latex or row["mathematical_sha256"] != expected_digest):
            raise ValueError("Stale structural identity rule: " + identity)
        key = structural_key(parse_expression(canonical), canonical)
        rules.append(IdentityRule(identity, latex, key, expected_digest))
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("Duplicate structural representation rule")
    if len({rule.key for rule in rules}) != len(rules):
        raise ValueError("Conflicting structural identity rules")
    policy = digest({"version": HYBRID_VERSION, "dictionary": dictionary.digest, "rules": RULES,
                     "named_intro": NAMED_INTRO.pattern, "context_version": CONTEXT_VERSION,
                     "prose_context_version": PROSE_CONTEXT_VERSION,
                     "euler_short": [(kind.value, value) for kind, value in EULER_SHORT],
                     "substitution": "named-pythagoras-distinct-lowercase-ascii-except-e-i"})
    return HybridRecognizer(dictionary, tuple(rules), policy), rows, binding
