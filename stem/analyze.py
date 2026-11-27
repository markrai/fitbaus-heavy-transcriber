import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .acquire import MAX_BYTES
from .dictionary import COMMANDS, validate_latex

SCHEMA = "fitbaus.stem.analysis/v1"
SAMPLE_LIMIT = 20
ENTITY = re.compile(r"https?://www\.wikidata\.org/entity/([QP][1-9][0-9]*)")
COMMAND = re.compile(r"\\([A-Za-z]+|.)?")
RELATION = re.compile(r"=|[<>]|\\(?:neq|leq|geq|approx|propto|equiv|sim|to)(?![A-Za-z])")


def read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{path.name} exceeds analysis size limit")
    return raw


def load_snapshot(directory):
    directory = Path(directory)
    manifest = json.loads(read_bounded(directory / "manifest.json", 65536))
    raw = read_bounded(directory / "snapshot.json", MAX_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if (not isinstance(manifest, dict) or manifest.get("source") != "wikidata"
            or manifest.get("license") != "CC0-1.0"
            or manifest.get("status") != "candidate_only"
            or manifest.get("sha256") != digest):
        raise ValueError("Snapshot manifest or SHA-256 mismatch")
    payload = json.loads(raw)
    rows = payload["results"]["bindings"]
    if not isinstance(rows, list) or not rows or type(manifest.get("rows")) is not int or manifest["rows"] != len(rows):
        raise ValueError("Snapshot row count mismatch")
    return digest, len(raw), rows


def unpack(row):
    values = []
    for field in ("item", "itemLabel", "formula"):
        binding = row.get(field) if isinstance(row, dict) else None
        value = binding.get("value") if isinstance(binding, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Malformed binding")
        values.append(value)
    entity = ENTITY.fullmatch(values[0])
    if entity is None:
        raise ValueError("Unexpected entity identifier")
    return entity[1], values[1], values[2]


def screen(formula):
    try:
        validate_latex(formula)
    except ValueError as error:
        return str(error)
    return "passes_lexical_screen"


def complexity(formula, commands):
    if len(formula) > 160 or len(commands) > 12:
        return "long_or_command_dense"
    if len(formula) > 48 or len(commands) > 3:
        return "intermediate"
    return "short"


def relevance(entity, formula):
    if entity.startswith("P"):
        return "property_entity"
    if "\ufffd" in formula or any(ord(c) < 32 and c not in "\n\r\t" for c in formula):
        return "encoding_or_control_issue"
    if RELATION.search(formula):
        return "relation_like"
    return "other_expression"


def counts(counter):
    return dict(sorted(counter.items(), key=lambda pair: (-pair[1], pair[0])))


def analyze(directory):
    digest, byte_count, rows = load_snapshot(directory)
    unique = {}
    entity_formulas = {}
    label_formulas = {}
    row_screen, row_relevance, invalid = Counter(), Counter(), Counter()
    exact_rows = set()
    for row in rows:
        try:
            entity, label, formula = unpack(row)
        except ValueError as error:
            invalid[str(error)] += 1
            continue
        exact_rows.add((entity, label, formula))
        entity_formulas.setdefault(entity, set()).add(formula)
        label_formulas.setdefault(" ".join(label.casefold().split()), set()).add(formula)
        if formula not in unique:
            unique[formula] = (screen(formula), tuple(m.group(1) or "<dangling>" for m in COMMAND.finditer(formula)))
        row_screen[unique[formula][0]] += 1
        row_relevance[relevance(entity, formula)] += 1

    unique_screen, command_counts, complexity_counts = Counter(), Counter(), Counter()
    formula_bytes = 0
    examples = []
    for formula, (status, commands) in sorted(unique.items()):
        unique_screen[status] += 1
        command_counts.update(set(commands))
        complexity_counts[complexity(formula, commands)] += 1
        formula_bytes += len(formula.encode("utf-8"))
        if status != "passes_lexical_screen" and len(examples) < SAMPLE_LIMIT:
            examples.append({"formula": formula[:256], "reason": status})

    label_collisions = sorted((label, len(formulas)) for label, formulas in label_formulas.items() if len(formulas) > 1)
    multi_entities = sorted((entity, len(formulas)) for entity, formulas in entity_formulas.items() if len(formulas) > 1)
    approved = COMMANDS | {","}
    valid_rows = len(rows) - sum(invalid.values())
    return {
        "schema": SCHEMA,
        "source_sha256": digest,
        "snapshot_bytes": byte_count,
        "rows": len(rows),
        "valid_binding_rows": valid_rows,
        "invalid_binding_rows": counts(invalid),
        "distinct_entity_label_formula_rows": len(exact_rows),
        "duplicate_binding_rows": valid_rows - len(exact_rows),
        "unique_exact_formulas": len(unique),
        "repeated_formula_rows": valid_rows - len(unique),
        "unique_entities": len(entity_formulas),
        "unique_normalized_labels": len(label_formulas),
        "row_lexical_screen": counts(row_screen),
        "unique_formula_lexical_screen": counts(unique_screen),
        "row_relevance_heuristic": counts(row_relevance),
        "unique_formula_complexity_heuristic": counts(complexity_counts),
        "command_document_frequency": counts(command_counts),
        "commands_outside_current_allowlist": counts(Counter({k: v for k, v in command_counts.items() if k not in approved})),
        "labels_with_multiple_formulas": len(label_collisions),
        "entities_with_multiple_formulas": len(multi_entities),
        "label_collision_examples": [{"label": label[:256], "formula_count": n} for label, n in label_collisions[:SAMPLE_LIMIT]],
        "multi_formula_entity_examples": [{"entity": entity, "formula_count": n} for entity, n in multi_entities[:SAMPLE_LIMIT]],
        "lexical_rejection_examples": examples,
        "unique_formula_utf8_bytes": formula_bytes,
        "spoken_aliases_verified": 0,
        "status": "candidate_only",
    }


def markdown(report):
    lines = [
        "# STEM corpus analysis", "",
        f"Source SHA-256: {report['source_sha256']}", "",
        "| Metric | Count |", "| --- | ---: |",
    ]
    metrics = (
        ("Candidate records", "rows"),
        ("Valid binding rows", "valid_binding_rows"),
        ("Exact duplicate binding rows", "duplicate_binding_rows"),
        ("Unique exact formulas", "unique_exact_formulas"),
        ("Repeated formula rows", "repeated_formula_rows"),
        ("Unique entities", "unique_entities"),
        ("Labels with multiple formulas", "labels_with_multiple_formulas"),
        ("Entities with multiple formulas", "entities_with_multiple_formulas"),
        ("Verified spoken aliases", "spoken_aliases_verified"),
        ("UTF-8 bytes of unique formula strings (not a compiled database estimate)", "unique_formula_utf8_bytes"),
    )
    lines.extend(f"| {label} | {report[key]:,} |" for label, key in metrics)
    for heading, key in (
        ("Lexical screen (unique formulas)", "unique_formula_lexical_screen"),
        ("Relevance heuristic (rows)", "row_relevance_heuristic"),
        ("Complexity heuristic (unique formulas)", "unique_formula_complexity_heuristic"),
        ("Commands outside current allowlist (top 30)", "commands_outside_current_allowlist"),
    ):
        lines.extend(["", f"## {heading}", "", "| Classification | Count |", "| --- | ---: |"])
        for label, value in list(report[key].items())[:30]:
            safe = label.encode("unicode_escape").decode("ascii").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"| {safe} | {value:,} |")
    lines.extend(["", "## Interpretation", "",
                  "Exact strings are deduplicated without changing variable case, grouping or whitespace.",
                  "Lexical screening is not mathematical validation or renderer qualification.",
                  "Relevance and complexity are heuristics, not semantic classifications.",
                  "A label with multiple formulas is a review signal, not proof of ambiguity in speech.",
                  "No spoken aliases are present in this source. No entries have been admitted.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze a local, immutable STEM candidate snapshot")
    parser.add_argument("snapshot", type=Path, help="Directory containing snapshot.json and manifest.json")
    parser.add_argument("--output", type=Path, required=True, help="New report directory (outside the snapshot)")
    args = parser.parse_args()
    try:
        source = args.snapshot.resolve()
        output = args.output.resolve()
        if output == source or source in output.parents:
            raise ValueError("Reports must be outside the immutable snapshot directory")
        report = analyze(source)
        output.mkdir(parents=True, exist_ok=False)
        (output / "analysis.json").write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        (output / "analysis.md").write_text(markdown(report), encoding="utf-8")
        print(json.dumps({key: report[key] for key in (
            "source_sha256", "rows", "unique_exact_formulas", "unique_formula_lexical_screen",
            "row_relevance_heuristic", "labels_with_multiple_formulas", "spoken_aliases_verified"
        )}, indent=2))
        print(f"Reports: {output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Analysis failed: {error}\n")


if __name__ == "__main__":
    main()
