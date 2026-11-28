# Contributing to the FitBaus STEM corpus

The authoring corpus is a mathematical knowledge base, not the runtime dictionary. One JSON file per concept, under `<discipline>/<subject>/<concept-id suffix>.json`. Use the existing disciplines (mathematics, physics, chemistry, biology, computer_science, engineering); add subject directories as needed. Preserve stable concept IDs across moves and use short stable representation IDs. IDs are not derived from file contents. The full representation identity is concept ID plus colon plus representation ID. Never recycle an ID for different mathematics.

Use schema.json as the structural schema and run `python -m stem.corpus_model` from the repository root. The standard-library validator additionally enforces path, source, review and alias rules. It does not execute LaTeX and is not a renderer security boundary. CI runs the validator and the corpus regression tests.

## Authoring

- Use a familiar, useful concept with one or more exact mathematical representations. Do not substitute one representation for a different equation merely because they share a name.
- Provide conditions and symbol meanings for each representation. Include domains, units or conventions where applicable. Keep descriptions independently authored unless the source permits adaptation.
- Use alternate_names and tags for discovery only. Names are not recognition triggers. Spoken aliases must be recitations of the exact representation; generic mentions, invented equations and ambiguous aliases must not match. Pending representations may have no spoken aliases. Existing normalization is conservative and ASCII-only.
- Reference precise sources (edition, chapter, equation number, URL or other stable locator). Register sources in sources.json. Imported or adapted data requires pinned provenance, redistribution rights and attribution before admission. A candidate source is not an approved source. The migrated seed references its original file solely for provenance, not independent verification.

Reference-only sources may be separately registered with an admitted _reference ID for bibliographic citations to independently authored facts. Record the scope and source locator explicitly; never use such admission as permission to import or adapt copyrighted content. Leave the corresponding content source pending until redistribution rights are established.

## Review

Every representation has separate mathematical_review and recognition_review records. New entries start pending with null digest, empty method and evidence lists. Approved or rejected records require the matching content digest, nonempty methods and concrete evidence (e.g. reference and section, derivation or test identifier). A mathematical approval requires admitted references; recognition approval additionally requires mathematical approval and at least one alias. A status field is an assertion to review, not a proof or an authorization mechanism.

Use mathematical_digest(concept, representation) and recognition_digest(concept, representation) in stem.corpus_model to compute the review bindings. Mathematical identity, title, discipline, subject, exact TeX, assumptions, symbols and references are bound. Recognition additionally binds normalized aliases. Changing a bound field invalidates the corresponding review; reset affected reviews to pending and re-review. Changing display-only alternate names or tags does not invalidate review. Do not mark approved merely because a hash matches. Rendering fidelity and recognition against real transcription/negative examples are separately required before release.

## Generated spoken-alias proposals

S.1B generates maintainer-only proposals into ignored work directories, with a pinned plan and resumable response records. Do not copy raw model output into spoken_aliases or approve recognition based on lexical screening, model confidence or collision absence. Even apparently correct proposals require independent exact-representation review and positive/negative recognition tests. Keep original source formulas unchanged. A changed alias set invalidates recognition approval and must be re-reviewed. See stem/README.md for the generator commands.

## Direct recitation authoring and scope review (preferred)

For the small verified corpus, directly author and vet a few high-quality spoken recitations per representation instead of requiring local model generation. Read the exact equation, symbol definitions and conditions, and reconstruct the expression from each proposed phrase. Explicitly delimit powers, fractions, subscripts, factors, summation bounds and vector notation. Prefer clear natural mathematical wording to eight near-duplicates. Do not silently change signs, operands or algebraic form.

Record exact mathematical digests, reviewed phrases, a scope rationale and counterexamples in tracked review fixtures. Test them against the actual matcher in an isolated test-only dictionary. These tests prove string recognition and rejection for the supplied phrases, not real speech accuracy or independent semantic verification. A direct authoring pass is not a blind second-model review. Keep recognition_review pending until S.1C has sufficient recognition evidence. No automatic admission, GPU, API key or local model is required for direct authoring. The existing Ollama experiment remains optional.

## Recognition qualification evidence

Use python -m stem.qualify_recognition --summary to evaluate the complete scope-reviewed corpus with the actual matcher. Preserve the distinction between authored regression cases, conservative context challenges and independently labeled transcription observations. Exact-span scores on authored aliases are not ASR accuracy or independent mathematical review. Never approve recognition simply because synthetic tests pass. Keep private narration local, and record the dataset identity, matcher version, recognition digests and explicit admission criteria before marking any representation approved.

## Release boundary

curated.json remains the unchanged legacy prototype dictionary until a later production compiler replaces it. Its 20 migrated entries are tracked separately in the authoring corpus; mathematical and recognition review statuses may differ. Do not edit both copies to add new concepts; new contributions go in the structured authoring corpus. The legacy parity test protects seed concept identity, name and exact formula. Structured aliases may diverge deliberately after scope review; the legacy prototype remains untouched. No new authoring entry is consulted by the current matcher or normal transcription. S.1A provides a deterministic candidate compiler (python -m stem.compiler --summary). It never automatically approves entries, and its output is not a release artifact or runtime input. Raw Wikidata/NMFT exports and generated assets remain outside tracked source. End users will receive a compiled, approved dictionary and pre-rendered assets, not acquisition or review tools.
