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

## Classical physics mathematical review (S.0F.2D.5)

Review 23 representations in mechanics, gravitation, fluid dynamics and thermodynamics. Distinguish empirical model laws and definitions from mathematical derivations. Cross-check the classical physics equations against University Physics Volumes 1 and 2 and the one-dimensional conduction equation against MIT 18.303, The 1-D Heat Equation, section 1.1. Record the derivations and content-bound review digests, with bibliography-only source admission.

Clarify nonrelativistic and constant-mass assumptions, positive mass and separation, constant-density streamline flow, phase speed versus group speed, spring extension conventions, conduction-only heat transfer, thermodynamic work sign, process heat capacity and the first-order thermal expansion approximation. Preserve formula strings, IDs and spoken aliases. No textbook prose or figures imported.

Cumulative proposed mathematical approvals: 85 of 107 representations; 22 remain in electromagnetism, optics, relativity and quantum mechanics. Recognition and rendering remain unqualified; the runtime matcher and legacy seed remain unchanged.

## Electromagnetism, optics and modern physics mathematical review (S.0F.2D.6)

Review the remaining 21 concepts and 22 representations: nine electromagnetic concepts (ten forms), three optics, five relativity and four quantum mechanics. Distinguish empirical laws and constitutive models from mathematical derivations, and add independently authored review evidence tied to exact content digests. Correct the full Lorentz-force reference to University Physics Volume 2 section 16.1 and retain the magnetic-only form's separate chapter reference. Check the uncertainty principle against Volume 3 chapter 7, and clarify canonical operator domains and intrinsic state standard deviations. Specify rest versus total energy, simultaneous endpoint measurements, photon frequency/frame, ideal photoemission threshold, paraxial and far-field approximations, and electrical sign conventions.

Cumulative proposed mathematical approvals: 107 of 107 representations across 102 concepts. No new formulas, aliases, or runtime changes. Bibliographic-only source admission does not authorize copying reference content; the content source records remain pending. Approval is an authoring-level review record, not independent human certification, rendering qualification, recognition qualification or production release approval. S.1A is next: a deterministic compiler with explicit admission gates and stable representation identities.

## Deterministic dictionary compiler (S.1A)

    python -m stem.compiler --summary
    python -m stem.compiler

The compiler validates the complete structured authoring corpus and its source registry first. It emits a new versioned candidate artifact to standard output (canonical ASCII JSON plus a final newline), or a concise summary with --summary. Explicitly redirect standard output to a local work file if an artifact is needed; the compiler never writes files itself. No network, model, GPU, npm installation or renderer execution is required.

Only representations with current approved mathematical and recognition reviews, admitted references and nonempty explicit spoken aliases can enter the candidate dictionary. Invalid review digests, source admission, global alias collisions or malformed corpus data fail the entire build. Approved entries must also pass the existing renderer TeX preflight; failure is a build error, not a silent omission. That lexical preflight is not rendering qualification or a sandbox. Each candidate retains its stable concept:representation ID, exact TeX, normalized sorted aliases and both review digests. Names, tags and alternate names do not create recognition triggers. Exclusions include precise reasons, which may overlap. The artifact binds the complete validated authoring corpus, source registry metadata, compiler version and matcher version; artifact_sha256 hashes the canonical payload without the artifact_sha256 field or final newline.

All 107 current representations have mathematical review records but recognition is still pending, so the initial candidate dictionary is intentionally empty. An empty candidate build is valid, not a release. release_qualified is always false: rendering evidence, recognition qualification and distribution gates must still be implemented. The old curated.json prototype, matcher and normal transcription path are unchanged. No compiled-candidate artifact is consumed by the runtime. The shared CI unit suite tests the compiler with isolated fixtures and the actual repository corpus, without generating persistent reports.

## Maintainer spoken-alias generation (S.1B)

Run Ollama locally on the maintainer workstation with a locally installed model. Disable Ollama cloud features in the server configuration (OLLAMA_NO_CLOUD=1) for an offline run. The tool talks only to 127.0.0.1:11434 and never downloads a model, sends book text, calls a remote API directly or installs a dependency. Select the exact installed name using ollama list. Use ollama ps separately to verify GPU placement; the generator does not force or certify GPU residency. A model suitable for precise mathematical recitations is preferred.

    ollama list
    python -m stem.generate_aliases --model qwen2.5-coder:32b --output work/stem-aliases/pilot --max-new 5
    python -m stem.generate_aliases --model qwen2.5-coder:32b --output work/stem-aliases/pilot

The model name above is an example; use an actual locally installed model. The second command resumes the same plan, completing remaining representations. Default is up to eight proposed aliases per representation; --count accepts 1 through 16 and is part of the plan. Use a new output directory when model, prompt, corpus, source registry or count changes. The native Ollama chat and model-list APIs provide structured JSON and model metadata: https://docs.ollama.com/api/chat and https://docs.ollama.com/api/tags.

The tool creates plan.json, one bounded atomic checkpoint per completed representation under responses/, and candidates.json (the current candidate report). Keep one process per output directory. The immutable plan binds the reviewed mathematical content, source registry, existing aliases, prompt/options, model digest and reported Ollama version. Resume validates checkpoints and checks model identity before and after generation; identity is server-reported, not proof of inference or determinism. A malformed or truncated response stops the run without committing that response. Earlier checkpoints survive. After a failed run, the report may reflect an earlier successful invocation; rerun to refresh it. An incomplete report must not be used for final collision adjudication.

Only mathematically approved representations with pending recognition review are selected. The report classifies normalized aliases, already-existing phrases, duplicates, generic names, missing explicit relation words, invalid aliases and cross-representation collisions (including collisions with existing authored aliases). All accepted-looking proposals remain candidate_only. Exact collision checks are not semantic verification; a candidate can still be mathematically wrong or match ordinary prose. A later recognition qualification phase must independently review recitation fidelity and measure false positives and transcription coverage before any alias is admitted. No source file, review status, legacy dictionary, normal transcript or runtime is changed. CI exercises the workflow with mock responses only, without running Ollama.

## Direct spoken-recitation vetting (S.1B.1)

The preferred workflow is direct maintainer-assisted recitation authoring and semantic scope review of the verified corpus, not mandatory GPU generation. The five-representation Ollama pilot demonstrated that lexical acceptance does not establish correct grouping. Preserve that experimental baseline; no further inference is necessary for the curated corpus.

The first batch revises arithmetic sequence, arithmetic series, binomial theorem, difference of squares and Euler's identity. It provides 14 deliberately scoped phrases, with exact equations, mathematical review digest bindings, scope reasoning and negative examples in tests/fixtures/stem_recitation_pilot.json. The two ambiguous inherited Euler phrases are replaced only in the structured corpus. The legacy prototype remains unchanged. CI runs the actual matcher against positive and negative fixtures using a test-only dictionary and checks that unqualified rows remain excluded by the candidate compiler.

Authoring rubric: say explicit subscripts; preserve the base and end of compound exponents; identify numerator and denominator scope; group sums and products; state both summation bounds, signs and variable names. Prefer distinct correct recitations over filling a quota. For every phrase, reconstruct the expression and consider an alternative parse. A mathematically plausible alternative is grounds to exclude or rewrite it. A later independent or blind review may catch correlated authoring errors, but this batch does not claim independent inference or formal recognition qualification.

Recognition reviews remain pending; S.1C still requires actual transcription coverage, broader negative cases and release gates. No GPU, Ollama, additional API account or model download is needed for the direct authoring path. The optional existing generator is retained unchanged for reproducing the pilot.

## Algebra recitation review (S.1B.2)

Complete direct scope review for the remaining nine algebra concepts (ten representations), including both geometric series forms, logarithm identities, the quadratic formula and squares of sums and differences. The structured quadratic alias is replaced because its radical and denominator boundaries were implicit; the legacy prototype remains unchanged. Explicitly distinguish logarithm bases from arguments, the finite and infinite summation bounds, exponent grouping and the signs of the middle polynomial terms.

The tracked tests/fixtures/stem_recitation_algebra.json holds 21 reviewed recitations and 31 counterexamples. The fixture-driven matcher tests discover all stem_recitation_*.json fixtures, check unique representation coverage, exact formula and mathematical digest bindings, and exercise positive spans and negative rejection across the combined test dictionary. Cumulative scope-reviewed coverage: 15 of 107 representations, with all 14 algebra representations plus Euler's identity reviewed. Recognition approval is still pending. No runtime or inference changes.

## Geometry and trigonometry recitation review (S.1B.3)

Complete direct scope review of seven geometry and ten trigonometry representations. Keep the existing formulas and mathematical review values unchanged. Make coordinate and radical grouping explicit, distinguish ordered pairs from scalar sums, separate trigonometric function powers from powers of arguments, and preserve each of the three cosine double-angle representations. Use explicit side and angle roles where spoken letter case cannot distinguish the two. The reciprocal law of sines is a valid related identity but is not an alias of the stored form. Defer ambiguous and homophonic circle-area variants to later ASR qualification; the legacy prototype remains unchanged.

The geometry and trigonometry review fixtures add 37 scope-reviewed recitations and 50 negative examples. Cumulative review covers 32 of 107 representations, 72 recitations and 100 negative examples. The existing fixture discovery and matcher tests apply without changes. These are direct scope reviews, not speech-transcription or independent blind-review evidence. Recognition remains pending; no runtime, inference or publication change.

## Calculus recitation review (S.1B.4)

Directly scope-review 17 calculus representations in 16 concepts. Preserve the original LaTeX and mathematical review digests. Explicitly distinguish the derivative of a composition from derivatives evaluated at the wrong point, the two fundamental theorem forms, lowercase integrand f from uppercase antiderivative F, limit targets, differential variables, subtraction order and numerator scope. In the Taylor series the parenthesized superscript denotes derivative order, not exponentiation; in sine and cosine series the alternating factor has base negative one and each factorial covers its entire index expression. The exact source conditions remain unchanged.

The calculus fixture adds 34 reviewed recitations and 51 counterexamples. Cumulative scope review covers 49 of 107 representations, 106 aliases and 151 negative examples. Existing fixture discovery tests check positive recognition and negative rejection. No recognition approvals, runtime changes or external inference are introduced.

## Linear algebra, probability and statistics recitation review (S.1B.5)

Complete direct scope review of the remaining 13 mathematics representations. Distinguish matrices from their entries, preserve row order and signs in the two-by-two inverse, distinguish conditional from joint probabilities and combinations from ordered selections, and explicitly identify random variables, support indices, factorial arguments, weighted squared deviations, sample versus population quantities and both grouped factors of the normal density. The original mathematical definitions, conditions, LaTeX and mathematical approval digests remain unchanged.

The linear algebra, probability and statistics fixtures add 26 recitations and 39 counterexamples. All 62 mathematics representations now have direct recitation scope reviews, comprising 132 aliases and 190 negative examples. The existing fixture-driven matcher tests discover these additions. Recognition approval remains pending; this is not independent blind review or measured ASR performance. No runtime or inference changes.

## Classical physics recitation review (S.1B.6)

Directly review all 23 representations in mechanics, Newtonian gravity, fluid dynamics and thermodynamics. Preserve the exact formula strings, stable identities, conditions and mathematical review digests. Distinguish signed scalar components from vectors, phase speed from group speed, net force and net work from individual forces, gravitational constant G from acceleration g, force magnitude from potential energy, and heat entering the system from work done by the system. Preserve radical and denominator boundaries, initial-state indices, temperature differences and partial derivative orders. Literal spoken symbols remain supported where unambiguous within the stored representation. Withhold several underspecified inherited physical descriptions from the structured corpus; the legacy prototype remains unchanged.

Four subject fixtures add 51 scope-reviewed recitations and 71 negative examples. Cumulative review covers 85 of 107 representations, 183 aliases and 261 negative examples. Existing fixture-driven tests exercise the exact matcher against these cases. Recognition approval remains pending; this is not independent blind review or measured speech-transcription qualification. No runtime, publication or inference changes.

## Electromagnetism, optics, relativity and quantum mechanics recitation review (S.1B.7)

Directly review the remaining 22 representations. Preserve vector directions and ordered cross products, the absolute value and vacuum permittivity in Coulomb's force magnitude, closed-surface electric flux, the sign of Faraday's derivative, optical indices and reciprocal distances, the rest-versus-total energy distinction, proper-time and coordinate-time intervals, Planck versus reduced Planck constant, and the inequality between position and canonical momentum standard deviations. Keep the full and magnetic-only Lorentz force representations distinct. Withhold underspecified inherited aliases in the structured corpus; preserve the legacy prototype and all exact mathematical content.

Four subject fixtures add 48 scope-reviewed recitations and 68 negative examples. All 107 representations now have direct recitation scope reviews, comprising 231 aliases and 329 negative examples. Exact normalized alias uniqueness and positive/negative collisions were checked across all 16 fixtures. Recognition approval remains pending; these recitations and counterexamples are not independent blind-review evidence or real ASR measurements. S.1C must qualify the recognition behavior and build the admission evidence before release. No runtime, publication or inference changes.

## Recognition qualification baseline (S.1C.1)

    python -m stem.qualify_recognition --summary
    python -m stem.qualify_recognition

The maintainer-only harness loads all structured concepts and scope-review fixtures, requires exact formula, mathematical digest and alias parity for every representation, and constructs an isolated qualification dictionary. It does not load the legacy prototype or bypass the production compiler. The actual sentence matcher is evaluated with all authored positive aliases and negative examples, capitalization and whitespace variants, Unicode prefix/source-span checks, prefix and suffix mutations, and adjacent pairs of representations. Metrics count exact representation ID, code-point start/end and LaTeX matches; an incorrect ID or span counts as both a false positive and false negative. Undefined precision/recall is null. Report identity binds corpus, registry, fixtures, per-representation recognition digests, matcher version and implementation source hashes.

Separately evaluate conservative abstention challenges: negated and hypothetical introductions and arbitrary colon prefixes. The current sentence-v1 matcher may accept these because it is a lexical matcher, not a semantic context classifier. Challenge failures are explicit blockers, not silently counted as successes or used to inflate the authored regression metrics. These challenges test a proposed conservative context policy, not a claim that every quoted equation should be suppressed. S.1C.2 must resolve and qualify the context policy before admission. In the original S.1C.1 baseline, CLI exit zero meant the synthetic regression suite passed, and challenge failures did not break baseline CI. S.1C.2 supersedes that behavior: both suites must pass. The full report contains case IDs and counts, not narration text. --summary omits detailed failure rows and corpus bindings. No report file is created automatically.

Optional local transcription observations:

    python -m stem.qualify_recognition --observed work/stem-observations.json --summary

The observation JSON schema is fitbaus.stem.recognition-observations/v1 with provenance containing source, transcriber and labeling_method strings, and cases containing unique id, original text and expected annotations (id, start, end). Annotations use stable concept:representation IDs and nonoverlapping Python Unicode code-point offsets into the original text. Use an empty expected array for non-equation examples. Include independently labeled narration and difficult negatives, not just dictionary phrases; a correct equation that is missed should still be annotated. Preserve actual ASR spelling and punctuation. Do not commit private or copyrighted audiobook text. Example schema shape (synthetic, not observed ASR evidence):

    {
      "schema": "fitbaus.stem.recognition-observations/v1",
      "provenance": {
        "source": "local test",
        "transcriber": "manual example only",
        "labeling_method": "manual span annotation"
      },
      "cases": [
        {"id": "example-1", "text": "E equals M C squared.",
         "expected": [{"id": "physics.mass_energy:standard", "start": 0, "end": 20}]},
        {"id": "example-2", "text": "The chapter discusses energy.", "expected": []}
      ]
    }

The optional observation dataset is operator-declared, not independently authenticated, and its scores are separate from synthetic tests. No measured ASR accuracy is claimed until real observations are collected and independently reviewed. There is no automatic approval or threshold tuning in this baseline. Recognition and release qualification remain false. CI runs the deterministic baseline through unit tests without additional files, network, GPU or model calls. No corpus review status, compiler admission rules, legacy matcher or normal transcription behavior is changed.

## Context and sentence-boundary hardening (S.1C.2)

The sentence-v2 matcher deliberately favors precision over recall. It accepts a complete reviewed spoken alias by itself, or following an anchored formula/equation introduction (including a literal formula/equation colon or "is given by"). The two narrow historical attribution prefixes used by the legacy examples remain supported. Arbitrary trailing introduction searches and arbitrary colon prefixes are removed. Negation or hypothetical wording ahead of an introduction no longer permits a suffix match. This is an explicit lexical policy, not verification of a narrator's intent or a general language parser.

A period or exclamation mark followed by whitespace/end can terminate a candidate; a final unpunctuated fragment can also be considered. Questions, mixed punctuation, ellipses, embedded punctuation, semicolons and internal line breaks are not treated as safe equation boundaries. Obvious arithmetic continuation at the beginning of the next fragment or an unfinished operator at the end of the preceding fragment causes abstention. Separate complete sentences remain eligible, with exact original Unicode code-point offsets. No cross-cue recognition or normalization of punctuation into mathematical operators is attempted. A complete alias presented without its surrounding context can still be misleading; this bounded lexical policy cannot resolve every semantic qualifier or ASR punctuation error.

The qualification harness (version 2) adds anchored-colon and "is given by" positives for every alias and expands context abstention challenges to 14 per representation. Both the mandatory synthetic regression suite and the separate context challenge suite must pass for the CLI to exit zero. CI asserts both suites pass, including original legacy examples, original source spans, sentence isolation and CLI failure behavior. Synthetic success does not grant recognition approval; real transcription observations and admission criteria remain pending. No corpus aliases, review statuses, renderer, publication or normal transcription pipeline are changed. The legacy inspection CLI intentionally uses the hardened shared matcher.

## Existing checkpoint sampling (S.1C.3A)

Run from the Heavy Transcriber checkout after core CI or setup has provisioned the pinned upstream contract. Stop any active transcription batch before sampling so the checkpoint snapshot is stable. No audio download, model initialization, GPU, network connection or VEGA credentials are needed.

    python -m stem.sample_checkpoints --inventory
    python -m stem.sample_checkpoints --name development.json --uniform 100 --targeted 100

The inventory scans the existing work directory's audio cache keys and known heavy profile hashes; use --work-dir for a custom checkpoint root. It reports hashed audio identity keys, inferred profile names, window/cue counts and covered milliseconds, not book titles or narration. It validates each checkpoint against the pinned TranscriptWindow contract, cache-key identity, aligned filename, coverage and bounded size. It supports interrupted runs with gaps; covered duration is not proof of a complete book or current library revision. Publication acknowledgements, unrelated work directories and unknown profile hashes are not used. Profile identity is inferred from the directory name, not independently attested. Use repeatable --book CACHE_KEY and optional --profile-key PROFILE_KEY to restrict the population. A malformed compatible checkpoint stops the scan.

Each sampled case preserves an entire original ASR cue, its timestamps, cue index, checkpoint digest, stable opaque ID and cache/profile keys. No text normalization or matching is used to select it. The uniform stratum uses a deterministic seed-based hash ranking across all eligible cues, not a formula filter. The second stratum uses broad mathematical word/symbol hints (including symbolic notation), excludes already sampled cues and is explicitly enriched, not representative of prevalence. Requests are caps, not guaranteed counts; the summary reports the actual sample sizes. Neither stratum has automatically assigned labels: expected is null, not an empty negative annotation. All output is candidate evidence only.

Window-level partitions are fixed by seed and audio cache key plus window start, independent of profile. Approximately one quarter of windows are reserved for holdout. Keep the default seed 42 and book/profile selection fixed between runs. Sample development first; do not inspect or tune against holdout until the alias/matcher policy is frozen:

    python -m stem.sample_checkpoints --partition holdout --name holdout.json --uniform 100 --targeted 100

Partitions are disjoint by window, not independent by audiobook; nearby content or multiple revisions can still correlate. The snapshot digest binds the scanned windows and their hashes. Changing inputs or seed changes the evidence population; compare snapshot identities before using results together. Avoid combining multiple profiles of the same audio for prevalence metrics. Separate strata in evaluation, and do not interpret formula-enriched precision/recall as library-wide rates.

Packs are written only to the ignored work/stem-qualification directory, using a new simple JSON filename; existing output is never overwritten. The terminal prints metadata and counts, not cue text. The pack contains private audiobook text: do not commit it, publish it, or share material you are not permitted to share. An interrupted write can leave an incomplete file; use a new filename and validate the pack digest. The sampler never modifies checkpoints. A subsequent review phase must label the cue text, check source and annotation fidelity, and convert completed annotations to the observation schema. No production dictionary admission or ASR accuracy claim is made here.

## Source-mapped mathematical tokenization (S.1D.1)

The development observations exposed the limits of whole-sentence aliases: all 4,110 synthetic cases passed, but the three labeled target mentions in the sampled audiobook were missed. The data covers only one audiobook and one exact target representation, not broad ASR accuracy. Holdout remains untouched.

The standalone stem.tokenizer module introduces a bounded, lossless lexical representation. tokenize(text) returns immutable typed tokens with a canonical lexical value, spoken/symbolic/raw form, original source substring and Python Unicode code-point start/end offsets. Concatenating all source substrings reconstructs the exact input, including whitespace, punctuation and unknown characters. Longest explicit spoken phrases take precedence over individual words and never cross line breaks. Digits and individual spoken number words share lexical values; superscript digits and squared/cubed share exponent tokens. Greek symbols retain case, named Greek letters are lexical candidates, and multi-letter words such as mc remain intact. Decimal spelling, variable case and unsupported Unicode are not silently normalized.

Tokenization is not recognition. Ordinary words such as a, I, one, over, equal and to the can have nonmathematical meanings. The latter is a POWER_HINT, not an asserted exponent boundary. No multiplication, number composition, variable renaming, homophone correction, exponent grouping, punctuation removal or equation inference is performed. Unknown words and symbols remain in the stream; they must not be skipped to create a match. Uppercase/lowercase spoken modifiers are separate tokens and not applied until structural interpretation. A parser must account for the complete selected span and abstain when meaning or scope is uncertain. Input is bounded to 32,768 code points and 8,192 tokens, rejecting NUL and surrogate code points. No external dependency, renderer, GPU or language model is needed.

Next: S.1D.2 typed expression AST and structural validation; S.1D.3 restricted spoken parser; S.1D.4 dictionary integration and controlled substitution; S.1D.5 bounded cross-cue assembly; S.1D.6 development and untouched holdout qualification. Existing matcher, compiler, corpus approvals, observation format and normal transcription pipeline remain unchanged. The tokenizer alone does not improve recognition scores or admit representations.

## Typed mathematical expression tree (S.1D.2)

The standalone stem.expression module defines immutable, source-spanned nodes for numbers, case-preserving symbols, unary and binary operations, powers, simple subscripts, single-argument allowlisted functions, explicit grouping, factorials and root-level relation chains. Fraction structure is represented as division; grouping and power nesting are explicit. Every node carries a half-open Python Unicode code-point span. The tree is a structural representation, not a solver or proof of mathematical validity.

validate(tree, source) enforces the exact node/operator/function types, bounded numeric literals and symbol vocabulary, source bounds, ordered nonoverlapping child spans, containment, prefix/postfix/group boundaries, root-only relations, valid relation arity and limits of 256 nodes and 32 levels. Shared nodes and cycles are rejected. Explicit operator gaps are required for relations and nonmultiplicative binary operations; adjacent children are permitted for multiplication and postfix notation. The validator does not prove token coverage, operator spelling, grouping correctness, semantic types, domain conditions or mathematical truth. Those checks belong to the parser and recognition policy; never use a constructed AST alone as evidence that an equation occurred in narration.

structural_key(tree, source) validates before creating a deterministic, span-independent nested tuple. Redundant grouping wrappers are omitted from that key, but the operand tree, order, signs, case, exact numeric spelling and relation operators remain distinct. No simplification, commutation, algebraic equivalence, variable substitution, numeric evaluation, arbitrary TeX or execution is performed. The AST permits explicit structures for future parsing, including factorials, without claiming the tokenizer currently recognizes every such form. Calculus binders, matrices, vectors, general indexed expressions and other advanced constructs remain dictionary-only or deferred.

Twelve focused tests cover Euler's explicit exponent structure, case and grouping identity, Unicode and spoken postfix spans, relation chains, fractions and function structure, adjacency, invalid types and spans, immutability and complexity limits. S.1D.3 must derive these trees from source-mapped tokens, enforce full token consumption and reject ambiguous scope; the current exact matcher, corpus, compiler, renderer and normal transcription flow are unchanged. No recognition approval or real-world accuracy improvement is claimed. Holdout remains untouched.

## Restricted mathematical parser (S.1D.3)

The standalone stem.parser.parse_expression(source) accepts an already selected mathematical expression span and returns a validated source-spanned AST, or raises ParseError (a ValueError subclass). It is not a narration recognizer and must not be called on arbitrary extracted fragments as proof of a match. All significant tokens must be consumed, and only spaces/tabs may be skipped. The AST root spans the first through last significant token. No introductory prose, trailing sentence punctuation, unknown words, repair or cross-cue assembly is performed. A terminal adjacent exclamation mark within an explicitly selected expression is factorial notation, not evidence that narration actually used a factorial.

The grammar supports relation chains, additive and multiplicative operations, unary signs, right-associative symbolic powers, spoken squared/cubed, explicitly grouped spoken exponents and selected ordinal power phrases, simple subscripts, factorials, case modifiers, explicit groups and allowlisted single-argument functions. Symbolic precedence is conventional. Implicit multiplication is restricted to an adjacent numeric literal followed by a symbolic variable or opening parenthesis, such as 3x or 2(x+1); multi-letter words and whitespace-separated products are not split or inferred. Spoken fractions mixed with other infix operations in the same scope require explicit grouping, as do compound spoken denominators. Bare spoken power/function arguments must end at a scope/relation boundary; ambiguous signs on ungrouped powers or factorials are rejected. Examples:

    x squared plus y squared equals z squared
    e raised to the power of open parenthesis i times pi close parenthesis plus one equals zero
    cosine of open parenthesis pi over 2 close parenthesis equals 0

The unscoped audiobook wording e to the i pi plus 1 equals 0, ambiguous fraction a plus b over c and cosine of pi over 2 equals 0 remain rejected. Resolving a known identity from contextual evidence is a separate dictionary integration policy, not a guess made by this parser. No mathematical truth, domain, dimensional, vector or semantic validation is implied. Input is bounded to 4,096 code points, 256 significant tokens and 24 nested parser operations, with the AST's stricter node/depth limits also applied. No arbitrary TeX, rendering, symbolic evaluation, external dependency or inference is used.

Twelve focused tests cover precedence, explicit scope, ambiguous recitations, preserved notation, full consumption, exact source spans and complexity. Existing tokenizer, AST, exact matcher, compiler, corpus approvals and transcription runtime are unchanged. S.1D.4 must connect validated structures to verified identities and specify controlled substitutions and contextual abstention. Development recognition remains unmeasured for this standalone parser; holdout remains untouched.

## Verified structural identity pilot (S.1D.4A)

The separate maintainer-only stem.hybrid module binds three explicitly authored structural rules to the exact mathematical review digests and LaTeX of Euler's identity, Pythagoras and mass-energy equivalence. It builds from the full scope-reviewed qualification dictionary, not the release compiler or legacy prototype. The existing sentence-v2 exact matcher runs first and is unchanged. New paths use the same conservative sentence selection, complete restricted-parser consumption, and exact structural keys. They do not render arbitrary parsed expressions. Stale rules or duplicate structural keys fail closed. Other representations remain exact-alias only.

Named introductions are narrowly anchored: "Euler's identity is" and "The Pythagorean theorem is" (including "is given by" or a colon). The name alone is insufficient. The exact normalized short sequence e to the i pi plus 1 equals 0 is eligible only after the named Euler introduction. This is an explicitly reviewed contextual exception, not a general exponent repair. The ambiguous sequence in ordinary narration remains rejected. Pythagorean substitutions require the named theorem introduction, the exact ordered sum of two squared symbols equal to a third squared symbol, and three distinct lowercase ASCII variables excluding e and i. No reorder, general symbol substitution, simplification or homophone inference is performed. The output preserves those variable names using a fixed safe template, not arbitrary TeX. Fixed-notation rules preserve case and use the reviewed corpus TeX. Exact legacy alias matching retains its existing case-insensitive behavior; it is not a new structural rule. Named-introduction selection and semantic conditions remain conservative lexical evidence, not proof of narrator intent or mathematical truth.

    python -m stem.qualify_hybrid --summary
    python -m stem.qualify_hybrid --observed work/stem-qualification/development-uniform-observations.json --summary
    python -m stem.qualify_hybrid --observed work/stem-qualification/development-formula_hint-observations.json --summary

The pilot must preserve the 4,110 existing synthetic cases and adds focused structural, context, notation and stale-rule tests. Reports include separate baseline/hybrid results on the same optional observations, bound policy, corpus and implementation digests. The original observation schema expects canonical representation LaTeX, so renamed Pythagorean examples are not yet supported by that observation format; the targeted unit tests check the actual substituted output. The original labeled audiobook positives do not have the new anchored Euler introduction; no recovery of those mentions is claimed. The next slice must address safe contextual span selection and observation labels for noncanonical notation before broadening structural coverage. No holdout inspection, corpus approval, production matcher or normal transcription changes. No general AST-to-LaTeX renderer, GPU or LLM requirement.

## Contextual spans and notation-aware observations (S.1D.4B)

The qualification-only hybrid pilot now accepts two additional bounded forms: a named identity followed by a complete expression and a comma-delimited where/which explanatory clause, and a complete short Euler recitation immediately followed by its explicit equivalent restatement (comma, or, e to the i pi equals negative one). The latter supplies local corroboration for the exponent scope without an identity name. It may end in a narrow comma-delimited prose continuation. The first expression alone is annotated; the alternative wording remains original narration. Both forms preserve exact source offsets. The full sentence must already pass the existing conservative candidate boundary policy. No arbitrary substring scanning, general suffix truncation, homophone guessing or cross-cue context is used. The named clause path requires an explicit anchored identity and rejects arithmetic or relation tokens in its explanatory tail. Context checks are lexical, not semantic proof.

The development sample contains three labeled Euler mentions. One includes an equivalent restatement in the same cue; the other two lack sufficient local corroboration. The new rule targets the former without assuming that the latter can be safely resolved from isolated cues. This is a development-derived rule, not held-out evidence. Real scores must be rerun locally; do not inspect holdout yet.

Hybrid qualification accepts the existing observation v1 format and a v2 format (fitbaus.stem.recognition-observations/v2). V2 adds a required latex field to each expected annotation. The expected TeX must equal the corpus representation or match the narrow distinct lowercase Pythagorean variable template (excluding e and i). Labels remain independent of matcher predictions: a missed or contextually ambiguous expression can still be labeled. The loader verifies schema, bounds, exact source spans, identity and notation allowlist, not mathematical interpretation or annotation correctness. The same exact ID/span/LaTeX metrics apply to baseline and hybrid, so rendering canonical variables when the source uses different variables counts as an error. V1 keeps canonical semantics; do not silently rewrite existing labels. Both formats retain declared, unverified provenance.

    python -m stem.qualify_hybrid --observed work/stem-qualification/development-uniform-observations.json --summary
    python -m stem.qualify_hybrid --observed work/stem-qualification/development-formula_hint-observations.json --summary

Seven additional focused tests cover equivalent restatement, named explanatory clauses, abstention, notation scoring, missed labels, invalid input and v1 compatibility. Existing 4,110 regression/context cases remain mandatory. No private audiobook text or observation files are committed; synthetic fixtures exercise the general rule. Policy and implementation hashes include the new context and label modules. No corpus approval, production integration, arbitrary expression rendering or inference. S.1D.4C expands structural coverage; S.1D.5 addresses adjacent cue context; S.1D.6 qualifies on development and untouched holdout data.

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
