import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .analyze import counts, load_snapshot, unpack
from .convert import inspect
from .mathml import VERSION as CONVERTER_VERSION

VERSION = "label-priority-v1"
SCHEMA = "fitbaus.stem.prioritization/v1"
ENTITY_LABEL = re.compile(r"[QP][0-9]+", re.IGNORECASE)
WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
SAMPLE_LIMIT = 20


def label_key(label):
    return " ".join(unicodedata.normalize("NFC", label).casefold().split())


def classify_label(entity, label):
    if entity.startswith("P"):
        return "property"
    label = label.strip()
    if ENTITY_LABEL.fullmatch(label):
        return "unresolved"
    if WORD.search(label):
        return "potentially_named"
    if any(c.isnumeric() for c in label) and not any(c.isalpha() for c in label):
        return "numeric_expression"
    return "symbolic_or_uncertain"


def write_row(stream, row):
    stream.write(json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def prioritize(directory, named_stream, rejected_stream, deferred_stream):
    digest, byte_count, rows = load_snapshot(directory)
    categories, outcomes, rejections = Counter(), Counter(), Counter()
    examples = defaultdict(list)
    names, entities, formulas = defaultdict(set), defaultdict(set), defaultdict(list)
    converted = []
    cached = {}
    for index, row in enumerate(rows):
        try:
            entity, label, source = unpack(row)
        except ValueError:
            categories["invalid_binding"] += 1
            write_row(deferred_stream, {"row_index": index, "source_sha256": digest,
                                       "category": "invalid_binding", "status": "candidate_only"})
            continue
        category = classify_label(entity, label)
        categories[category] += 1
        record = {
            "row_index": index, "entity": entity, "label": label,
            "category": category, "source_sha256": digest,
            "formula_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "status": "candidate_only",
        }
        if category != "potentially_named":
            write_row(deferred_stream, record)
            continue
        if source not in cached:
            kind, latex, error, _ = inspect(source)
            cached[source] = kind, latex, error
        kind, latex, error = cached[source]
        record.update({"representation": kind, "converter": CONVERTER_VERSION})
        if error is not None:
            outcomes["conversion_rejected"] += 1
            rejections[error] += 1
            record["reason"] = error
            write_row(rejected_stream, record)
            if len(examples[error]) < SAMPLE_LIMIT:
                examples[error].append({"row_index": index, "entity": entity, "label": label[:128]})
            continue
        outcomes["screened_candidate"] += 1
        record["latex"] = latex
        converted.append(record)
        names[label_key(label)].add(latex)
        entities[entity].add(latex)
        formulas[latex].append(index)

    for record in converted:
        latex = record["latex"]
        record["review_flags"] = {
            "label_has_multiple_formulas": len(names[label_key(record["label"])]) > 1,
            "entity_has_multiple_formulas": len(entities[record["entity"]]) > 1,
            "formula_shared_by_multiple_rows": len(formulas[latex]) > 1,
        }
        write_row(named_stream, record)

    return {
        "schema": SCHEMA, "prioritizer": VERSION, "converter": CONVERTER_VERSION,
        "source_sha256": digest, "snapshot_bytes": byte_count, "rows": len(rows),
        "label_categories": counts(categories),
        "named_conversion_outcomes": counts(outcomes),
        "named_rejection_reasons": counts(rejections),
        "named_rejection_examples": dict(sorted(examples.items())),
        "named_unique_latex": len(formulas),
        "named_labels_with_multiple_screened_formulas": sum(len(v) > 1 for v in names.values()),
        "named_entities_with_multiple_screened_formulas": sum(len(v) > 1 for v in entities.values()),
        "named_latex_shared_by_multiple_rows": sum(len(v) > 1 for v in formulas.values()),
        "deferred_rows": len(rows) - categories["potentially_named"],
        "spoken_aliases_verified": 0,
        "status": "candidate_only",
    }


def markdown(report):
    lines = ["# STEM corpus prioritization", "", f"Source SHA-256: {report['source_sha256']}", "",
             f"Total source records: {report['rows']:,}", ""]
    for heading, key in (
        ("Label classification", "label_categories"),
        ("Named conversion outcomes", "named_conversion_outcomes"),
        ("Named conversion rejection priorities", "named_rejection_reasons"),
    ):
        lines.extend(["", f"## {heading}", "", "| Classification | Rows |", "| --- | ---: |"])
        for name, count in report[key].items():
            safe = name.encode("unicode_escape").decode("ascii").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"| {safe} | {count:,} |")
    lines.extend(["", f"Distinct screened named LaTeX strings: {report['named_unique_latex']:,}",
                  f"Names with multiple screened formulas: {report['named_labels_with_multiple_screened_formulas']:,}",
                  f"Entities with multiple screened formulas: {report['named_entities_with_multiple_screened_formulas']:,}",
                  "", "Classification is a label-based heuristic, not a semantic or mathematical audit.",
                  "Collision flags cover screened named candidates only; rejected and deferred rows remain unreviewed.",
                  "No spoken aliases are verified and no entries are admitted.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Prioritize named STEM candidates for offline review")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = args.snapshot.resolve()
        output = args.output.resolve()
        if output == source or source in output.parents:
            raise ValueError("Output must be outside the immutable snapshot")
        output.mkdir(parents=True, exist_ok=False)
        names = ("named.jsonl", "rejected-named.jsonl", "deferred.jsonl")
        with (output / (names[0] + ".tmp")).open("w", encoding="utf-8", newline="\n") as named, \
                (output / (names[1] + ".tmp")).open("w", encoding="utf-8", newline="\n") as rejected, \
                (output / (names[2] + ".tmp")).open("w", encoding="utf-8", newline="\n") as deferred:
            report = prioritize(source, named, rejected, deferred)
        for name in names:
            (output / (name + ".tmp")).replace(output / name)
        (output / "prioritization.md").write_text(markdown(report), encoding="utf-8")
        temporary = output / "prioritization.json.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output / "prioritization.json")
        print(json.dumps({key: report[key] for key in (
            "source_sha256", "rows", "label_categories", "named_conversion_outcomes",
            "named_rejection_reasons", "named_unique_latex",
            "named_labels_with_multiple_screened_formulas", "deferred_rows"
        )}, indent=2))
        print(f"Reports: {output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Prioritization failed: {error}\n")


if __name__ == "__main__":
    main()
