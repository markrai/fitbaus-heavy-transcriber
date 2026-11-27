import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

from .dictionary import normalize_alias

ROOT = Path(__file__).resolve().parent / "corpus"
SCHEMA = "fitbaus.stem.concept/v1"
MAX_FILE = 256 * 1024
MAX_CONCEPTS = 10000
ID = re.compile(r"[a-z][a-z0-9_]*")
CONCEPT_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
DISCIPLINES = frozenset({"mathematics", "physics", "chemistry", "biology", "computer_science", "engineering"})
CONCEPT_FIELDS = {"schema", "id", "name", "discipline", "subject", "tags", "alternate_names", "representations"}
REP_FIELDS = {"id", "latex", "conditions", "symbols", "spoken_aliases", "references", "mathematical_review", "recognition_review"}
REVIEW_FIELDS = {"status", "digest", "method", "evidence"}


def fail(message):
    raise ValueError(message)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        fail("Corpus file size limit: " + str(path))
    return json.loads(raw, object_pairs_hook=strict_object,
                      parse_constant=lambda value: fail("Nonfinite JSON constant: " + value))


def fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        fail("Invalid fields: " + label)


def string(value, limit, label):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or 127 <= ord(char) <= 159
                   or 0xD800 <= ord(char) <= 0xDFFF or char == "\ufffd" for char in value)):
        fail("Invalid text: " + label)
    return value


def identifier(value, label, pattern=ID, limit=64):
    if not pattern.fullmatch(string(value, limit, label)):
        fail("Invalid identifier: " + label)
    return value


def sequence(value, low, high, label):
    if not isinstance(value, list) or not low <= len(value) <= high:
        fail("Invalid list: " + label)
    return value


def strings(value, low, high, limit, label, ids=False):
    items = sequence(value, low, high, label)
    for item in items:
        if ids:
            identifier(item, label)
        else:
            string(item, limit, label)
    if len(set(items)) != len(items):
        fail("Duplicate item: " + label)
    return items


def digest(value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def mathematical_digest(concept, rep):
    return digest({
        "schema": SCHEMA, "concept_id": concept["id"], "name": concept["name"],
        "discipline": concept["discipline"], "subject": concept["subject"],
        "representation_id": rep["id"], "latex": rep["latex"],
        "conditions": rep["conditions"], "symbols": rep["symbols"],
        "references": rep["references"],
    })


def recognition_digest(concept, rep):
    return digest({
        "mathematics": mathematical_digest(concept, rep),
        "spoken_aliases": sorted(normalize_alias(alias) for alias in rep["spoken_aliases"]),
    })


def validate_review(review, expected_digest, label):
    fields(review, REVIEW_FIELDS, label)
    methods = strings(review["method"], 0, 16, 128, label + ".method")
    evidence = strings(review["evidence"], 0, 32, 2048, label + ".evidence")
    status = review["status"]
    if status not in ("pending", "approved", "rejected"):
        fail("Invalid review status: " + label)
    if status == "pending":
        if review["digest"] is not None or methods or evidence:
            fail("Pending review cannot carry approval evidence: " + label)
    elif review["digest"] != expected_digest or not methods or not evidence:
        fail("Stale or incomplete review: " + label)


def source_registry(root):
    value = read_json(root / "sources.json")
    fields(value, {"schema", "sources"}, "sources")
    if value["schema"] != "fitbaus.stem.sources/v1":
        fail("Invalid source registry schema")
    result = {}
    for row in sequence(value["sources"], 1, 256, "sources"):
        if not isinstance(row, dict):
            fail("Invalid source record")
        key = identifier(row.get("id"), "source id")
        status = row.get("status")
        if key in result or status not in ("admitted", "candidate_only", "pending_review"):
            fail("Invalid or duplicate source: " + key)
        result[key] = status
    return result


def validate_concept(concept, path, sources, aliases):
    fields(concept, CONCEPT_FIELDS, "concept")
    if concept["schema"] != SCHEMA:
        fail("Invalid concept schema")
    key = identifier(concept["id"], "concept id", CONCEPT_ID, 128)
    string(concept["name"], 128, "name")
    discipline = identifier(concept["discipline"], "discipline")
    subject = identifier(concept["subject"], "subject")
    if discipline not in DISCIPLINES:
        fail("Unknown discipline: " + discipline)
    expected = (discipline, subject, key.rsplit(".", 1)[-1] + ".json")
    if tuple(path.parts) != expected:
        fail("Concept path does not match metadata: " + key)
    strings(concept["tags"], 0, 32, 64, "tags", ids=True)
    strings(concept["alternate_names"], 0, 64, 128, "alternate_names")
    rep_ids = set()
    for rep in sequence(concept["representations"], 1, 64, "representations"):
        fields(rep, REP_FIELDS, "representation")
        rep_id = identifier(rep["id"], "representation id")
        full_id = key + ":" + rep_id
        if rep_id in rep_ids:
            fail("Duplicate representation: " + full_id)
        rep_ids.add(rep_id)
        string(rep["latex"], 1024, "latex")
        strings(rep["conditions"], 1, 32, 1024, "conditions")
        symbols = rep["symbols"]
        if not isinstance(symbols, dict) or not 1 <= len(symbols) <= 64:
            fail("Invalid symbols: " + full_id)
        for symbol, meaning in symbols.items():
            string(symbol, 64, "symbol")
            string(meaning, 512, "symbol meaning")
        normalized = set()
        for alias in strings(rep["spoken_aliases"], 0, 256, 512, "spoken_aliases"):
            phrase = normalize_alias(alias)
            if phrase in normalized or phrase in aliases:
                fail("Ambiguous or duplicate spoken alias: " + phrase)
            normalized.add(phrase)
            aliases[phrase] = full_id
        references = sequence(rep["references"], 1, 32, "references")
        referenced = set()
        for reference in references:
            fields(reference, {"source_id", "locator"}, "reference")
            source = identifier(reference["source_id"], "source id")
            locator = string(reference["locator"], 2048, "reference locator")
            if source not in sources or (source, locator) in referenced:
                fail("Unknown or duplicate reference: " + source)
            referenced.add((source, locator))
        validate_review(rep["mathematical_review"], mathematical_digest(concept, rep), full_id + ".mathematical_review")
        validate_review(rep["recognition_review"], recognition_digest(concept, rep), full_id + ".recognition_review")
        if rep["recognition_review"]["status"] == "approved" and (
                rep["mathematical_review"]["status"] != "approved" or not normalized):
            fail("Recognition approval requires approved mathematics and aliases: " + full_id)
        if rep["mathematical_review"]["status"] == "approved" and any(
                sources[source] != "admitted" for source, _ in referenced):
            fail("Mathematical approval requires admitted references: " + full_id)
    return concept


def load_corpus(root=ROOT):
    root = Path(root)
    sources = source_registry(root)
    concepts, aliases, ids = [], {}, set()
    for discipline in sorted(DISCIPLINES):
        directory = root / discipline
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.json")):
            if len(concepts) >= MAX_CONCEPTS:
                fail("Concept count limit")
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
                fail("Symlink in corpus: " + str(path))
            try:
                concept = validate_concept(read_json(path), path.relative_to(root), sources, aliases)
            except (ValueError, TypeError) as error:
                raise ValueError(str(path) + ": " + str(error)) from error
            if concept["id"] in ids:
                fail("Duplicate concept ID: " + concept["id"])
            ids.add(concept["id"])
            concepts.append(concept)
    for path in root.iterdir():
        if path.is_dir() and path.name not in DISCIPLINES and path.name != "__pycache__":
            fail("Unknown corpus directory: " + path.name)
    if not concepts:
        fail("Empty authoring corpus")
    return sorted(concepts, key=lambda concept: concept["id"])


def report(concepts):
    representations = [rep for concept in concepts for rep in concept["representations"]]
    return {
        "schema": "fitbaus.stem.corpus-report/v1",
        "concepts": len(concepts),
        "representations": len(representations),
        "spoken_aliases": sum(len(rep["spoken_aliases"]) for rep in representations),
        "disciplines": dict(sorted(Counter(c["discipline"] for c in concepts).items())),
        "mathematical_review": dict(sorted(Counter(r["mathematical_review"]["status"] for r in representations).items())),
        "recognition_review": dict(sorted(Counter(r["recognition_review"]["status"] for r in representations).items())),
        "corpus_sha256": digest(concepts),
        "release_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate the FitBaus STEM authoring corpus")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(report(load_corpus(args.root)), indent=2))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, "Corpus validation failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
