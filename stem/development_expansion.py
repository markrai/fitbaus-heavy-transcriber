import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .context_observations import check_digest, implementation_digest, load_json, score, verify_context
from .corpus_model import digest
from .cue_recognition import WindowRecognition, recognize_run
from .hybrid import build_hybrid
from .sample_checkpoints import (
    BOOK_KEY, FORMULA_HINT, MAX_CANDIDATES, MAX_WINDOWS, OUTPUT_ROOT, REPO_ROOT,
    SCHEMA as SAMPLE_SCHEMA, checkpoint_directories, link_like, offer, ordered,
    partition_for, rank, read_checkpoint, save_sample, window_paths,
)
from transcriber.contract import MAX_WINDOW_MS

SCHEMA = "fitbaus.stem.development-expansion/v1"
REPORT_SCHEMA = "fitbaus.stem.development-expansion-qualification/v1"
SAMPLER_VERSION = "1"
SEED = 42
STRATA = ("equation_hint", "boundary_hint", "hard_negative_hint")
DEFAULT_QUOTAS = dict(zip(STRATA, (60, 40, 30)))
RELATION = re.compile(r"[=≤≥≠]|\b(?:equals?|equal[ \t]+to|greater[ \t]+than|less[ \t]+than|proportional[ \t]+to)\b", re.I)
MATH = re.compile(r"[+*/^²³√π∑∫]|"
                  r"\b(?:plus|minus|times|over|divided by|multiplied by|squared|cubed|"
                  r"power|square root|sine|cosine|tangent|derivative|integral|subscript|"
                  r"factorial|numerator|denominator|lambda|theta|sigma|pi)\b", re.I)
ATOM = re.compile(r"\b(?:[a-z]|[0-9]+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
EDGE = r"(?:plus|minus|times|over|divided by|multiplied by|equals?|equal to|raised to|power of|[+*/=^])"
LEFT_EDGE = re.compile(r"(?:\b" + EDGE + r"|[+*/=^])[ \t]*$", re.I)
RIGHT_EDGE = re.compile(r"^[ \t]*(?:" + EDGE + r")(?:\b|[ \t]|$)", re.I)
NEGATIVE = re.compile(r"\?|"
                      r"\b(?:not|never|incorrect|wrong|false|suppose|hypothetical|"
                      r"whether|counterexample|mistake|impossible|undefined|if)\b", re.I)


def equation_hint(text):
    return bool(RELATION.search(text) and (MATH.search(text) or len(ATOM.findall(text)) >= 2))


def boundary_hint(left, right):
    if right.start_ms - left.end_ms > 1500:
        return False
    lhs, rhs = left.text.rstrip(), right.text.lstrip()
    if lhs.endswith((".", "!", "?", ";", "…")):
        return False
    return bool(equation_hint(lhs + " " + rhs)
                and (LEFT_EDGE.search(lhs) or RIGHT_EDGE.match(rhs)
                     or (MATH.search(lhs) and RELATION.search(rhs))))


def classify(cues, index):
    text = cues[index].text
    if index + 1 < len(cues) and boundary_hint(cues[index], cues[index + 1]):
        return "boundary_hint"
    if FORMULA_HINT.search(text) and NEGATIVE.search(text):
        return "hard_negative_hint"
    if equation_hint(text):
        return "equation_hint"
    return None


def prior_anchors(prior):
    check_digest(prior, "sample_sha256")
    if (prior.get("schema") != SAMPLE_SCHEMA or prior.get("partition") != "development"
            or prior.get("seed") != SEED or prior.get("inventory_only") is not False
            or not isinstance(prior.get("cases"), list) or not 1 <= len(prior["cases"]) <= MAX_CANDIDATES):
        raise ValueError("Expected original seed-42 development sample")
    keys = set()
    for row in prior["cases"]:
        book, start, index = row["book_key"], row["window_start_ms"], row["cue_index"]
        if (not isinstance(book, str) or not BOOK_KEY.fullmatch(book)
                or type(start) is not int or start < 0 or start % MAX_WINDOW_MS
                or type(index) is not int or index < 0
                or partition_for(SEED, book, start) != "development"):
            raise ValueError("Invalid prior anchor")
        key = (book, start, index)
        if key in keys:
            raise ValueError("Duplicate prior anchor across profiles")
        keys.add(key)
    return keys


def selections(work, books, profile_key):
    if any(link_like(path) for path in (work, *work.parents)):
        raise ValueError("Work directory must not traverse a link")
    selected = {}
    for book, directory in checkpoint_directories(work, books, profile_key):
        if book in selected:
            raise ValueError("Multiple profiles for one book; select --profile-key")
        selected[book] = directory
    if not selected or set(books) - set(selected):
        raise ValueError("No compatible checkpoint profile for selected books")
    return selected


def expansion(work, prior, hybrid, *, books=(), profile_key=None, quotas=None, inventory=False):
    work = Path(work)
    excluded = prior_anchors(prior)
    quotas = dict(DEFAULT_QUOTAS if quotas is None else quotas)
    if (set(quotas) != set(STRATA) or any(type(n) is not int or not 0 <= n <= MAX_CANDIDATES
                                        for n in quotas.values()) or not sum(quotas.values())):
        raise ValueError("Invalid per-book sampling quotas")
    selected = selections(work, books, profile_key)
    if not inventory and sum(quotas.values()) * len(selected) > MAX_CANDIDATES:
        raise ValueError("Total requested anchors exceed 1000; select fewer books or smaller quotas")
    records, chosen, sources = [], [], []
    scanned = 0
    for book, directory in sorted(selected.items()):
        heaps = {name: [] for name in STRATA}
        counts = Counter({name: 0 for name in STRATA})
        counts.update(development_windows=0, holdout_windows_not_read=0, development_cues=0, prior_anchors_skipped=0)
        previous_end = 0
        for path in window_paths(directory):
            scanned += 1
            if scanned > MAX_WINDOWS:
                raise ValueError("Checkpoint scan limit; select fewer books")
            start = int(path.stem)
            if partition_for(SEED, book, start) != "development":
                counts["holdout_windows_not_read"] += 1
                continue
            window, sha = read_checkpoint(path, book)
            if window.start_ms < previous_end or previous_end and previous_end % MAX_WINDOW_MS:
                raise ValueError("Overlapping or nonterminal partial development window")
            previous_end = window.end_ms
            records.append({"book_key": book, "profile_key": directory.name, "start_ms": window.start_ms,
                            "end_ms": window.end_ms, "checkpoint_sha256": sha, "cues": len(window.cues)})
            counts.update(development_windows=1, development_cues=len(window.cues))
            for index, cue in enumerate(window.cues):
                if (book, start, index) in excluded:
                    counts["prior_anchors_skipped"] += 1
                    continue
                stratum = classify(window.cues, index)
                if stratum is None:
                    continue
                counts[stratum] += 1
                if inventory:
                    continue
                key = digest({"book_key": book, "profile_key": directory.name,
                              "window_start_ms": start, "cue_index": index})
                row = {"id": key, "cue_index": index, "stratum": stratum,
                       "book_key": book, "profile_key": directory.name, "window_start_ms": start,
                       "checkpoint_sha256": sha}
                offer(heaps[stratum], quotas[stratum], row, rank(SEED, "expanded:" + stratum, key))
        for stratum in STRATA:
            chosen.extend(ordered(heaps[stratum]))
        sources.append({"book_key": book, "profile_key": directory.name, "profile_verified": False,
                        "available": dict(counts),
                        "selected": {name: len(heaps[name]) for name in STRATA}})
    if not records:
        raise ValueError("No development checkpoints found")
    grouped = {}
    for row in chosen:
        grouped.setdefault((row["book_key"], row["profile_key"], row["window_start_ms"]), []).append(row)
    windows, originals = [], {}
    for (book, profile, start), rows in sorted(grouped.items()):
        window, sha = read_checkpoint(selected[book] / f"{start}.json", book)
        if any(row["checkpoint_sha256"] != sha for row in rows):
            raise ValueError("Development checkpoint changed during export")
        key = digest([book, profile, start, sha])
        anchors = [{k: row[k] for k in ("id", "cue_index", "stratum")}
                   for row in sorted(rows, key=lambda item: item["cue_index"])]
        windows.append({"id": key, "book_key": book, "profile_key": profile,
                        "checkpoint_sha256": sha, "start_ms": window.start_ms, "end_ms": window.end_ms,
                        "cues": [{"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text}
                                 for cue in window.cues], "anchors": anchors})
        originals[key] = window
    payload = {"schema": SCHEMA, "sampler_version": SAMPLER_VERSION, "partition": "development",
               "seed": SEED, "prior_sample_sha256": prior["sample_sha256"],
               "source_snapshot_sha256": digest(records),
               "selection": {"books": sorted(selected), "profile_key": profile_key, "quotas": quotas},
               "sources": sources, "inventory_only": inventory, "windows": windows,
               "hybrid_policy_sha256": hybrid.policy_sha256,
               "implementation_sha256": implementation_digest(),
               "labels_complete": False, "recognition_qualified": False}
    return {**payload, "context_sha256": digest(payload)}, originals


def single_cue_window(window, hybrid):
    matches = tuple(match for i, cue in enumerate(window.cues)
                    for match in recognize_run((cue,), i, hybrid))
    return WindowRecognition(window.identity.cache_key(), window.start_ms, window.end_ms,
                             hybrid.policy_sha256, matches)


def compare(pack, originals, supplied, labels, hybrid, requalify=False):
    verify_context(supplied, pack, requalify)
    if not pack["windows"] or pack["inventory_only"]:
        raise ValueError("No sampled windows to qualify")
    baseline = score(pack, originals, labels, hybrid, label_pack=supplied, strata=STRATA,
                     recognizer=single_cue_window, diagnostics=True)
    contextual = score(pack, originals, labels, hybrid, label_pack=supplied, strata=STRATA,
                       diagnostics=True)
    payload = {"schema": REPORT_SCHEMA, "partition": "development",
               "context_sha256": supplied["context_sha256"],
               "evaluated_context_sha256": pack["context_sha256"],
               "labels_sha256": digest(labels), "implementation_sha256": pack["implementation_sha256"],
               "hybrid_policy_sha256": hybrid.policy_sha256, "source_count": len(pack["sources"]),
               "single_cue": baseline, "contextual": contextual,
               "recognition_qualified": False, "release_qualified": False}
    return {**payload, "report_sha256": digest(payload)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sample and qualify equation-rich development checkpoints")
    parser.add_argument("--prior", type=Path, default=OUTPUT_ROOT / "development.json")
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / "work")
    parser.add_argument("--book", action="append", default=[])
    parser.add_argument("--profile-key")
    parser.add_argument("--equations", type=int, default=DEFAULT_QUOTAS["equation_hint"])
    parser.add_argument("--boundaries", type=int, default=DEFAULT_QUOTAS["boundary_hint"])
    parser.add_argument("--hard-negatives", type=int, default=DEFAULT_QUOTAS["hard_negative_hint"])
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--context", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--requalify", action="store_true")
    args = parser.parse_args(argv)
    scoring = args.context is not None and args.labels is not None
    if (int(args.inventory) + int(bool(args.name)) + int(scoring) != 1
            or bool(args.context) != bool(args.labels) or args.requalify and not scoring):
        parser.error("Choose --inventory, --name, or --context and --labels")
    try:
        prior = load_json(args.prior)
        hybrid, _, _ = build_hybrid()
        quotas = dict(zip(STRATA, (args.equations, args.boundaries, args.hard_negatives)))
        if scoring:
            supplied = load_json(args.context)
            check_digest(supplied, "context_sha256")
            if supplied.get("schema") != SCHEMA or supplied.get("inventory_only") is not False:
                raise ValueError("Expected expanded development evidence")
            config = supplied["selection"]
            pack, originals = expansion(args.work_dir, prior, hybrid, books=config["books"],
                                        profile_key=config["profile_key"], quotas=config["quotas"])
            report = compare(pack, originals, supplied, load_json(args.labels), hybrid, args.requalify)
        else:
            pack, _ = expansion(args.work_dir, prior, hybrid, books=args.book, profile_key=args.profile_key,
                                quotas=quotas, inventory=args.inventory)
            report = {k: v for k, v in pack.items() if k != "windows"}
            report["anchors"] = sum(len(row["anchors"]) for row in pack["windows"])
            report["windows"] = len(pack["windows"])
            if args.name:
                if not report["anchors"]:
                    raise ValueError("No additional candidates; select more STEM checkpoint sources")
                report["output"] = str(save_sample(pack, args.name))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        parser.exit(1, "Development expansion failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
