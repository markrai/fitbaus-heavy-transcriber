import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = """SELECT DISTINCT ?item ?itemLabel ?formula WHERE {
  ?item wdt:P2534 ?formula.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY ?item ?formula"""
MAX_BYTES = 16 * 1024 * 1024


def snapshot(output):
    request = Request(ENDPOINT + "?" + urlencode({"query": QUERY, "format": "json"}),
                      headers={"Accept": "application/sparql-results+json",
                               "User-Agent": "FitBausHeavyTranscriber/1.0 (https://github.com/markrai/fitbaus-heavy-transcriber)"})
    with urlopen(request, timeout=90) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Corpus snapshot exceeds limit")
    payload = json.loads(raw)
    bindings = payload["results"]["bindings"]
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("Empty or invalid Wikidata snapshot")
    for row in bindings:
        if not all(isinstance(row.get(key, {}).get("value"), str) for key in ("item", "itemLabel", "formula")):
            raise ValueError("Invalid Wikidata binding")
    digest = hashlib.sha256(raw).hexdigest()
    destination = Path(output) / digest
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "snapshot.json").write_bytes(raw)
    manifest = {"source": "wikidata", "license": "CC0-1.0", "endpoint": ENDPOINT,
                "query": QUERY, "sha256": digest, "rows": len(bindings),
                "status": "candidate_only"}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Capture a review-only Wikidata formula snapshot")
    parser.add_argument("output", help="Local output directory outside tracked source files")
    args = parser.parse_args()
    print(json.dumps(snapshot(args.output), indent=2))


if __name__ == "__main__":
    main()
