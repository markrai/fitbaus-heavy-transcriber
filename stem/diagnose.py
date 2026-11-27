import argparse
from collections import Counter
import json
from pathlib import Path

from .analyze import counts, load_snapshot, unpack
from .convert import classify, inspect
from .mathml import ConversionError, VERSION, local_name, parse_mathml
from .prioritize import classify_label

MAX_VALUE = 128
MAX_KEYS = 2048


def bounded_key(counter, value):
    if len(value) > MAX_VALUE:
        value = "<long-value>"
    if value not in counter and len(counter) >= MAX_KEYS:
        value = "<other-values>"
    counter[value] += 1


def diagnose(directory):
    digest, _, rows = load_snapshot(directory)
    attributes = {}
    tokens = {}
    reasons = Counter()
    examined = 0
    parsed = 0
    for row in rows:
        try:
            entity, label, source = unpack(row)
        except ValueError:
            continue
        if classify_label(entity, label) != "potentially_named" or classify(source) != "mathml":
            continue
        _, _, error, _ = inspect(source)
        if error is None:
            continue
        examined += 1
        reasons[error] += 1
        try:
            root = parse_mathml(source)
        except ConversionError:
            continue
        parsed += 1
        for node in root.iter():
            tag = local_name(node.tag)
            for key, value in node.attrib.items():
                name = tag + ":" + key
                if name not in attributes and len(attributes) >= MAX_KEYS:
                    name = "<other-attributes>"
                bounded_key(attributes.setdefault(name, Counter()), value)
            if tag in {"mi", "mo", "mn", "mtext"}:
                bounded_key(tokens.setdefault(tag, Counter()), (node.text or "").strip())
    return {
        "schema": "fitbaus.stem.diagnostics/v1",
        "source_sha256": digest,
        "converter": VERSION,
        "rejected_named_mathml_rows": examined,
        "parsed_rejected_rows": parsed,
        "first_rejection_reasons": counts(reasons),
        "attribute_values": {k: counts(v) for k, v in sorted(attributes.items())},
        "token_values": {k: counts(v) for k, v in sorted(tokens.items())},
        "status": "candidate_only",
    }


def main():
    parser = argparse.ArgumentParser(description="Inventory XML values in rejected named MathML records")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = args.snapshot.resolve()
        output = args.output.resolve()
        if output == source or source in output.parents:
            raise ValueError("Output must be outside the immutable snapshot")
        report = diagnose(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print(f"Rejected named MathML rows: {report['rejected_named_mathml_rows']}")
        print(f"Report: {output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Diagnostics failed: {error}\n")


if __name__ == "__main__":
    main()
