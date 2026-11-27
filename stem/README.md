# Optional STEM enrichment foundation

This package is independent of the normal transcription workflow. No corpus is downloaded, loaded or consulted by app.py or heavy.py. No LLM, GPU, renderer or external dependency is needed for dictionary inspection.

## Local inspection

    python -m stem
    python -m stem --text "Einstein showed that E equals M C squared."

The curated seed has 20 independently authored entries. Each has a stable ID, category, name, LaTeX and explicit spoken aliases. The compiler rejects conflicting aliases and unapproved sources and emits a deterministic content digest. The matcher only accepts a complete sentence-like expression, optionally following a limited explicit introduction. Matching is deliberately conservative, case-insensitive for spoken aliases and not a general mathematical parser. It does not match cross-cue expressions, infer equations from topics, or repair mathematical errors. Offsets are Python Unicode code-point offsets into unchanged source text. LaTeX screening is lexical and structural, not a proof of mathematical correctness or a full renderer security boundary.

## Corpus acquisition

    python -m stem.acquire work/stem-candidates

This explicit online command captures a Wikidata P2534 query response with its exact query and SHA-256 in a content-addressed directory. Results are candidate-only and are never admitted automatically. Wikidata structured data is CC0. Review and author aliases for selected formulas before adding entries. Other sources in corpus/sources.json are not yet approved for redistribution. Do not commit raw datasets or private narration. Keep external source snapshots pinned and record licenses, attribution and per-entry provenance before expanding the admitted source policy.

If Wikidata responds with HTTP 429 or 503, the acquisition command respects Retry-After and uses bounded retries (at most three attempts and 120 seconds of total retry sleep). Longer requested cooldowns stop the command rather than retrying prematurely. If no Retry-After is provided, the fallback delay starts at 60 seconds. Do not repeatedly restart the command while throttled.

Alternatively, open the [Wikidata Query Service](https://query.wikidata.org/) after the cooldown, run the query below, and download the results using **JSON file (verbose)**, which retains the SPARQL results bindings. Online and local snapshots are bounded to 128 MiB; this is an offline workstation acquisition limit, not a runtime dictionary or transcript limit.

    SELECT DISTINCT ?item ?itemLabel ?formula WHERE {
      ?item wdt:P2534 ?formula.
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    } ORDER BY ?item ?formula

Then import the local export without any network request:

    python -m stem.acquire work/stem-candidates --from-json path/to/results.json

Local exports are marked as such, with no assertion about the exact query executed. Reimporting identical snapshot bytes reuses an existing consistent snapshot. Neither online nor offline acquisition automatically admits formulas into the curated dictionary.

## Offline corpus analysis (S.0B)

    python -m stem.analyze work/stem-candidates/<snapshot-sha256> --output work/stem-analysis/<snapshot-sha256>

Use a new output directory for each report. The analyzer verifies the source manifest, checksum and row count before producing analysis.json and analysis.md. It counts exact formula and binding duplicates, entity and normalized-label multiplicity, lexical screen outcomes, command frequencies, heuristic complexity and relevance, and the UTF-8 size of distinct formulas. No formula strings are normalized in ways that might change meaning. Example lists are bounded. Results are deterministic and the snapshot is never modified. No network, GPU, LLM or third-party package is used.

Wikidata formulas are candidates, not spoken aliases. Lexical acceptance is not proof of correct mathematics or safe rendering. Label collisions are review signals, not verified spoken ambiguity. Raw string sizes are not a compiled database estimate. No automatic admission is performed.

## MathML conversion (S.0C)

    python -m stem.convert work/stem-candidates/<snapshot-sha256> --output work/stem-conversion/<snapshot-sha256>

The first full Wikidata snapshot contained 113,049 MathML rows and no annotation elements, according to the operator's preliminary inventory. This explicit offline command verifies the snapshot and writes conversion.json and candidates.jsonl. Each candidate retains the source snapshot digest, source formula digest, row index, entity and converter version. Nothing is admitted to the runtime dictionary.

The initial converter handles simple identifiers, numbers, selected operators and Greek symbols, presentation wrappers, fractions, superscripts, subscripts, combined scripts and square roots. XML parsing rejects declarations, DTDs, foreign namespaces, excessive depth, node counts and document size. Unsupported attributes, tokens and structures fail closed. Matrices, text, spacing elements, under/over notation, nth roots, styled identifiers and additional symbols are deferred. Presentation wrapper styles supported by the converter may be discarded; output is not promised to reproduce exact typography. The existing restricted LaTeX screen remains in force. Conversion does not prove mathematical equivalence, safety of a future renderer, or suitability as a spoken alias.

The report inventories parsed MathML elements and separates original representation from conversion outcomes, including explicit rejection reasons. The original corpus remains immutable. Reports are local work artifacts. No GPU, network, or external package is required.

## Integration sequence

1. Expand the curated corpus, qualify source rights, analyze collisions and measure false positives.
2. Add bounded recognition across cue boundaries, validated typesetting, cached assets and independently versioned enrichment checkpoints.
3. Add a per-book STEM option, disabled by default, and enrich from retained raw GPU windows without invalidating transcription checkpoints.
4. Negotiate an optional versioned annotation and asset import contract with FitBaus Transcriber. Preserve the existing atomic publication, identity and storage quotas.
5. Display prepared assets in FitBaus Trainer with original narration fallback and no runtime corpus or TeX engine.

This first slice intentionally does not change the existing import protocol, workbench UI or playback behavior.
