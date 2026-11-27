import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = """SELECT DISTINCT ?item ?itemLabel ?formula WHERE {
  ?item wdt:P2534 ?formula.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY ?item ?formula"""
MAX_BYTES = 16 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_TOTAL_WAIT = 120
USER_AGENT = "FitBausHeavyTranscriber/1.0 (https://github.com/markrai/fitbaus-heavy-transcriber)"


class AcquisitionError(RuntimeError):
    pass


def retry_delay(header, attempt):
    if header:
        if header.isascii() and header.isdecimal():
            try:
                return max(1, int(header))
            except ValueError:
                return MAX_TOTAL_WAIT + 1
        try:
            date = parsedate_to_datetime(header)
            if date.tzinfo is not None:
                return max(1, math.ceil((date - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            pass
    return 60 * (2 ** (attempt - 1))


def fetch_snapshot():
    request = Request(ENDPOINT + "?" + urlencode({"query": QUERY, "format": "json"}),
                      headers={"Accept": "application/sparql-results+json",
                               "User-Agent": USER_AGENT})
    remaining = MAX_TOTAL_WAIT
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=75) as response:
                return response.read(MAX_BYTES + 1)
        except HTTPError as error:
            status = error.code
            header = error.headers.get("Retry-After") if error.headers else None
            error.close()
            if status not in (429, 503):
                raise AcquisitionError(f"Wikidata returned HTTP {status}; no snapshot saved.") from None
            delay = retry_delay(header, attempt)
            if attempt == MAX_ATTEMPTS or delay > remaining:
                raise AcquisitionError(
                    f"Wikidata returned HTTP {status}. Retry after at least {delay} seconds "
                    "or use --from-json with an existing query export. No snapshot saved."
                ) from None
            print(f"Wikidata HTTP {status}; retrying in {delay} seconds "
                  f"(attempt {attempt + 1}/{MAX_ATTEMPTS}).", file=sys.stderr, flush=True)
            time.sleep(delay)
            remaining -= delay
        except (URLError, TimeoutError) as error:
            raise AcquisitionError("Wikidata request failed or timed out; retry later or use --from-json.") from error
    raise AcquisitionError("Wikidata retry budget exhausted.")


def store_snapshot(output, raw, *, acquisition):
    if len(raw) > MAX_BYTES:
        raise AcquisitionError("Corpus snapshot exceeds limit")
    try:
        payload = json.loads(raw)
        bindings = payload["results"]["bindings"]
        if not isinstance(bindings, list) or not bindings:
            raise ValueError("Empty bindings")
        for row in bindings:
            if not isinstance(row, dict) or not all(
                isinstance(row.get(key), dict) and isinstance(row[key].get("value"), str)
                and row[key]["value"].strip() for key in ("item", "itemLabel", "formula")
            ):
                raise ValueError("Invalid binding")
    except (ValueError, KeyError, TypeError) as error:
        raise AcquisitionError("Invalid or empty Wikidata SPARQL JSON snapshot") from error
    digest = hashlib.sha256(raw).hexdigest()
    destination = Path(output) / digest
    manifest = {"source": "wikidata", "license": "CC0-1.0", "endpoint": ENDPOINT,
                "query": QUERY if acquisition == "online" else None,
                "acquisition": acquisition, "sha256": digest, "rows": len(bindings),
                "status": "candidate_only"}
    if destination.exists():
        try:
            with (destination / "snapshot.json").open("rb") as stream:
                existing = stream.read(MAX_BYTES + 1)
            with (destination / "manifest.json").open("rb") as stream:
                previous = json.loads(stream.read(65537))
            if existing == raw and isinstance(previous, dict) and all(
                previous.get(key) == manifest[key] for key in ("source", "sha256", "rows", "status")
            ):
                return previous
        except (OSError, ValueError):
            pass
        raise AcquisitionError("Existing snapshot directory is incomplete or inconsistent; inspect it before retrying.")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "snapshot.json").write_bytes(raw)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def snapshot(output, from_json=None):
    if from_json is None:
        return store_snapshot(output, fetch_snapshot(), acquisition="online")
    with Path(from_json).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return store_snapshot(output, raw, acquisition="local_export")


def main():
    parser = argparse.ArgumentParser(description="Capture a review-only Wikidata formula snapshot")
    parser.add_argument("output", help="Local output directory outside tracked source files")
    parser.add_argument("--from-json", type=Path, help="Import an existing Wikidata SPARQL JSON export without network access")
    args = parser.parse_args()
    try:
        print(json.dumps(snapshot(args.output, args.from_json), indent=2))
    except (AcquisitionError, OSError) as error:
        parser.exit(1, f"Acquisition failed: {error}\n")


if __name__ == "__main__":
    main()
