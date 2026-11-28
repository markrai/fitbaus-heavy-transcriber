import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from .corpus_model import ROOT, digest, load_corpus, mathematical_digest, read_json, recognition_digest
from .dictionary import MAX_BYTES, normalize_alias
from .matcher import MATCHER_VERSION
from .qualify_render import preflight

SCHEMA = "fitbaus.stem.compiled-candidates/v1"
COMPILER_VERSION = "1"


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def compile_corpus(root=ROOT):
    root = Path(root)
    concepts = load_corpus(root)
    registry = read_json(root / "sources.json")
    sources = sorted(registry["sources"], key=lambda row: row["id"])
    entries, excluded = [], []
    for concept in concepts:
        for rep in sorted(concept["representations"], key=lambda row: row["id"]):
            identity = concept["id"] + ":" + rep["id"]
            reasons = []
            for review in ("mathematical_review", "recognition_review"):
                status = rep[review]["status"]
                if status != "approved":
                    reasons.append(review + ":" + status)
            if not rep["spoken_aliases"]:
                reasons.append("no_spoken_aliases")
            if reasons:
                excluded.append({"id": identity, "reasons": reasons})
                continue
            try:
                preflight(rep["latex"])
            except ValueError as error:
                raise ValueError(f"Admitted representation fails TeX preflight: {identity}: {error}") from error
            entries.append({
                "id": identity,
                "concept_id": concept["id"],
                "representation_id": rep["id"],
                "name": concept["name"],
                "discipline": concept["discipline"],
                "subject": concept["subject"],
                "latex": rep["latex"],
                "aliases": sorted(normalize_alias(alias) for alias in rep["spoken_aliases"]),
                "mathematical_sha256": mathematical_digest(concept, rep),
                "recognition_sha256": recognition_digest(concept, rep),
            })
    counts = Counter(reason for row in excluded for reason in row["reasons"])
    payload = {
        "schema": SCHEMA,
        "compiler_version": COMPILER_VERSION,
        "matcher_version": MATCHER_VERSION,
        "authoring_sha256": digest(concepts),
        "source_registry_sha256": digest({"schema": registry["schema"], "sources": sources}),
        "release_qualified": False,
        "entries": entries,
        "excluded": excluded,
        "counts": {
            "concepts": len(concepts),
            "representations": len(entries) + len(excluded),
            "eligible": len(entries),
            "excluded": len(excluded),
            "aliases": sum(len(row["aliases"]) for row in entries),
            "exclusion_reasons": dict(sorted(counts.items())),
        },
    }
    artifact = {**payload, "artifact_sha256": digest(payload)}
    if len(canonical_bytes(artifact)) > MAX_BYTES:
        raise ValueError("Compiled candidate artifact size limit")
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compile reviewed STEM dictionary candidates offline")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--summary", action="store_true", help="Print counts and identity only")
    args = parser.parse_args(argv)
    try:
        artifact = compile_corpus(args.root)
        if args.summary:
            summary = {key: value for key, value in artifact.items() if key not in ("entries", "excluded")}
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            sys.stdout.buffer.write(canonical_bytes(artifact))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, "STEM compilation failed: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
