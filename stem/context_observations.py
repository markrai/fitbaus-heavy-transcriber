import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .sample_checkpoints import (
    MAX_PACK_BYTES, OUTPUT_ROOT, REPO_ROOT, SCHEMA as SAMPLE_SCHEMA,
    link_like, read_checkpoint, require_directory, save_sample, scan,
)
from .corpus_model import digest, strict_object
from .cue_recognition import recognize_window
from .hybrid import build_hybrid
from .observation_labels import label_latex
from .qualify_recognition import fields, text_value
from .prose_context import MAX_EVIDENCE_CUES, MAX_EVIDENCE_GAP_MS, MAX_EVIDENCE_MS

SCHEMA = "fitbaus.stem.context-sample/v1"
LABEL_SCHEMA = "fitbaus.stem.context-labels/v1"
REPORT_SCHEMA = "fitbaus.stem.context-qualification/v1"
MAX_CONTEXT_BYTES = MAX_PACK_BYTES
STRATA = ("uniform", "formula_hint")
IMPLEMENTATION_FILES = (
    "context_observations.py", "sample_checkpoints.py", "cue_recognition.py",
    "hybrid.py", "structural_rules.py", "identity_context.py", "matcher.py", "prose_context.py",
    "tokenizer.py", "parser.py", "expression.py", "dictionary.py",
    "corpus_model.py", "observation_labels.py", "qualify_recognition.py",
)


def load_json(path):
    path = Path(path)
    if link_like(path) or not path.is_file():
        raise ValueError("Expected ordinary JSON file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONTEXT_BYTES + 1)
    if len(raw) > MAX_CONTEXT_BYTES:
        raise ValueError("Context evidence size limit")
    value = json.loads(raw, object_pairs_hook=strict_object,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def check_digest(value, field):
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise ValueError("Evidence digest mismatch: " + field)


def implementation_digest():
    root = Path(__file__).resolve().parent
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                   for name in IMPLEMENTATION_FILES})


def recover_context(sample, work, hybrid):
    check_digest(sample, "sample_sha256")
    if (sample.get("schema") != SAMPLE_SCHEMA or sample.get("sampler_version") != "1"
            or sample.get("partition") != "development" or sample.get("inventory_only") is not False
            or sample.get("labels_complete") is not False or not sample.get("cases")):
        raise ValueError("Expected original unlabeled development sample")
    sources = sample["sources"]
    books = sorted({row["book_key"] for row in sources})
    profiles = {row["profile_key"] for row in sources}
    if not books or len(profiles) != 1:
        raise ValueError("Context pilot requires one checkpoint profile")
    profile = next(iter(profiles))
    work = Path(work)
    if any(link_like(path) for path in (work, *work.parents)):
        raise ValueError("Work directory must not traverse a link")
    replay = scan(work, books=books, profile_key=profile, seed=sample["seed"],
                  partition="development", uniform_count=sample["requested"]["uniform"],
                  targeted_count=sample["requested"]["formula_hint"])
    if replay != sample:
        raise ValueError("Original development sample no longer matches checkpoint snapshot")
    grouped = {}
    for row in sample["cases"]:
        grouped.setdefault((row["book_key"], row["profile_key"], row["window_start_ms"]), []).append(row)
    windows, originals = [], {}
    for (book, profile, start), rows in sorted(grouped.items()):
        directory = work / book / profile
        require_directory(directory)
        window, sha = read_checkpoint(directory / f"{start}.json", book)
        key = digest([book, profile, start, sha])
        anchors = []
        for row in sorted(rows, key=lambda item: item["cue_index"]):
            cue = window.cues[row["cue_index"]]
            if (row["checkpoint_sha256"] != sha or row["text"] != cue.text
                    or row["start_ms"] != cue.start_ms or row["end_ms"] != cue.end_ms):
                raise ValueError("Checkpoint changed after sample verification")
            anchors.append({"id": row["id"], "cue_index": row["cue_index"], "stratum": row["stratum"]})
        windows.append({"id": key, "book_key": book, "profile_key": profile,
                        "checkpoint_sha256": sha, "start_ms": window.start_ms, "end_ms": window.end_ms,
                        "cues": [{"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text}
                                 for cue in window.cues], "anchors": anchors})
        originals[key] = window
    payload = {"schema": SCHEMA, "partition": "development",
               "sample_sha256": sample["sample_sha256"],
               "source_snapshot_sha256": sample["source_snapshot_sha256"],
               "hybrid_policy_sha256": hybrid.policy_sha256,
               "implementation_sha256": implementation_digest(), "windows": windows,
               "labels_complete": False, "recognition_qualified": False}
    return {**payload, "context_sha256": digest(payload)}, originals


def read_labels(labels, pack, hybrid):
    fields(labels, {"schema", "context_sha256", "labeling_method", "cases"}, "context labels")
    if labels["schema"] != LABEL_SCHEMA or labels["context_sha256"] != pack["context_sha256"]:
        raise ValueError("Labels do not bind the context sample")
    text_value(labels["labeling_method"], 2048, "labeling method")
    anchors = {anchor["id"]: (window, anchor) for window in pack["windows"] for anchor in window["anchors"]}
    rows = labels["cases"]
    if not isinstance(rows, list) or len(rows) != len(anchors):
        raise ValueError("Every sampled anchor requires an explicit review")
    entries = {entry.id: entry for entry in hybrid.dictionary.entries}
    reviewed = {}
    for row in rows:
        fields(row, {"id", "expected", "exclusion_reason"}, "context label")
        key = row["id"]
        if not isinstance(key, str) or key not in anchors or key in reviewed:
            raise ValueError("Unknown or duplicate anchor")
        window, anchor = anchors[key]
        cues = window["cues"]
        if row["expected"] is None:
            text_value(row["exclusion_reason"], 1024, "exclusion reason")
            reviewed[key] = None
            continue
        if row["exclusion_reason"] is not None or not isinstance(row["expected"], list) or len(row["expected"]) > 256:
            raise ValueError("Invalid context annotations")
        expected = []
        previous = (-1, -1)
        for match in row["expected"]:
            fields(match, {"id", "latex", "spans"}, "context annotation")
            identity = match["id"]
            if not isinstance(identity, str) or identity not in entries:
                raise ValueError("Unknown representation")
            latex = label_latex(identity, match["latex"], entries[identity].latex)
            spans = match["spans"]
            if not isinstance(spans, list) or not 1 <= len(spans) <= 3:
                raise ValueError("Invalid span collection")
            parts = []
            for part in spans:
                fields(part, {"cue_index", "start", "end"}, "cue span")
                index, start, end = part["cue_index"], part["start"], part["end"]
                if (type(index) is not int or not 0 <= index < len(cues)
                        or type(start) is not int or type(end) is not int
                        or not 0 <= start < end <= len(cues[index]["text"])
                        or not cues[index]["text"][start:end].strip()
                        or (index, start) < previous):
                    raise ValueError("Invalid or overlapping cue span")
                if not parts and index != anchor["cue_index"]:
                    raise ValueError("Annotation must start in sampled anchor")
                if parts and index != parts[-1][0] + 1:
                    raise ValueError("Annotation spans must use consecutive cues")
                parts.append((index, start, end))
                previous = (index, end)
            expected.append((identity, latex, tuple(parts)))
        reviewed[key] = Counter(expected)
    if set(reviewed) != set(anchors):
        raise ValueError("Incomplete anchor review")
    return reviewed


def verify_context(supplied, current, requalify=False):
    check_digest(supplied, "context_sha256")
    if supplied == current:
        return
    if requalify:
        mutable = {"context_sha256", "hybrid_policy_sha256", "implementation_sha256"}
        if ({k: v for k, v in supplied.items() if k not in mutable}
                == {k: v for k, v in current.items() if k not in mutable}
                and all(isinstance(supplied.get(key), str)
                        and len(supplied[key]) == 64
                        and all(char in "0123456789abcdef" for char in supplied[key])
                        for key in mutable)):
            return
    raise ValueError("Context sample, checkpoints or implementation changed")


def score(pack, originals, labels, hybrid, *, label_pack=None):
    supplied = pack if label_pack is None else label_pack
    verify_context(supplied, pack, requalify=label_pack is not None)
    reviewed = read_labels(labels, supplied, hybrid)
    groups = {name: Counter(anchors=0, excluded=0, scored=0, expected_matches=0,
                            actual_matches=0, true_positive=0, false_positive=0,
                            false_negative=0, invalid_evidence=0, cross_cue_expected=0,
                            cross_cue_true_positive=0) for name in STRATA}
    failures = []
    coverage = {name: set() for name in STRATA}
    for row in pack["windows"]:
        window = originals[row["id"]]
        result = recognize_window(window, hybrid)
        by_anchor = {}
        for match in result.matches:
            parts = tuple((s.cue_index, s.start, s.end) for s in match.spans)
            if not parts:
                raise ValueError("Recognizer returned empty annotation")
            first, last = parts[0][0], parts[-1][0]
            valid = (result.book_key == row["book_key"] and result.window_start_ms == window.start_ms
                     and result.window_end_ms == window.end_ms and result.policy_sha256 == hybrid.policy_sha256
                     and 0 <= match.evidence_start_cue <= first <= last <= match.evidence_end_cue < len(window.cues)
                     and match.evidence_end_cue - match.evidence_start_cue < (MAX_EVIDENCE_CUES if len(parts) == 1 else 3)
                     and (match.evidence_end_cue == match.evidence_start_cue
                          or window.cues[match.evidence_end_cue].end_ms
                          - window.cues[match.evidence_start_cue].start_ms <= MAX_EVIDENCE_MS)
                     and all(window.cues[i + 1].start_ms - window.cues[i].end_ms <= MAX_EVIDENCE_GAP_MS
                             for i in range(match.evidence_start_cue, match.evidence_end_cue))
                     and all(0 <= s.cue_index < len(window.cues)
                             and 0 <= s.start < s.end <= len(window.cues[s.cue_index].text)
                             and s.source_text == window.cues[s.cue_index].text[s.start:s.end]
                             and (s.start_ms, s.end_ms) == (window.cues[s.cue_index].start_ms,
                                                           window.cues[s.cue_index].end_ms)
                             for s in match.spans))
            by_anchor.setdefault(first, []).append(((match.dictionary_id, match.latex, parts), valid))
        for anchor in row["anchors"]:
            stats = groups[anchor["stratum"]]
            stats["anchors"] += 1
            expected = reviewed[anchor["id"]]
            if expected is None:
                stats["excluded"] += 1
                continue
            predictions = by_anchor.get(anchor["cue_index"], [])
            actual = Counter(item for item, valid in predictions if valid)
            invalid = sum(not valid for _, valid in predictions)
            overlap = actual & expected
            tp = sum(overlap.values())
            fp = sum((actual - expected).values()) + invalid
            fn = sum((expected - actual).values())
            coverage[anchor["stratum"]].update(item[0] for item in expected)
            stats.update(scored=1, expected_matches=sum(expected.values()),
                         actual_matches=len(predictions), true_positive=tp, false_positive=fp,
                         false_negative=fn, invalid_evidence=invalid,
                         cross_cue_expected=sum(count for item, count in expected.items() if len(item[2]) > 1),
                         cross_cue_true_positive=sum(count for item, count in overlap.items() if len(item[2]) > 1))
            if fp or fn or invalid:
                failures.append({"anchor_id": anchor["id"], "stratum": anchor["stratum"],
                                 "false_positive": fp, "false_negative": fn, "invalid_evidence": invalid})
    summaries = {}
    for name, stats in groups.items():
        summaries[name] = {**dict(stats), "expected_representation_coverage": len(coverage[name]),
                           "precision": stats["true_positive"] / stats["actual_matches"] if stats["actual_matches"] else None,
                           "recall": stats["true_positive"] / stats["expected_matches"] if stats["expected_matches"] else None,
                           "pass": bool(stats["scored"]) and not (stats["false_positive"] or stats["false_negative"]
                                                                  or stats["invalid_evidence"])}
    payload = {"schema": REPORT_SCHEMA, "partition": "development", "context_sha256": supplied["context_sha256"],
               "evaluated_context_sha256": pack["context_sha256"],
               "label_policy_sha256": supplied["hybrid_policy_sha256"],
               "label_implementation_sha256": supplied["implementation_sha256"],
               "labels_sha256": digest(labels), "implementation_sha256": pack["implementation_sha256"],
               "hybrid_policy_sha256": hybrid.policy_sha256, "groups": summaries, "failures": failures,
               "provenance_verified": False, "recognition_qualified": False, "release_qualified": False}
    return {**payload, "report_sha256": digest(payload)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export and score development-only adjacent-cue evidence")
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / "work")
    parser.add_argument("--name", help="New context JSON filename under work/stem-qualification")
    parser.add_argument("--context", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--requalify", action="store_true", help="Allow old implementation/policy binding only with identical development evidence")
    args = parser.parse_args(argv)
    if args.requalify and args.name:
        parser.error("--requalify requires scoring")
    if not ((args.name and not args.context and not args.labels)
            or (not args.name and args.context and args.labels)):
        parser.error("Choose --name for export or --context and --labels for scoring")
    try:
        hybrid, _, _ = build_hybrid()
        pack, originals = recover_context(load_json(args.sample), args.work_dir, hybrid)
        if args.name:
            path = save_sample(pack, args.name, OUTPUT_ROOT)
            report = {"output": str(path), "context_sha256": pack["context_sha256"],
                      "windows": len(pack["windows"]), "cues": sum(len(row["cues"]) for row in pack["windows"]),
                      "anchors": sum(len(row["anchors"]) for row in pack["windows"]),
                      "partition": pack["partition"], "recognition_qualified": False}
        else:
            supplied = load_json(args.context)
            verify_context(supplied, pack, args.requalify)
            report = score(pack, originals, load_json(args.labels), hybrid,
                           label_pack=supplied if args.requalify else None)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        parser.exit(1, "Context qualification failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
