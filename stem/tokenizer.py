from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

TOKENIZER_VERSION = "math-tokens-v1"
MAX_SOURCE_CHARS = 32768
MAX_TOKENS = 8192


class Kind(str, Enum):
    NUMBER = "number"
    SYMBOL = "symbol"
    WORD = "word"
    OPERATOR = "operator"
    RELATION = "relation"
    POWER = "power"
    POWER_HINT = "power_hint"
    EXPONENT = "exponent"
    SUBSCRIPT = "subscript"
    FUNCTION = "function"
    GROUP = "group"
    SCOPE = "scope"
    MODIFIER = "modifier"
    WHITESPACE = "whitespace"
    PUNCTUATION = "punctuation"
    UNKNOWN = "unknown"


class Form(str, Enum):
    SPOKEN = "spoken"
    SYMBOLIC = "symbolic"
    RAW = "raw"


@dataclass(frozen=True)
class Token:
    kind: Kind
    value: str
    form: Form
    start: int
    end: int
    source_text: str


NUMBERS = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
GREEK = (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "omicron pi rho sigma tau upsilon phi chi psi omega"
).split()
GREEK_CHARS = "αβγδεζηθικλμνξοπρστυφχψω"
GREEK_UPPER = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"

_WORDS = {
    **{word: (Kind.NUMBER, str(index)) for index, word in enumerate(NUMBERS)},
    **{word: (Kind.NUMBER, str(index * 10)) for index, word in enumerate(
        "twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)},
    **{word: (Kind.SYMBOL, word) for word in GREEK},
    "plus": (Kind.OPERATOR, "+"),
    "minus": (Kind.OPERATOR, "-"),
    "negative": (Kind.OPERATOR, "-"),
    "positive": (Kind.OPERATOR, "+"),
    "times": (Kind.OPERATOR, "*"),
    "over": (Kind.OPERATOR, "/"),
    "equals": (Kind.RELATION, "="),
    "equal": (Kind.RELATION, "="),
    "squared": (Kind.EXPONENT, "2"),
    "cubed": (Kind.EXPONENT, "3"),
    "prime": (Kind.MODIFIER, "prime"),
    "capital": (Kind.MODIFIER, "uppercase"),
    "uppercase": (Kind.MODIFIER, "uppercase"),
    "lowercase": (Kind.MODIFIER, "lowercase"),
    "sub": (Kind.SCOPE, "subscript"),
    "subscript": (Kind.SCOPE, "subscript"),
    "infinity": (Kind.SYMBOL, "infinity"),
    **{word: (Kind.FUNCTION, canonical) for word, canonical in (
        ("sine", "sin"), ("sin", "sin"), ("cosine", "cos"), ("cos", "cos"),
        ("tangent", "tan"), ("tan", "tan"), ("log", "log"), ("ln", "ln"),
    )},
}

_PHRASES = {
    "is greater than or equal to": (Kind.RELATION, ">="),
    "is less than or equal to": (Kind.RELATION, "<="),
    "greater than or equal to": (Kind.RELATION, ">="),
    "less than or equal to": (Kind.RELATION, "<="),
    "is not equal to": (Kind.RELATION, "!="),
    "not equal to": (Kind.RELATION, "!="),
    "is greater than": (Kind.RELATION, ">"),
    "is less than": (Kind.RELATION, "<"),
    "greater than": (Kind.RELATION, ">"),
    "less than": (Kind.RELATION, "<"),
    "is equal to": (Kind.RELATION, "="),
    "equal to": (Kind.RELATION, "="),
    "at least": (Kind.RELATION, ">="),
    "at most": (Kind.RELATION, "<="),
    "is proportional to": (Kind.RELATION, "proportional"),
    "proportional to": (Kind.RELATION, "proportional"),
    "plus or minus": (Kind.OPERATOR, "+/-"),
    "minus or plus": (Kind.OPERATOR, "-/+"),
    "divided by": (Kind.OPERATOR, "/"),
    "multiplied by": (Kind.OPERATOR, "*"),
    "raised to the power of": (Kind.POWER, "^"),
    "raised to the power": (Kind.POWER, "^"),
    "to the power of": (Kind.POWER, "^"),
    "to the power": (Kind.POWER, "^"),
    "raised to": (Kind.POWER, "^"),
    "to the": (Kind.POWER_HINT, "^"),
    "square root": (Kind.FUNCTION, "sqrt"),
    "cube root": (Kind.FUNCTION, "cbrt"),
    "natural logarithm": (Kind.FUNCTION, "ln"),
    "open parenthesis": (Kind.GROUP, "("),
    "close parenthesis": (Kind.GROUP, ")"),
    "open bracket": (Kind.GROUP, "["),
    "close bracket": (Kind.GROUP, "]"),
    "end exponent": (Kind.SCOPE, "end_exponent"),
    "the quantity": (Kind.SCOPE, "quantity"),
    "all divided by": (Kind.SCOPE, "all_divided_by"),
    "h bar": (Kind.SYMBOL, "hbar"),
}

_SYMBOLS = {
    **{char: (Kind.SYMBOL, name) for char, name in zip(GREEK_CHARS, GREEK)},
    **{char: (Kind.SYMBOL, name.capitalize()) for char, name in zip(GREEK_UPPER, GREEK)},
    "ℏ": (Kind.SYMBOL, "hbar"),
    "∞": (Kind.SYMBOL, "infinity"),
    "+": (Kind.OPERATOR, "+"),
    "-": (Kind.OPERATOR, "-"),
    "−": (Kind.OPERATOR, "-"),
    "*": (Kind.OPERATOR, "*"),
    "×": (Kind.OPERATOR, "*"),
    "·": (Kind.OPERATOR, "dot"),
    "/": (Kind.OPERATOR, "/"),
    "÷": (Kind.OPERATOR, "/"),
    "±": (Kind.OPERATOR, "+/-"),
    "∓": (Kind.OPERATOR, "-/+"),
    "=": (Kind.RELATION, "="),
    "<": (Kind.RELATION, "<"),
    ">": (Kind.RELATION, ">"),
    "<=": (Kind.RELATION, "<="),
    ">=": (Kind.RELATION, ">="),
    "!=": (Kind.RELATION, "!="),
    "≤": (Kind.RELATION, "<="),
    "≥": (Kind.RELATION, ">="),
    "≠": (Kind.RELATION, "!="),
    "∝": (Kind.RELATION, "proportional"),
    "^": (Kind.POWER, "^"),
    "_": (Kind.SCOPE, "subscript"),
    "√": (Kind.FUNCTION, "sqrt"),
    "′": (Kind.MODIFIER, "prime"),
    **{char: (Kind.GROUP, char) for char in "()[]"},
}

_SUPERSCRIPT = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
_SUBSCRIPT = dict(zip("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_PHRASE_PATTERNS = tuple(
    (re.compile(r"[ \t]+".join(phrase.split()), re.IGNORECASE | re.ASCII), kind, value)
    for phrase, (kind, value) in sorted(
        _PHRASES.items(), key=lambda row: (-len(row[0].split()), -len(row[0]), row[0]))
)


def word_char(char):
    return char.isalpha() or unicodedata.category(char).startswith("M")


def phrase_at(text, start):
    for pattern, kind, value in _PHRASE_PATTERNS:
        match = pattern.match(text, start)
        if match is not None and (match.end() == len(text) or not word_char(text[match.end()])):
            if match.end() < len(text) and (text[match.end()].isdigit() or text[match.end()] == "_"):
                continue
            return match.end(), kind, value
    return None


def tokenize(text: str) -> tuple[Token, ...]:
    if not isinstance(text, str):
        raise ValueError("Tokenizer source must be text")
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError("Tokenizer source length limit")
    if any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise ValueError("Invalid tokenizer source character")
    tokens = []
    start = 0
    while start < len(text):
        if len(tokens) >= MAX_TOKENS:
            raise ValueError("Tokenizer token count limit")
        char = text[start]
        end = start + 1
        form = Form.RAW
        if char.isspace():
            while end < len(text) and text[end].isspace():
                end += 1
            kind, value = Kind.WHITESPACE, text[start:end]
        elif char in _SUPERSCRIPT or char in _SUBSCRIPT:
            table = _SUPERSCRIPT if char in _SUPERSCRIPT else _SUBSCRIPT
            while end < len(text) and text[end] in table:
                end += 1
            kind = Kind.EXPONENT if table is _SUPERSCRIPT else Kind.SUBSCRIPT
            value, form = "".join(table[c] for c in text[start:end]), Form.SYMBOLIC
        elif match := _NUMBER.match(text, start):
            end = match.end()
            kind, value, form = Kind.NUMBER, match.group(), Form.SYMBOLIC
        elif word_char(char):
            phrase = phrase_at(text, start) if char.isascii() else None
            if phrase is not None:
                end, kind, value = phrase
                form = Form.SPOKEN
            else:
                while end < len(text) and word_char(text[end]):
                    end += 1
                word = text[start:end]
                if word in _SYMBOLS:
                    kind, value = _SYMBOLS[word]
                    form = Form.SYMBOLIC
                elif word.isascii() and word.lower() in _WORDS:
                    kind, value = _WORDS[word.lower()]
                    form = Form.SPOKEN
                elif len(word) == 1 and word.isascii() and word.isalpha():
                    kind, value, form = Kind.SYMBOL, word, Form.SYMBOLIC
                else:
                    kind, value = Kind.WORD, word
        elif start + 2 <= len(text) and text[start:start + 2] in _SYMBOLS:
            end = start + 2
            kind, value = _SYMBOLS[text[start:end]]
            form = Form.SYMBOLIC
        elif char in _SYMBOLS:
            kind, value = _SYMBOLS[char]
            form = Form.SYMBOLIC
        elif unicodedata.category(char).startswith("P"):
            kind, value = Kind.PUNCTUATION, char
        else:
            kind, value = Kind.UNKNOWN, char
        tokens.append(Token(kind, value, form, start, end, text[start:end]))
        start = end
    return tuple(tokens)
