import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

from epub_assets import RASTER
from epub_enrichment import (DIGEST, EnrichmentError, MAX_ARTIFACT_BYTES, SCHEMA as SOURCE_SCHEMA,
                             build_artifact, canonical, store_artifact)
from epub_timing import SCHEMA as TIMING_SCHEMA


SCHEMA = "fitbaus.epub-delivery-candidate/v1"
POLICY = "static-rgba-png/v1"
MAX_PNG = 1024 * 1024
MAX_WIDTH = 1024
MAX_HEIGHT = 600
MAX_ASSETS = 128
MAX_TOTAL_PNG = 16 * 1024 * 1024
WORKER_TIMEOUT = 10
WORKER = Path(__file__).resolve().with_name("epub_raster_worker.py")


class DeliveryError(ValueError):
    pass


def read_source(root, artifact_id):
    if not isinstance(artifact_id, str) or not DIGEST.fullmatch(artifact_id):
        raise DeliveryError("Invalid enrichment artifact ID")
    directory = Path(root) / "enrichment"
    path = directory / (artifact_id + ".json")
    if directory.is_symlink() or path.is_symlink() or not path.is_file():
        raise DeliveryError("Enrichment artifact unavailable")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES or hashlib.sha256(raw).hexdigest() != artifact_id:
        raise DeliveryError("Enrichment artifact digest or size mismatch")
    try:
        artifact = json.loads(raw)
        if artifact["schema"] != SOURCE_SCHEMA or canonical(artifact) != raw:
            raise ValueError()
        assets = []
        for asset in artifact["assets"]:
            row = dict(asset)
            row["payload"] = base64.b64decode(row.pop("payload_base64"), validate=True)
            assets.append(row)
        result = {**artifact["identity"], **artifact["summary"], "schema": TIMING_SCHEMA,
                  "policy": artifact["timing_policy"], "assets": assets,
                  "occurrences": artifact["occurrences"],
                  **{key: artifact[key] for key in
                     ("edition_verified", "render_qualified", "playback_qualified")}}
        if canonical(build_artifact(result)) != raw:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise DeliveryError("Invalid enrichment artifact contract") from None
    return artifact, assets


def png_dimensions(raw):
    if not 0 < len(raw) <= MAX_PNG or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise DeliveryError("Invalid normalized PNG")
    offset, width, height = 8, 0, 0
    compressed = bytearray()
    while offset + 12 <= len(raw):
        length = struct.unpack_from(">I", raw, offset)[0]
        end = offset + 12 + length
        if end > len(raw):
            break
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:end - 4]
        if zlib.crc32(kind + data) != struct.unpack_from(">I", raw, end - 4)[0]:
            break
        if kind == b"IHDR" and offset == 8 and length == 13:
            width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", data)
            if (not 0 < width <= MAX_WIDTH or not 0 < height <= MAX_HEIGHT
                    or (depth, color, comp, filt, interlace) != (8, 6, 0, 0, 0)):
                break
        elif kind == b"IDAT" and width:
            compressed.extend(data)
        elif kind == b"IEND" and width and length == 0 and end == len(raw) and compressed:
            expected = height * (1 + 4 * width)
            try:
                decoder = zlib.decompressobj()
                pixels = decoder.decompress(compressed, expected + 1)
                if (len(pixels) == expected and decoder.eof and not decoder.unused_data
                        and not decoder.unconsumed_tail
                        and all(pixels[i] <= 4 for i in range(0, expected, 1 + 4 * width))):
                    return width, height
            except zlib.error:
                pass
            break
        else:
            break
        offset = end
    raise DeliveryError("Invalid normalized PNG structure")


def normalize_raster(asset):
    try:
        result = subprocess.run([sys.executable, "-I", str(WORKER), asset["media_type"]],
                                input=asset["payload"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=WORKER_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return None, "decode_timeout"
    if result.returncode == 2:
        return None, "unsupported_or_invalid_raster"
    if result.returncode != 0:
        raise DeliveryError("Raster worker failed; install the pinned delivery requirements")
    try:
        width, height = png_dimensions(result.stdout)
    except DeliveryError:
        return None, "invalid_worker_output"
    return {"png_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "width": width, "height": height, "size": len(result.stdout),
            "payload_base64": base64.b64encode(result.stdout).decode("ascii")}, None


def build_delivery(artifact_id, artifact, assets):
    timed = {row["asset_id"] for row in artifact["occurrences"] if row["evidence"] is not None}
    eligible = [asset for asset in assets if asset["asset_id"] in timed and asset["media_type"] in RASTER]
    if len(eligible) > MAX_ASSETS:
        raise DeliveryError("Timed raster count exceeds delivery candidate limit")
    rendered, failures, pngs = {}, {}, {}
    total = 0
    for asset in eligible:
        output, reason = normalize_raster(asset)
        key = asset["asset_id"]
        if output is None:
            failures[key] = reason
            continue
        digest = output["png_sha256"]
        if digest not in pngs:
            total += output["size"]
            if total > MAX_TOTAL_PNG:
                raise DeliveryError("Delivery candidate exceeds normalized payload limit")
            pngs[digest] = output
        rendered[key] = digest
    occurrences, reasons = [], Counter()
    for row in artifact["occurrences"]:
        key, evidence = row["asset_id"], row["evidence"]
        if evidence is None:
            reason = "no_timing_evidence"
        elif key not in rendered:
            reason = failures.get(key, "renderer_not_supported")
        else:
            occurrences.append({"occurrence_index": row["occurrence_index"], "source_asset_id": key,
                                "png_sha256": rendered[key], "earliest_ms": evidence["earliest_ms"],
                                "latest_ms": evidence["latest_ms"], "method": evidence["method"]})
            continue
        reasons[reason] += 1
    return {"schema": SCHEMA, "render_policy": POLICY, "source_artifact_id": artifact_id,
            "identity": artifact["identity"], "timing_policy": artifact["timing_policy"],
            "edition_verified": False, "render_qualified": False, "playback_qualified": False,
            "summary": {"candidate_count": len(occurrences), "unique_png_count": len(pngs),
                        "withheld_count": sum(reasons.values()), "withheld_reasons": dict(reasons)},
            "pngs": sorted(pngs.values(), key=lambda row: row["png_sha256"]),
            "occurrences": occurrences}


def prepare_delivery(root, artifact_id):
    artifact, assets = read_source(root, artifact_id)
    candidate = build_delivery(artifact_id, artifact, assets)
    return store_artifact(root, candidate, store_name="delivery", schema=SCHEMA)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare local raster-only delivery candidate; does not publish")
    parser.add_argument("artifact_id")
    parser.add_argument("--work-dir", type=Path, default=Path(__file__).resolve().parent / "work")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare_delivery(args.work_dir, args.artifact_id), sort_keys=True))
    except (DeliveryError, EnrichmentError, OSError) as error:
        print("Delivery preparation failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
