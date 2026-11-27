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

## Release boundary

curated.json remains the unchanged legacy prototype dictionary until a later production compiler replaces it. Its 20 migrated entries are all pending in the authoring corpus. Do not edit both copies to add new concepts; new contributions go in the structured authoring corpus. The legacy parity test protects the original seed migration during this transition. No new authoring entry is consulted by the current matcher or normal transcription. No release compiler or automatic approval is implemented here. Raw Wikidata/NMFT exports and generated assets remain outside tracked source. End users will receive a compiled, approved dictionary and pre-rendered assets, not acquisition or review tools.
