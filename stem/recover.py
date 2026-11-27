import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .acquire import AcquisitionError, MAX_ATTEMPTS, MAX_TOTAL_WAIT, USER_AGENT, retry_delay
from .analyze import counts, load_snapshot, unpack
from .dictionary import validate_latex
from .prioritize import VERSION as PRIORITIZER_VERSION, classify_label, write_row

ENDPOINT = "https://www.wikidata.org/w/api.php"
SCHEMA = "fitbaus.stem.original-tex/v1"
BATCH_SIZE = 25
MAX_RESPONSE = 16 * 1024 * 1024
MAX_CHECKPOINT = MAX_RESPONSE * 6 + 65536
MAX_FORMULA = 65536
REQUEST_INTERVAL = 1.0
COMMAND = re.compile(r"\\([A-Za-z]+|.)?")


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def plan(directory):
    source_digest, _, rows = load_snapshot(directory)
    labels = defaultdict(set)
    for row in rows:
        try:
            entity, label, _ = unpack(row)
        except ValueError:
            continue
        if classify_label(entity, label) == "potentially_named":
            labels[entity].add(label)
    entities = sorted(labels, key=lambda q: int(q[1:]))
    batches = [entities[i:i + BATCH_SIZE] for i in range(0, len(entities), BATCH_SIZE)]
    return {
        "schema": SCHEMA, "source_sha256": source_digest, "source": "wikidata",
        "license": "CC0-1.0", "endpoint": ENDPOINT, "property": "P2534",
        "prioritizer": PRIORITIZER_VERSION, "batch_size": BATCH_SIZE,
        "entities": len(entities), "batches": batches, "status": "candidate_only",
    }, labels


def parse_response(raw, ids):
    if len(raw) > MAX_RESPONSE:
        raise AcquisitionError("API response exceeds size limit")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("invalid response")
        if "error" in payload:
            raise AcquisitionError("Wikidata API error: " + str(payload["error"].get("code", "unknown")))
        entities = payload["entities"]
        if not isinstance(entities, dict) or set(entities) != set(ids):
            raise ValueError("response entity set differs from requested set")
        for entity_id, entity in entities.items():
            if not isinstance(entity, dict) or entity.get("id") != entity_id:
                raise ValueError("entity identity mismatch")
            if "missing" in entity:
                continue
            if type(entity.get("lastrevid")) is not int or entity["lastrevid"] <= 0:
                raise ValueError("missing entity revision")
            claims = entity.get("claims")
            if not isinstance(claims, dict) or not isinstance(claims.get("P2534", []), list):
                raise ValueError("invalid claims")
            seen = set()
            for claim in claims.get("P2534", []):
                if not isinstance(claim, dict):
                    raise ValueError("invalid claim")
                statement_id = claim.get("id")
                if (not isinstance(statement_id, str) or not statement_id.startswith(entity_id + "$")
                        or statement_id in seen):
                    raise ValueError("invalid or duplicate statement ID")
                seen.add(statement_id)
                if claim.get("rank") not in {"preferred", "normal", "deprecated"}:
                    raise ValueError("invalid statement rank")
                snak = claim.get("mainsnak")
                if not isinstance(snak, dict) or snak.get("property") != "P2534":
                    raise ValueError("invalid formula snak")
                if snak.get("snaktype") not in {"value", "novalue", "somevalue"}:
                    raise ValueError("invalid snak type")
                if snak["snaktype"] == "value":
                    value = snak.get("datavalue")
                    if (not isinstance(value, dict) or value.get("type") != "string"
                            or not isinstance(value.get("value"), str)
                            or snak.get("datatype") != "math"):
                        raise ValueError("invalid mathematical value")
        return entities
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise AcquisitionError("Invalid Wikidata entity response: " + str(error)) from error


def fetch_batch(ids):
    request = Request(ENDPOINT + "?" + urlencode({
        "action": "wbgetentities", "ids": "|".join(ids), "props": "claims|info",
        "format": "json", "maxlag": "5",
    }), headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    remaining = MAX_TOTAL_WAIT
    for attempt in range(1, MAX_ATTEMPTS + 1):
        header = None
        try:
            time.sleep(REQUEST_INTERVAL)
            with urlopen(request, timeout=60) as response:
                raw = response.read(MAX_RESPONSE + 1)
                header = response.headers.get("Retry-After")
            if len(raw) > MAX_RESPONSE:
                raise AcquisitionError("API response exceeds size limit")
            payload = json.loads(raw)
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("code") == "maxlag":
                reason = "maxlag"
            else:
                parse_response(raw, ids)
                return raw
        except HTTPError as error:
            status = error.code
            header = error.headers.get("Retry-After") if error.headers else None
            error.close()
            if status not in (429, 503):
                raise AcquisitionError(f"Wikidata HTTP {status}; retry manually after inspection") from None
            reason = f"HTTP {status}"
        except (URLError, TimeoutError, ValueError) as error:
            raise AcquisitionError("Wikidata request failed; completed batches retained") from error
        delay = retry_delay(header, attempt)
        if attempt == MAX_ATTEMPTS or delay > remaining:
            raise AcquisitionError(f"Wikidata {reason}; stop and retry after at least {delay} seconds")
        print(f"Wikidata {reason}; retry in {delay} seconds", file=sys.stderr, flush=True)
        time.sleep(delay)
        remaining -= delay
    raise AcquisitionError("Wikidata retry budget exhausted")


def read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise AcquisitionError(f"{path.name} exceeds size limit")
    return raw


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    temporary.replace(path)


def checkpoint(path, ids, raw=None):
    if raw is not None:
        parse_response(raw, ids)
        payload = {"ids": ids, "response_sha256": digest_bytes(raw),
                   "response_utf8": raw.decode("utf-8")}
        atomic_json(path, payload)
    payload = json.loads(read_bounded(path, MAX_CHECKPOINT))
    if not isinstance(payload, dict) or payload.get("ids") != ids:
        raise AcquisitionError("Checkpoint request identity mismatch")
    value = payload.get("response_utf8")
    if not isinstance(value, str):
        raise AcquisitionError("Checkpoint has no response")
    stored = value.encode("utf-8")
    if payload.get("response_sha256") != digest_bytes(stored):
        raise AcquisitionError("Checkpoint response SHA-256 mismatch")
    return payload["response_sha256"], parse_response(stored, ids)


def lexical_status(formula):
    if not formula.strip():
        return "empty_formula"
    if "\ufffd" in formula:
        return "source_replacement_character"
    if len(formula) > MAX_FORMULA:
        return "formula_size_limit"
    try:
        validate_latex(formula)
    except ValueError as error:
        return str(error)
    return "passes_lexical_screen"


def summarize(output, manifest, labels, completed):
    outcomes, lexical, commands = Counter(), Counter(), Counter()
    unique = set()
    named_count = 0
    temporary = output / "original-tex.jsonl.tmp"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for index in range(completed):
            ids = manifest["batches"][index]
            batch_digest, entities = checkpoint(output / "batches" / f"{index:05d}.json", ids)
            for entity_id in ids:
                entity = entities[entity_id]
                if "missing" in entity:
                    outcomes["missing_entity"] += 1
                    continue
                claims = entity["claims"].get("P2534", [])
                outcomes["entity_with_formula_claims" if claims else "entity_without_formula_claims"] += 1
                for claim in sorted(claims, key=lambda row: row["id"]):
                    snak = claim["mainsnak"]
                    if claim["rank"] == "deprecated":
                        outcomes["deprecated_statement"] += 1
                        continue
                    if snak["snaktype"] != "value":
                        outcomes["non_value_statement"] += 1
                        continue
                    formula = snak["datavalue"]["value"]
                    status = lexical_status(formula)
                    lexical[status] += 1
                    if status in {"empty_formula", "formula_size_limit", "source_replacement_character"}:
                        outcomes["deferred_invalid_source_value"] += 1
                        continue
                    commands.update({m.group(1) or "<dangling>" for m in COMMAND.finditer(formula)})
                    unique.add(formula)
                    record = {
                        "entity": entity_id, "labels": sorted(labels[entity_id]),
                        "statement_id": claim["id"], "entity_revision": entity["lastrevid"],
                        "rank": claim["rank"], "latex": formula, "lexical_screen": status,
                        "source_sha256": manifest["source_sha256"],
                        "response_sha256": batch_digest, "batch": index,
                        "formula_sha256": digest_bytes(formula.encode("utf-8")),
                        "source": "wikidata", "license": "CC0-1.0",
                        "representation": "original_tex", "status": "candidate_only",
                    }
                    write_row(stream, record)
                    named_count += 1
    temporary.replace(output / "original-tex.jsonl")
    report = {
        "schema": SCHEMA, "source_sha256": manifest["source_sha256"],
        "entities_requested": manifest["entities"], "entities_completed": sum(
            len(ids) for ids in manifest["batches"][:completed]),
        "batches_completed": completed, "batches_total": len(manifest["batches"]),
        "complete": completed == len(manifest["batches"]),
        "outcomes": counts(outcomes), "lexical_screen": counts(lexical),
        "candidate_statements": named_count, "unique_exact_latex": len(unique),
        "command_document_frequency": counts(commands),
        "spoken_aliases_verified": 0, "status": "candidate_only",
    }
    atomic_json(output / "recovery.json", report)
    return report


def recover(directory, output, max_batches=None, fetch=None):
    source = Path(directory).resolve()
    output = Path(output).resolve()
    if output == source or source in output.parents:
        raise AcquisitionError("Output must be outside the immutable snapshot")
    if max_batches is not None and max_batches < 1:
        raise AcquisitionError("max-batches must be positive")
    manifest, labels = plan(source)
    if not manifest["entities"]:
        raise AcquisitionError("No named entities in snapshot")
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "plan.json"
    if plan_path.exists():
        if json.loads(read_bounded(plan_path, 2 * 1024 * 1024)) != manifest:
            raise AcquisitionError("Existing recovery plan differs; use a new directory")
    else:
        if any(output.iterdir()):
            raise AcquisitionError("Existing output directory has no recovery plan")
        atomic_json(plan_path, manifest)
    batch_dir = output / "batches"
    batch_dir.mkdir(exist_ok=True)
    fetch = fetch or fetch_batch
    completed = requested = 0
    for index, ids in enumerate(manifest["batches"]):
        path = batch_dir / f"{index:05d}.json"
        if path.exists():
            checkpoint(path, ids)
        else:
            if max_batches is not None and requested >= max_batches:
                break
            checkpoint(path, ids, fetch(ids))
            requested += 1
            print(f"Saved batch {index + 1}/{len(manifest['batches'])}", file=sys.stderr, flush=True)
        completed += 1
    return summarize(output, manifest, labels, completed)


def main():
    parser = argparse.ArgumentParser(description="Recover original Wikidata TeX for named entities")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-batches", type=int, help="Maximum new requests in this invocation")
    args = parser.parse_args()
    try:
        report = recover(args.snapshot, args.output, args.max_batches)
        print(json.dumps({key: value for key, value in report.items()
                          if key != "command_document_frequency"}, indent=2))
        print(f"Reports: {args.output.resolve()}")
    except (AcquisitionError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Recovery stopped: {error}\n")


if __name__ == "__main__":
    main()
