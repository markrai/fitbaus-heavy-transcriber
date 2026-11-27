import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .analyze import counts, load_snapshot, unpack
from .dictionary import validate_latex
from .mathml import VERSION, ConversionError, convert_mathml, parse_mathml, local_name

SCHEMA = "fitbaus.stem.conversion/v1"
MATHML_START = re.compile(r"\s*<(?:[A-Za-z_][\w.-]*:)?math(?:\s|>)")
SAMPLE_LIMIT = 3


def classify(source):
    if MATHML_START.match(source):
        return "mathml"
    if source.lstrip().startswith("<"):
        return "other_markup"
    return "latex_candidate"


def inspect(source):
    kind = classify(source)
    if kind == "other_markup":
        return kind, None, "unsupported_markup", ()
    if kind == "mathml":
        try:
            root = parse_mathml(source)
            elements = tuple(local_name(node.tag) for node in root.iter())
            latex = convert_mathml(source)
        except ConversionError as error:
            return kind, None, str(error), locals().get("elements", ())
        return kind, latex, None, elements
    try:
        return kind, validate_latex(source), None, ()
    except ValueError as error:
        return kind, None, "latex_screen:" + str(error), ()


def convert_snapshot(directory, candidate_stream):
    digest, byte_count, rows = load_snapshot(directory)
    cached = {}
    kinds, outcomes, elements = Counter(), Counter(), Counter()
    unique_outcomes, unique_elements = Counter(), Counter()
    examples = {}
    latex_strings = set()
    written = 0
    for row_index, row in enumerate(rows):
        try:
            entity, label, source = unpack(row)
        except ValueError:
            outcomes["invalid_binding"] += 1
            continue
        if source not in cached:
            result = inspect(source)
            cached[source] = result
            kind, latex, error, tags = result
            unique_outcomes[error or "screened_candidate"] += 1
            unique_elements.update(tags)
        kind, latex, error, tags = cached[source]
        kinds[kind] += 1
        elements.update(tags)
        outcomes[error or "screened_candidate"] += 1
        if error:
            bucket = examples.setdefault(error, [])
            if len(bucket) < SAMPLE_LIMIT:
                bucket.append({"row_index": row_index, "entity": entity, "label": label[:128]})
            continue
        candidate = {
            "row_index": row_index, "entity": entity, "label": label,
            "source_sha256": digest,
            "formula_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "representation": kind, "latex": latex, "converter": VERSION,
            "status": "candidate_only",
        }
        candidate_stream.write(json.dumps(candidate, ensure_ascii=True, sort_keys=True) + "\n")
        latex_strings.add(latex)
        written += 1
    return {
        "schema": SCHEMA, "converter": VERSION, "source_sha256": digest,
        "snapshot_bytes": byte_count, "rows": len(rows),
        "representation_rows": counts(kinds), "row_outcomes": counts(outcomes),
        "unique_source_formulas": len(cached), "unique_source_outcomes": counts(unique_outcomes),
        "element_occurrences_rows": counts(elements),
        "element_occurrences_unique_sources": counts(unique_elements),
        "candidate_rows_written": written, "unique_candidate_latex": len(latex_strings),
        "rejection_examples": dict(sorted(examples.items())),
        "spoken_aliases_verified": 0, "status": "candidate_only",
    }


def main():
    parser = argparse.ArgumentParser(description="Convert bounded MathML subset to review-only LaTeX candidates")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = args.snapshot.resolve()
        output = args.output.resolve()
        if output == source or source in output.parents:
            raise ValueError("Output must be outside the immutable snapshot")
        output.mkdir(parents=True, exist_ok=False)
        with (output / "candidates.jsonl.tmp").open("w", encoding="utf-8", newline="\n") as stream:
            report = convert_snapshot(source, stream)
        (output / "candidates.jsonl.tmp").replace(output / "candidates.jsonl")
        temporary = output / "conversion.json.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output / "conversion.json")
        print(json.dumps({key: report[key] for key in (
            "source_sha256", "rows", "representation_rows", "row_outcomes",
            "candidate_rows_written", "unique_candidate_latex"
        )}, indent=2))
        print(f"Reports: {output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Conversion failed: {error}\n")


if __name__ == "__main__":
    main()
