import argparse
from collections import Counter
import hashlib
import heapq
import itertools
import json
from pathlib import Path
import re

from heavy import MAX_BOOK_MS, PROFILE_PREFIX, ROOT as REPO_ROOT
from transcriber.contract import AudioIdentity, Cue, MAX_WINDOW_MS, TranscriptWindow

from .compiler import canonical_bytes
from .corpus_model import digest, strict_object

SCHEMA = "fitbaus.stem.checkpoint-sample/v1"
SAMPLER_VERSION = "1"
MAX_WINDOW_BYTES = 1024 * 1024
MAX_WINDOWS = 20000
MAX_CANDIDATES = 1000
MAX_PACK_BYTES = 8 * 1024 * 1024
OUTPUT_ROOT = REPO_ROOT / "work" / "stem-qualification"
BOOK_KEY = re.compile(r"[0-9a-f]{64}")
PROFILE_KEY = re.compile(r"[0-9a-f]{16}")
WINDOW_NAME = re.compile(r"(0|[1-9][0-9]{0,9})\.json")
FORMULA_HINT = re.compile(
    r"[=≤≥≠±∑∫√²³⁴]|"
    r"\b(?:equals?|equal\s+to|greater\s+than|less\s+than|"
    r"divided\s+by|multiplied\s+by|squared|cubed|"
    r"raised\s+to|power\s+of|square\s+root|"
    r"derivative|integral|factorial|proportional\s+to|"
    r"denominator|numerator|subscript|equation|formula)\b",
    re.IGNORECASE,
)
PROFILE_KEYS = {
    hashlib.sha256((PROFILE_PREFIX + language).encode("ascii")).hexdigest()[:16]:
        PROFILE_PREFIX + language
    for language in itertools.chain(("auto",),
        (a + b for a in "abcdefghijklmnopqrstuvwxyz" for b in "abcdefghijklmnopqrstuvwxyz"))
}


def link_like(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def require_directory(path):
    if link_like(path) or not path.is_dir():
        raise ValueError("Expected ordinary directory: " + str(path))


def read_checkpoint(path, book_key):
    if link_like(path) or not path.is_file():
        raise ValueError("Invalid checkpoint file: " + path.name)
    with path.open("rb") as stream:
        raw = stream.read(MAX_WINDOW_BYTES + 1)
    if len(raw) > MAX_WINDOW_BYTES:
        raise ValueError("Checkpoint exceeds window size limit: " + path.name)
    value = json.loads(raw, object_pairs_hook=strict_object,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))
    if not isinstance(value, dict) or not isinstance(value.get("cues"), list):
        raise ValueError("Invalid checkpoint object: " + path.name)
    identity = AudioIdentity(value["source_id"], value["item_id"], value["audio_revision"])
    start, end = value["coverage"]["start_ms"], value["coverage"]["end_ms"]
    window = TranscriptWindow(identity, start, end, tuple(
        Cue(row["start_ms"], row["end_ms"], row["text"]) for row in value["cues"]))
    if (identity.cache_key() != book_key or path.name != f"{start}.json"
            or start % MAX_WINDOW_MS or end > MAX_BOOK_MS or value != window.to_json()):
        raise ValueError("Checkpoint identity, alignment or contract mismatch: " + path.name)
    for cue in window.cues:
        if any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in cue.text):
            raise ValueError("Unsupported cue text: " + path.name)
    return window, hashlib.sha256(raw).hexdigest()


def checkpoint_directories(work, books=(), profile_key=None):
    require_directory(work)
    if any(not isinstance(key, str) or not BOOK_KEY.fullmatch(key) for key in books):
        raise ValueError("Book selections must be exact cache keys")
    if profile_key is not None and profile_key not in PROFILE_KEYS:
        raise ValueError("Unknown heavy profile key")
    selected = set(books)
    found = set()
    for book in sorted(work.iterdir()):
        if not BOOK_KEY.fullmatch(book.name) or selected and book.name not in selected:
            continue
        require_directory(book)
        found.add(book.name)
        for profile in sorted(book.iterdir()):
            if not PROFILE_KEY.fullmatch(profile.name):
                continue
            require_directory(profile)
            if profile_key is not None and profile.name != profile_key:
                continue
            if profile.name in PROFILE_KEYS:
                yield book.name, profile
    if selected - found:
        raise ValueError("Selected cache key not found")


def window_paths(directory):
    paths = []
    for path in directory.iterdir():
        if WINDOW_NAME.fullmatch(path.name):
            paths.append(path)
            if len(paths) > MAX_BOOK_MS // MAX_WINDOW_MS:
                raise ValueError("Too many windows in checkpoint directory")
    return sorted(paths, key=lambda path: int(path.stem))


def rank(seed, domain, value):
    return int(digest({"seed": seed, "domain": domain, "value": value}), 16)


def partition_for(seed, book_key, start):
    return "holdout" if rank(seed, "partition", [book_key, start]) % 4 == 0 else "development"


def offer(heap, limit, row, priority):
    if limit == 0:
        return
    item = (-priority, row["id"], row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item[:2] > heap[0][:2]:
        heapq.heapreplace(heap, item)


def ordered(heap):
    return [item[2] for item in sorted(heap, key=lambda item: (-item[0], item[1]))]


def scan(work, books=(), profile_key=None, seed=42, partition="development",
         uniform_count=100, targeted_count=100, inventory=False):
    if (type(seed) is not int or not 0 <= seed < 2**32
            or partition not in ("development", "holdout")
            or any(type(count) is not int or not 0 <= count <= MAX_CANDIDATES
                   for count in (uniform_count, targeted_count))
            or not inventory and not 1 <= uniform_count + targeted_count <= MAX_CANDIDATES):
        raise ValueError("Invalid sample configuration")
    work = Path(work)
    if link_like(work):
        raise ValueError("Work directory must not be a link")
    uniform, targeted, records, sources = [], [], [], []
    totals = Counter()
    for book_key, directory in checkpoint_directories(work, books, profile_key):
        paths = window_paths(directory)
        if not paths:
            continue
        source = {"book_key": book_key, "profile_key": directory.name,
                  "profile": PROFILE_KEYS[directory.name], "profile_verified": False,
                  "windows": 0, "cues": 0, "covered_ms": 0,
                  "development_windows": 0, "holdout_windows": 0}
        previous_end = 0
        for path in paths:
            if totals["windows"] >= MAX_WINDOWS:
                raise ValueError("Checkpoint scan limit; select fewer books")
            window, sha = read_checkpoint(path, book_key)
            if window.start_ms < previous_end:
                raise ValueError("Overlapping checkpoint windows")
            if source["windows"] and previous_end % MAX_WINDOW_MS:
                raise ValueError("Partial checkpoint followed by another window")
            previous_end = window.end_ms
            group = partition_for(seed, book_key, window.start_ms)
            records.append({"book_key": book_key, "profile_key": directory.name,
                            "start_ms": window.start_ms, "end_ms": window.end_ms,
                            "sha256": sha, "partition": group, "cues": len(window.cues)})
            source["windows"] += 1
            source[group + "_windows"] += 1
            source["cues"] += len(window.cues)
            source["covered_ms"] += window.end_ms - window.start_ms
            totals.update(windows=1, cues=len(window.cues))
            if inventory or group != partition:
                continue
            totals["partition_windows"] += 1
            for index, cue in enumerate(window.cues):
                totals["eligible_cues"] += 1
                likely = FORMULA_HINT.search(cue.text) is not None
                totals["formula_hint_cues"] += int(likely)
                key = digest({"book_key": book_key, "profile_key": directory.name,
                              "window_start_ms": window.start_ms, "cue_index": index})
                row = {"id": key, "book_key": book_key, "profile_key": directory.name,
                       "window_start_ms": window.start_ms, "checkpoint_sha256": sha,
                       "cue_index": index, "start_ms": cue.start_ms, "end_ms": cue.end_ms,
                       "text": cue.text, "expected": None}
                offer(uniform, uniform_count, row, rank(seed, "uniform", key))
                if likely:
                    offer(targeted, uniform_count + targeted_count, row, rank(seed, "targeted", key))
        sources.append(source)
    if not records:
        raise ValueError("No compatible heavy transcript checkpoints found")
    selected = ordered(uniform)
    uniform_ids = {row["id"] for row in selected}
    rows = [{**row, "stratum": "uniform"} for row in selected]
    rows.extend({**row, "stratum": "formula_hint"} for row in
                [row for row in ordered(targeted) if row["id"] not in uniform_ids][:targeted_count])
    counts = {key: totals[key] for key in ("windows", "cues", "partition_windows",
                                          "eligible_cues", "formula_hint_cues")}
    counts.update(uniform_selected=len(selected), formula_hint_selected=len(rows) - len(selected))
    payload = {"schema": SCHEMA, "sampler_version": SAMPLER_VERSION,
               "seed": seed, "partition": partition, "inventory_only": inventory,
               "requested": {"uniform": uniform_count, "formula_hint": targeted_count},
               "source_snapshot_sha256": digest(records), "sources": sources,
               "counts": counts, "cases": rows, "labels_complete": False,
               "recognition_qualified": False}
    return {**payload, "sample_sha256": digest(payload)}


def save_sample(pack, name, output_root=OUTPUT_ROOT):
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\.json", name):
        raise ValueError("Use a simple JSON filename")
    output_root = Path(output_root)
    if any(link_like(path) for path in (output_root, *output_root.parents)):
        raise ValueError("Output directory must not traverse a link")
    raw = canonical_bytes(pack)
    if len(raw) > MAX_PACK_BYTES:
        raise ValueError("Sample pack size limit")
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / name
    with path.open("xb") as stream:
        stream.write(raw)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sample existing heavy transcript checkpoints without inference")
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / "work")
    parser.add_argument("--book", action="append", default=[], help="Exact cache key from inventory; repeat to select books")
    parser.add_argument("--profile-key", help="Exact heavy profile key from inventory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--partition", choices=("development", "holdout"), default="development")
    parser.add_argument("--uniform", type=int, default=100)
    parser.add_argument("--targeted", type=int, default=100)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--name", help="New JSON filename under work/stem-qualification")
    args = parser.parse_args(argv)
    if args.inventory == bool(args.name):
        parser.error("Choose either --inventory or --name")
    try:
        pack = scan(args.work_dir, args.book, args.profile_key, args.seed, args.partition,
                    args.uniform, args.targeted, args.inventory)
        summary = {key: value for key, value in pack.items() if key != "cases"}
        if args.name:
            if not pack["cases"]:
                raise ValueError("No eligible cues in the requested partition")
            summary["output"] = str(save_sample(pack, args.name))
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        parser.exit(1, "Checkpoint sampling failed: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
