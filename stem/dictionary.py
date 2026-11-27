from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

SCHEMA = "fitbaus.stem.dictionary/v1"
CURATED = Path(__file__).resolve().parent / "corpus" / "curated.json"
MAX_BYTES = 16 * 1024 * 1024
COMMANDS = frozenset({
    "frac", "sqrt", "pi", "alpha", "beta", "gamma", "delta", "lambda",
    "theta", "sigma", "mu", "rho", "omega", "Delta", "Sigma", "Omega",
    "hbar", "pm", "mp", "times", "cdot", "int", "sum", "lim", "infty",
    "to", "sin", "cos", "tan", "log", "ln", "partial", "leq", "geq",
    "neq", "approx", "propto", "left", "right",
    "Gamma", "Lambda", "Leftrightarrow", "Phi", "Pi", "Psi", "Rightarrow",
    "Theta", "Upsilon", "Xi", "arccos", "arcsin", "arctan", "ast",
    "cap", "cdots", "chi", "circ", "cong", "cosh", "cot",
    "csc", "cup", "det", "div", "emptyset", "epsilon", "equiv",
    "eta", "exists", "exp", "forall", "gcd", "gg", "in",
    "inf", "iota", "kappa", "land", "ldots", "leftarrow", "leftrightarrow",
    "ll", "lor", "mathbb", "mathbf", "mathcal", "mathfrak", "mathit",
    "mathrm", "mathsf", "mathtt", "max", "mid", "min", "nabla",
    "neg", "ni", "notin", "nu", "oint", "oplus", "otimes",
    "parallel", "perp", "phi", "prod", "psi", "sec", "sim",
    "simeq", "sinh", "subset", "subseteq", "sup", "supset", "supseteq",
    "tanh", "tau", "upsilon", "varepsilon", "varphi", "varrho", "varsigma",
    "vartheta", "xi", "zeta",
    "Longleftrightarrow", "Longrightarrow", "Pr", "Vert", "aleph", "arg", "bar",
    "because", "bigcap", "bigcup", "dagger", "ddot", "ddots", "deg",
    "dim", "dot", "downarrow", "ell", "geqslant", "hat", "hom",
    "iiint", "iint", "ker", "langle", "lbrace", "lbrack", "lceil",
    "leqslant", "lfloor", "lg", "limits", "mapsto", "mathbin", "mathclose",
    "mathinner", "mathop", "mathopen", "mathord", "mathpunct", "mathrel", "models",
    "nexists", "notin", "ominus", "operatorname", "overline", "prec", "preceq",
    "qquad", "quad", "rangle", "rbrace", "rbrack", "rceil", "rfloor",
    "setminus", "star", "subsetneq", "succ", "succeq", "text", "therefore",
    "top", "uparrow", "vdash", "vdots", "vec",
})


def normalize_alias(text):
    if not isinstance(text, str):
        raise ValueError("Alias must be text")
    value = " ".join(text.lower().split())
    if len(value) > 512 or not re.fullmatch(r"[a-z0-9]+(?: [a-z0-9]+)*", value):
        raise ValueError("Unsupported spoken alias")
    if len(value.split()) < 3:
        raise ValueError("Alias too short")
    return value


def validate_latex(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 512:
        raise ValueError("Invalid LaTeX length")
    if not re.fullmatch(r"[A-Za-z0-9{}\[\]_^=+\-*/().,<>| !:;\\]+", text):
        raise ValueError("Unsupported LaTeX character")
    depth = 0
    for char in text:
        if char == "{":
            depth += 1
            if depth > 16:
                raise ValueError("LaTeX nesting limit")
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced LaTeX braces")
    if depth:
        raise ValueError("Unbalanced LaTeX braces")
    for match in re.finditer(r"\\([A-Za-z]+|.)?", text):
        if match.group(1) not in COMMANDS and match.group(1) not in {",", ";", "!"}:
            raise ValueError("Unsupported LaTeX command")
    return text


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    category: str
    latex: str
    aliases: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class Dictionary:
    entries: tuple[Entry, ...]
    aliases: MappingProxyType
    digest: str


def compile_dictionary(value):
    if not isinstance(value, dict) or set(value) != {"schema", "entries"} or value["schema"] != SCHEMA:
        raise ValueError("Unsupported dictionary schema")
    if not isinstance(value["entries"], list) or not value["entries"]:
        raise ValueError("Missing dictionary entries")
    entries, aliases, ids = [], {}, set()
    for row in value["entries"]:
        if not isinstance(row, dict) or set(row) != {"id", "name", "category", "latex", "aliases", "source"}:
            raise ValueError("Invalid dictionary entry")
        for field in ("id", "name", "category", "source"):
            if not isinstance(row[field], str) or not row[field].strip() or len(row[field]) > 128:
                raise ValueError("Invalid entry field: " + field)
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", row["id"]) or row["id"] in ids:
            raise ValueError("Invalid or duplicate entry ID")
        if row["source"] != "curated":
            raise ValueError("Unapproved corpus source")
        if not isinstance(row["aliases"], list) or not row["aliases"]:
            raise ValueError("Missing aliases")
        phrases = tuple(sorted({normalize_alias(a) for a in row["aliases"]}))
        entry = Entry(row["id"], row["name"], row["category"], validate_latex(row["latex"]), phrases, row["source"])
        ids.add(entry.id)
        entries.append(entry)
        for phrase in phrases:
            if phrase in aliases:
                raise ValueError("Ambiguous alias: " + phrase)
            aliases[phrase] = entry
    entries.sort(key=lambda e: e.id)
    canonical = {"schema": SCHEMA, "entries": [
        {"id": e.id, "name": e.name, "category": e.category, "latex": e.latex,
         "aliases": list(e.aliases), "source": e.source} for e in entries]}
    raw = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return Dictionary(tuple(entries), MappingProxyType(aliases), hashlib.sha256(raw).hexdigest())


def load_dictionary(path=CURATED):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Dictionary size limit")
    return compile_dictionary(json.loads(raw))
