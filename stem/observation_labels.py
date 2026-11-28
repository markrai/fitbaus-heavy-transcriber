import hashlib
import json
from pathlib import Path
import re

from .corpus_model import strict_object
from .hybrid import PYTHAGORAS
from .qualify_recognition import (
    Case, Expected, MAX_CASES, MAX_OBSERVED_BYTES, MAX_TEXT, OBSERVED_SCHEMA,
    fields, load_observations, text_value,
)

SCHEMA = "fitbaus.stem.recognition-observations/v2"
PYTHAGOREAN_LATEX = re.compile(r"([a-df-hj-z])\^2\+([a-df-hj-z])\^2=([a-df-hj-z])\^2")


def label_latex(identity, latex, canonical):
    if not isinstance(latex, str):
        raise ValueError("Observation LaTeX must be text")
    if latex == canonical:
        return latex
    variant = PYTHAGOREAN_LATEX.fullmatch(latex) if identity == PYTHAGORAS and len(latex) <= 64 else None
    if variant is None or len(set(variant.groups())) != 3:
        raise ValueError("Unsupported observation notation")
    return latex


def load_hybrid_observations(path, dictionary):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_OBSERVED_BYTES + 1)
    if len(raw) > MAX_OBSERVED_BYTES:
        raise ValueError("Observation file size limit")
    value = json.loads(raw, object_pairs_hook=strict_object,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))
    if not isinstance(value, dict):
        raise ValueError("Invalid observation object")
    if value.get("schema") == OBSERVED_SCHEMA:
        cases, metadata = load_observations(path, dictionary)
        if metadata["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("Observation file changed during read")
        return cases, {**metadata, "schema": OBSERVED_SCHEMA}
    fields(value, {"schema", "provenance", "cases"}, "observations")
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported observation schema")
    provenance = value["provenance"]
    fields(provenance, {"source", "transcriber", "labeling_method"}, "observation provenance")
    for name, item in provenance.items():
        text_value(item, 2048, name)
    rows = value["cases"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CASES:
        raise ValueError("Invalid observation case count")
    entries = {entry.id: entry for entry in dictionary.entries}
    ids, cases = set(), []
    for row in rows:
        fields(row, {"id", "text", "expected"}, "observation case")
        key = text_value(row["id"], 128, "case ID")
        if key in ids:
            raise ValueError("Duplicate observation case ID")
        ids.add(key)
        text = text_value(row["text"], MAX_TEXT, "observation text")
        if not isinstance(row["expected"], list) or len(row["expected"]) > 256:
            raise ValueError("Invalid observation annotations")
        annotations, previous_end = [], 0
        for match in row["expected"]:
            fields(match, {"id", "start", "end", "latex"}, "observation annotation")
            identity, start, end = match["id"], match["start"], match["end"]
            if (not isinstance(identity, str) or identity not in entries or type(start) is not int
                    or type(end) is not int or not previous_end <= start < end <= len(text)
                    or not text[start:end].strip()):
                raise ValueError("Invalid observation span or representation")
            latex = label_latex(identity, match["latex"], entries[identity].latex)
            annotations.append(Expected(identity, start, end, latex))
            previous_end = end
        cases.append(Case(key, "operator_labeled_observations", text, tuple(annotations)))
    return cases, {"schema": SCHEMA, "sha256": hashlib.sha256(raw).hexdigest(),
                   "provenance": provenance, "provenance_verified": False}
