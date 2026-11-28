import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from epub_assets import MAX_ASSET_BYTES, MAX_TOTAL_BYTES, MAX_OCCURRENCES, RASTER
from epub_timing import MAX_INTERVAL_MS, MAX_SIDE_WORDS, MIN_INSIDE_WORDS, POLICY, SCHEMA as TIMING_SCHEMA


SCHEMA = "fitbaus.epub-enrichment/v1"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_STORE_BYTES = 512 * 1024 * 1024
MAX_STORE_FILES = 128
DIGEST = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
MEDIA_TYPES = RASTER | {"application/mathml+xml", "image/svg+xml"}


class EnrichmentError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def build_artifact(result):
    if (result["schema"] != TIMING_SCHEMA or result["policy"] != POLICY
            or any(result[key] is not False for key in
                   ("edition_verified", "render_qualified", "playback_qualified"))):
        raise EnrichmentError("Unsupported enrichment evidence contract")
    identity = {key: result[key] for key in
                ("source_id", "item_id", "file_id", "audio_revision", "profile", "duration_ms",
                 "epub_sha256", "transcript_sha256")}
    if (any(not IDENTIFIER.fullmatch(identity[key]) for key in ("source_id", "item_id", "file_id"))
            or any(not DIGEST.fullmatch(identity[key]) for key in
                   ("audio_revision", "epub_sha256", "transcript_sha256"))
            or not isinstance(identity["profile"], str) or not 1 <= len(identity["profile"]) <= 256
            or type(identity["duration_ms"]) is not int or identity["duration_ms"] <= 0):
        raise EnrichmentError("Invalid enrichment provenance")
    assets = []
    asset_ids = set()
    total_bytes = 0
    for asset in result["assets"]:
        payload = asset["payload"]
        media_type = asset["media_type"]
        if (not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_ASSET_BYTES
                or media_type not in MEDIA_TYPES or asset["size"] != len(payload)):
            raise EnrichmentError("Invalid visual payload")
        digest = hashlib.sha256(payload).hexdigest()
        asset_id = hashlib.sha256((media_type + ":" + digest).encode("ascii")).hexdigest()
        if asset["sha256"] != digest or asset["asset_id"] != asset_id or asset_id in asset_ids:
            raise EnrichmentError("Invalid or duplicated visual identity")
        if ((media_type in RASTER and (asset["kind"], asset["representation"]) != ("raster", "original_bytes"))
                or (media_type == "application/mathml+xml" and
                    (asset["kind"], asset["representation"]) != ("mathml", "xml_subtree"))
                or (media_type == "image/svg+xml" and
                    (asset["kind"] != "svg" or asset["representation"] not in ("xml_subtree", "original_bytes")))):
            raise EnrichmentError("Invalid visual representation")
        asset_ids.add(asset_id)
        total_bytes += len(payload)
        if total_bytes > MAX_TOTAL_BYTES or len(asset_ids) > MAX_OCCURRENCES:
            raise EnrichmentError("Visual catalogue exceeds artifact limits")
        assets.append({key: asset[key] for key in
                       ("asset_id", "sha256", "kind", "media_type", "size", "representation")}
                      | {"payload_base64": base64.b64encode(payload).decode("ascii")})
    occurrences = result["occurrences"]
    if len(occurrences) > MAX_OCCURRENCES or len(occurrences) != result["occurrence_count"]:
        raise EnrichmentError("Invalid occurrence count")
    references, reasons, methods = set(), Counter(), Counter()
    for index, row in enumerate(occurrences):
        if row["occurrence_index"] != index or row["asset_id"] not in asset_ids:
            raise EnrichmentError("Invalid visual occurrence")
        references.add(row["asset_id"])
        evidence, reason = row["evidence"], row["untimed_reason"]
        if evidence is None:
            if not isinstance(reason, str) or not reason:
                raise EnrichmentError("Missing timing abstention reason")
            reasons[reason] += 1
            continue
        start, end = evidence["earliest_ms"], evidence["latest_ms"]
        method = evidence["method"]
        if (reason is not None or method not in ("within_exact_cue", "between_adjacent_exact_cues")
                or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= identity["duration_ms"] or end - start > MAX_INTERVAL_MS
                or type(row["ebook_word_position"]) is not int or row["ebook_word_position"] < 0):
            raise EnrichmentError("Invalid bounded timing evidence")
        indices, ranges = evidence["cue_indices"], evidence["anchor_word_ranges"]
        expected = 1 if method == "within_exact_cue" else 2
        if (len(indices) != expected or len(ranges) != expected
                or any(type(i) is not int or not 0 <= i < result["cue_count"] for i in indices)
                or any(len(pair) != 2 or any(type(n) is not int for n in pair)
                       or not 0 <= pair[0] < pair[1] for pair in ranges)):
            raise EnrichmentError("Invalid supporting anchor coordinates")
        position = row["ebook_word_position"]
        if expected == 1:
            left, right = ranges[0]
            valid = min(position - left, right - position) >= MIN_INSIDE_WORDS
        else:
            valid = (indices[1] == indices[0] + 1
                     and 0 <= position - ranges[0][1] <= MAX_SIDE_WORDS
                     and 0 <= ranges[1][0] - position <= MAX_SIDE_WORDS)
        if not valid:
            raise EnrichmentError("Supporting anchors do not satisfy timing policy")
        methods[method] += 1
    summary = {"occurrence_count": len(occurrences), "unique_asset_count": len(asset_ids),
               "timed_count": sum(methods.values()), "untimed_count": sum(reasons.values()),
               "timing_methods": dict(methods), "untimed_reasons": dict(reasons),
               "skipped_count": result["skipped_count"], "cue_count": result["cue_count"],
               "matched_cue_count": result["matched_cue_count"]}
    if references != asset_ids or any(summary[key] != result[key] for key in summary):
        raise EnrichmentError("Enrichment evidence counts disagree")
    return {"schema": SCHEMA, "timing_policy": POLICY, "identity": identity,
            "edition_verified": False, "render_qualified": False, "playback_qualified": False,
            "summary": summary, "assets": sorted(assets, key=lambda asset: asset["asset_id"]),
            "occurrences": occurrences}


def store_artifact(root, artifact):
    raw = canonical(artifact)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise EnrichmentError("Enrichment artifact exceeds size limit")
    artifact_id = hashlib.sha256(raw).hexdigest()
    directory = Path(root) / "enrichment"
    if directory.is_symlink():
        raise EnrichmentError("Enrichment store must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (artifact_id + ".json")
    if destination.is_symlink():
        raise EnrichmentError("Enrichment artifact must not be a symlink")
    reused = destination.exists()
    if reused:
        if not destination.is_file():
            raise EnrichmentError("Invalid enrichment artifact destination")
        with destination.open("rb") as stream:
            if stream.read(MAX_ARTIFACT_BYTES + 1) != raw:
                raise EnrichmentError("Existing enrichment artifact is corrupt")
    else:
        total, count = 0, 0
        for path in directory.glob("*.json"):
            if path.is_symlink() or not path.is_file():
                raise EnrichmentError("Invalid enrichment store entry")
            count += 1
            total += path.stat().st_size
            if count >= MAX_STORE_FILES or total + len(raw) > MAX_STORE_BYTES:
                raise EnrichmentError("Enrichment store is full; remove obsolete local artifacts")
        if len(raw) > MAX_STORE_BYTES or MAX_STORE_FILES < 1:
            raise EnrichmentError("Enrichment store is full")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".prepare-", suffix=".tmp",
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"schema": SCHEMA, "artifact_id": artifact_id, "artifact_bytes": len(raw),
            "reused": reused, "edition_verified": False, "render_qualified": False,
            "playback_qualified": False, **artifact["summary"]}


def prepare_artifact(root, result):
    return store_artifact(root, build_artifact(result))
