# Optional STEM enrichment foundation

This package is independent of the normal transcription workflow. No corpus is downloaded, loaded or consulted by app.py or heavy.py. No LLM, GPU, renderer or external dependency is needed for dictionary inspection.

## Local inspection

    python -m stem
    python -m stem --text "Einstein showed that E equals M C squared."

The curated seed has 20 independently authored entries. Each has a stable ID, category, name, LaTeX and explicit spoken aliases. The compiler rejects conflicting aliases and unapproved sources and emits a deterministic content digest. The matcher only accepts a complete sentence-like expression, optionally following a limited explicit introduction. Matching is deliberately conservative, case-insensitive for spoken aliases and not a general mathematical parser. It does not match cross-cue expressions, infer equations from topics, or repair mathematical errors. Offsets are Python Unicode code-point offsets into unchanged source text. LaTeX screening is lexical and structural, not a proof of mathematical correctness or a full renderer security boundary.

## Structured authoring corpus (S.0F.2A)

The 20 seed concepts now also exist as one file per concept under corpus/mathematics and corpus/physics. Their original IDs, exact TeX and spoken aliases are preserved. Conditions and symbol meanings are initial drafts, with separate pending mathematical and recognition reviews. The existing curated.json remains unchanged and is the only dictionary loaded by the prototype matcher.

    python -m stem.corpus_model

The validator reports deterministic content identity and review counts, checks normalized alias collisions, stable IDs, directory metadata, references and review digests. See corpus/CONTRIBUTING.md and corpus/schema.json. The authoring corpus is not a production release; successful validation does not establish mathematical correctness or renderability. NMFT and Wikidata remain discovery sources only. New authoring entries will not affect recognition until the production compiler and qualification gates are implemented.

## Mathematics expansion (S.0F.2B)

The structured corpus includes 49 additional independently authored mathematics concepts (53 representations) covering algebra, geometry, trigonometry, calculus, linear algebra, probability and statistics. All new entries have explicit conditions, symbol descriptions and edition-specific OpenStax reference locators. References are research leads, not completed independent reviews; new source registry entries remain pending_review. No textbook prose or NMFT templates were copied. New spoken aliases are intentionally empty until recognition qualification. Multiple forms of a concept remain distinct representations (e.g. finite and infinite geometric sums, cosine double-angle forms and the two parts of the fundamental theorem of calculus).

The legacy 20-entry seed and matcher are unchanged. S.0F.2D will independently verify the mathematics, source locators and source admission, including the known pitfalls from the earlier corpora. Rendering and spoken-alias qualification are later steps.

## Physics expansion (S.0F.2C)

Add 33 independently authored physics concepts (34 representations) across mechanics, gravitation, fluid dynamics, thermodynamics, electromagnetism, optics, relativity and quantum mechanics. Each representation states its physical domain, sign conventions, assumptions and symbol meanings where applicable, with a University Physics chapter-equation reference lead. In particular, the thermodynamic first law defines work done by the system as positive; gravitational force is a magnitude; uncertainty uses standard deviations; the Lorentz force has separate full and magnetic-only representations.

The textbook reference sources remain pending_review. The current OpenStax web editions identify their content as noncommercial/share-alike; do not copy or treat textbook prose, illustrations or templates as permissively licensed corpus data. Only independently authored standard mathematical facts and notation are included. All new review records remain pending, and new aliases are intentionally empty. The legacy seed, runtime matcher, renderer and normal transcription workflow are unchanged. Independent mathematics/physics verification, source admission, reference checking, rendering and recognition qualification remain separate gates.

## Algebra mathematical review (S.0F.2D.1)

Review the 13 algebra concepts and their 14 representations by direct derivation and textbook cross-check. The mathematical review records contain original derivations, exact content digests and reference locators. The quadratic formula conditions explicitly cover complex roots and the real-discriminant criterion. Recognition review remains pending for every representation. No renderer or runtime approval is implied.

Reference-only registry entries use a separate _reference ID, admitted solely for bibliographic citation to independently authored mathematical facts. The corresponding original textbook source records remain pending_review for any content reuse. This is not permission to redistribute textbook content. Other subjects retain their existing pending reviews.

## Geometry and trigonometry mathematical review (S.0F.2D.2)

Review 15 concepts and 17 representations, with independently written derivations, textbook cross-checks and content-bound mathematical review records. Preserve every existing formula, representation ID and spoken alias. Clarify the disk and solid-ball domains, orthonormal coordinates and coincident endpoints. Confirm the tangent addition denominator conditions, the positive square root in Heron's formula and the nondegenerate triangle requirement for the laws of sines and cosines. The four migrated geometry concepts gain external reference locators while retaining original provenance.

The cumulative proposed mathematical approvals are 31 of 107 representations. Recognition and rendering remain unqualified. Bibliographic-only reference admission does not grant permission to reuse textbook content.

## Calculus and complex analysis mathematical review (S.0F.2D.3)

Review 17 concepts and 18 representations using direct derivations or explicit reference evaluation, external reference cross-checks and content-bound mathematical review records. Preserve all existing LaTeX, stable IDs and spoken aliases. Taylor series equality now requires analyticity on a connected interval and evaluation strictly inside the convergence radius. Clarify continuity at endpoints for the definite-integral theorem and the common variable and additive constant for integration by parts. The Basel sum uses the exact NIST DLMF zeta definition and value rather than claiming a new derivation; Euler's identity is cross-checked against DLMF 4.14.3. The four migrated seed concepts retain original provenance with added external references.

Cumulative proposed mathematical approvals: 49 of 107 representations. Recognition and rendering remain unqualified. Bibliographic-only reference admission does not grant content reuse rights.

## Linear algebra, probability and statistics mathematical review (S.0F.2D.4)

Review the remaining 13 mathematics concepts and representations. Include direct derivations or definition-based checks, reference cross-checks and content-bound mathematical review records. Verify matrix inverse by multiplication in both orders, binomial and Poisson normalization, the normal density change of variables and the unbiasedness of the corrected sample variance under iid finite-variance sampling. Clarify finite real-valued support, nonnegative integer trial count, positive conditioning probabilities and the distinction between standardization and normality. Preserve all LaTeX, stable IDs and spoken aliases. Use precise OpenStax sections and NIST statistical handbook distribution references; bibliographic admission does not authorize copying textbook content.

All 62 mathematics representations now have proposed mathematical approvals, leaving 45 physics representations pending. Recognition and rendering remain unqualified; the legacy runtime is unchanged.

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

## Named corpus prioritization (S.0D)

    python -m stem.prioritize work/stem-candidates/<snapshot-sha256> --output work/stem-priority/<snapshot-sha256>

This stage reads the verified original snapshot, not the potentially stale conversion export. It classifies every source row by label, then runs the pinned-in-code current converter only on potentially named records. A label containing a multi-letter word is considered potentially named, numeric labels without letters are deferred, unresolved Q/P identifiers and symbolic/uncertain labels are deferred, and property entities are separate. These are review priorities, not semantic judgments. The heuristic may miss useful single-letter or non-word labels or include named numbers.

The new output directory contains named.jsonl (screened candidates with review flags), rejected-named.jsonl (every named conversion failure, with its reason), deferred.jsonl (source row references for all other records), prioritization.json (counts, converter version and ranked rejection reasons) and prioritization.md (human-readable summary). Every source row belongs to exactly one partition. Original formulas remain in the immutable source snapshot; source digest, formula digest and row index retain provenance. Exact LaTeX duplicates are flagged but never silently merged. Name and entity collision flags cover screened named candidates only. No source formula or alias is admitted, and no GPU, model, network or third-party dependency is required. A new output directory is required after converter upgrades.

## Prioritized MathML expansion (S.0E.1)

Converter mathml-subset-v2 adds explicit ASCII identifier style mappings (including upright, bold, blackboard bold and script where supported), additional Greek symbols, operators and named functions. Unknown styles and metadata remain rejected. The lexical allowlist has been extended only for explicit commands emitted by the converter; this is still not a renderer security boundary. Complex tables, under/over notation, arbitrary text and spacing remain deferred. Existing candidates must be regenerated after converter changes.

    python -m stem.prioritize work/stem-candidates/<snapshot-sha256> --output work/stem-priority/wikidata-v2
    python -m stem.diagnose work/stem-candidates/<snapshot-sha256> --output work/stem-priority/wikidata-v2/diagnostics.json

Diagnostics inventories bounded attribute and token value frequencies across parsed, rejected named MathML records. Counts describe all encountered values in those rows, not exclusively the offending value. The first-rejection summary remains distinct. The report is deterministic, offline, and review-only. A new output path is required.

## Structural MathML expansion (S.0E.2)

Converter mathml-subset-v3 supports common explicit delimiters, set symbols, MathJax atom classes, ASCII operator names, bounded plain mathematical text, selected spacing widths, simple indexed roots, known limit operators and selected accents. Explicit function application is accepted only between an identifier and an opening parenthesis. Operator spacing overrides are approximated by default TeX spacing for the observed allowlisted values; mathematical typography is not pixel-equivalent. Unsupported tables, styled Unicode and other unknown constructs remain rejected. Source rows containing Unicode replacement characters are rejected before conversion, including XML character references, and diagnostics report their row count separately. Never infer the missing characters. The original snapshot is unchanged and all candidates remain review-only.

    python -m stem.prioritize work/stem-candidates/<snapshot-sha256> --output work/stem-priority/wikidata-v3
    python -m stem.diagnose work/stem-candidates/<snapshot-sha256> --output work/stem-priority/wikidata-v3/diagnostics.json

## Original Wikidata TeX recovery (S.0E.3)

    python -m stem.recover work/stem-candidates/<snapshot-sha256> --output work/stem-original-tex/wikidata --max-batches 2
    python -m stem.recover work/stem-candidates/<snapshot-sha256> --output work/stem-original-tex/wikidata

Unlike the SPARQL MathML export, the Wikidata entity API exposes original P2534 mathematical string values. This explicit online stage uses the verified snapshot only to select distinct potentially named entity IDs. It retrieves current claims and entity revision IDs, not historical claims from the acquisition date. It does not assert a one-to-one match between original snapshot rows and current statements. Deprecated and non-value statements are counted but excluded from candidate exports; preferred and normal statements remain separate. Source labels are from the original snapshot.

Requests are sequential, in fixed batches of up to 25 IDs with a one-second minimum delay before each request, a bounded response size, maxlag and bounded retry handling for HTTP 429/503 and API maxlag. Completed raw JSON responses are retained with their request IDs and SHA-256 in atomic batch checkpoints. Rerun the same command and output directory to resume; --max-batches limits newly fetched batches, not cached ones. Use one process per output directory. A mismatched plan or damaged checkpoint fails closed. Partial reports explicitly mark complete=false; a stopped run may leave the previous report in place until resumed.

The output includes plan.json, batches/, original-tex.jsonl and recovery.json. Each candidate records the statement ID, entity revision, rank, exact formula, source snapshot digest and response digest. Original TeX is retained even when it fails the current lexical screen; empty, oversized or replacement-character values are deferred and remain in raw checkpoints. Nothing is admitted or rendered. The original snapshot and MathML exports remain unchanged. Do not commit the downloaded corpus. No GPU or additional package is required.

## Maintainer renderer qualification (S.0F.1)

Research: MathJax 4.1.3 and its matching New Computer Modern font are selected for offline SVG typesetting; resvg-js 2.6.2 rasterizes sanitized SVG into transparent PNG. See https://docs.mathjax.org/en/v4.0/server/components.html, https://docs.mathjax.org/en/latest/web/convert.html, https://docs.mathjax.org/en/latest/options/input/tex.html and https://github.com/thx/resvg-js. MathJax's optional Speech Rule Engine is a possible future deterministic alias seed, not enabled here.

The renderer is a maintainer tool, not an application installation prerequisite. Direct npm versions are exact; the initial dependency lockfile must be reviewed and committed before release qualification. The Windows smoke workflow uploads its generated lockfile for review. Until then, dependency resolution is not fully reproducible.

    npm --prefix stem/renderer install --ignore-scripts --no-audit --no-fund
    python -m stem.renderer_smoke
    python -m stem.qualify_render work/stem-original-tex/wikidata --output work/stem-render/pilot --limit 100
    python -m stem.qualify_render work/stem-original-tex/wikidata --output work/stem-render/wikidata

The input is a completed recovery directory. The tool checks formula digests and statement counts, deduplicates exact TeX, uses a conservative explicit command and environment allowlist, loads only selected MathJax packages with no dynamic TeX extension requests, and rejects unknown glyph text, unsafe SVG tags and attributes, and styling-dependent constructs. SVG paths are normalized to white on transparent background for the dark bike UI. Separate bounded subprocess batches render SVG then PNG; timed-out batches split to isolate single formulas. Node heap limits are not a full OS sandbox. Use a restricted, network-isolated maintainer environment for final qualification; installation itself requires npm access. Rendering success does not establish mathematical fidelity. The worker and SVG policy require live qualification before being considered safe for any public input.

The report includes formula and dependency-lock digests, outcomes and completeness, results.jsonl links candidates to source statements, assets/ is content-addressed, and gallery.html shows a deterministic sample of up to 100 successful PNG renders. Use a new output directory for each run. Nothing is admitted to the dictionary. Only approved, versioned dictionary records and assets should be distributed, with license notices; end users must not acquire or render the corpus. No runtime or APK changes.

## Integration sequence

1. Expand the curated corpus, qualify source rights, analyze collisions and measure false positives.
2. Add bounded recognition across cue boundaries, validated typesetting, cached assets and independently versioned enrichment checkpoints.
3. Add a per-book STEM option, disabled by default, and enrich from retained raw GPU windows without invalidating transcription checkpoints.
4. Negotiate an optional versioned annotation and asset import contract with FitBaus Transcriber. Preserve the existing atomic publication, identity and storage quotas.
5. Display prepared assets in FitBaus Trainer with original narration fallback and no runtime corpus or TeX engine.

This first slice intentionally does not change the existing import protocol, workbench UI or playback behavior.
