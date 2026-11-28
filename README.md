# FitBaus Heavy Transcriber

A standalone GPU workbench for preparing high-quality audiobook transcripts for FitBaus. Run it manually on a Windows PC with an NVIDIA GPU; Audiobookshelf and FitBaus Transcriber run on your own server.

## Setup

1. Merge and deploy the companion FitBaus Transcriber heavy-import change on the transcriber server.
2. Install Python 3.12, Git, FFmpeg, Windows OpenSSH, NVIDIA driver, and compatible CUDA 12 cuBLAS / cuDNN 9 DLLs on the GPU workstation. Ensure FFmpeg and the CUDA DLLs are on PATH. See the [Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu).
3. Set up SSH key authentication for your transcriber server. Verify `ssh -o BatchMode=yes user@server` works and the remote account can use Docker Compose.
4. Clone this repository and run:

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe app.py --abs-url http://YOUR_AUDIOBOOKSHELF_HOST:13378 --ssh-host user@server --remote-dir /absolute/path/to/fitbaus-transcriber
```

Supply your own SSH host and absolute remote Compose directory via those flags, or set `FITBAUS_SSH_HOST` and `FITBAUS_REMOTE_DIR`. There are no machine-specific defaults. Restart the Python application after pulling updates; static assets are captured at startup so frontend and API versions remain consistent. Use HTTPS when available, or HTTP only on a trusted LAN.

At the terminal prompt, choose username and password (default) or an Audiobookshelf API key/access token. The password is exchanged directly with Audiobookshelf and is never sent to the transcriber server's importer. Access and refresh tokens stay in memory; renewable sessions retry a rejected request once using a refreshed access token. Only the current access token is transferred to the importer over SSH stdin. Credentials are not exposed to the browser, persisted, placed in command-line arguments, or sent to the model. If an older Audiobookshelf server does not issue a refresh token, restart the workbench and select the book again if the session expires; existing checkpoints are retained.

The interface opens at [http://127.0.0.1:8780](http://127.0.0.1:8780). Search the library, select books and click **Transcribe selected**. The UI is bound to loopback only. No separate GPU service, public import endpoint or Bike Bridge update is required.

## Troubleshooting

The application checks that FFmpeg is on PATH before opening the workbench and before downloading a book. On Windows, use `Get-Command ffmpeg` and `ffmpeg -version` to verify it. Restart the terminal after changing PATH. Batch failures identify the failed stage and safe diagnostic in both the UI and terminal; valid checkpoints are retained for retry.

## Processing

- The first job downloads the pinned [Systran Large-v3 model](https://huggingface.co/Systran/faster-whisper-large-v3/tree/edaa852ec7e145841d8ffdb056a99866b5f0a478) into the local Hugging Face cache. CUDA FP16 is required; there is no silent CPU fallback.
- Faster-Whisper 1.2.1, beam size 5, temperature 0, VAD and the transcriber server transcription language are used. The pinned upstream checkout provides the existing audio identity, source validation, timestamp normalization and transcript contract; the utility does not modify that checkout.
- Tracks are downloaded directly from Audiobookshelf once per processing attempt, temporarily stored and removed when no longer needed. Five-minute transcript windows are saved under the ignored local `work/` directory. Retrying the same book and revision reuses valid checkpoints, including when upload failed. New audio revisions use a fresh checkpoint directory.
- A complete transcript is sent over SSH to the operator-only importer. the transcriber server checks the source identity, current revision, full aligned coverage, profile and storage limits before atomically publishing it. Existing CPU transcripts remain intact and usable until then.
- Imported windows are preferred over Small, Base and Tiny. The library badge means the local workbench previously received a successful import acknowledgement; it is not a live server inventory or proof that the book revision is still current.

## Scope

This is a personal single-workstation batch utility, not a distributed scheduler. One batch runs at a time (up to 32 selected books); individual failed books can be selected again. Closing the browser does not stop processing; Ctrl+C closes the UI and the current batch finishes before the process exits. The first version has no cancellation button or background daemon. Work files contain audiobook-derived text; keep them private. Delete the local work directory to discard checkpoints and reprocess.

The transcriber server's existing prepared-transcript quotas still apply. Full-book imports are limited to 100 hours, 32 MiB of serialized transcript data and the existing per-window limit. Imported Large-v3 data is operator-managed and not displayed in the bike's ordinary CPU-model preparation job list.

## Verification

Run the same checks used by GitHub Actions from a local checkout. Requires Git, Python 3.12, and Node.js 24 with npm for the renderer suite. No CUDA runtime, model weights, Audiobookshelf credentials, or the transcriber server connection is needed.

Windows (Command Prompt):

```bat
ci.bat
ci.bat core
ci.bat stem
ci.bat renderer
ci.bat all
```

Linux/macOS:

```sh
./ci.sh
./ci.sh core
./ci.sh stem
./ci.sh renderer
./ci.sh all
```

With no argument, only core CI runs, matching the required ordinary GitHub workflow. Core prepares the pinned contract, compiles active Python modules and runs all current top-level tests except test_stem*.py. The opt-in stem suite prepares the same contract, compiles the dormant STEM modules, validates the corpus and runs all test_stem*.py tests. The renderer suite installs npm dependencies and performs policy and real rendering checks. Both research workflows are manual dispatch only. Use all explicitly to run all three suites, stopping at the first failure. The shared test selector keeps core and STEM discovery disjoint; new top-level test modules are included automatically by naming convention. All suites report elapsed time, pass/fail/skip counts and exit status. Core refuses dirty or invalid upstream checkouts. Core installs the pinned raster decoder and active EPUB delivery renderer for real regression tests (Node.js 24 and npm required). Dormant STEM/TeX renderer workflows remain opt-in; no GPU or research corpus download is required.

The GitHub workflow also provisions the toolchains and uploads the generated renderer package-lock artifact. Local runs leave that lockfile in `stem/renderer/`. Until the renderer lockfile is committed, transitive npm resolution is not guaranteed identical between fresh installs. The scripts reproduce the checks and version requirements, not the hosted runner image or exact Python/Node patch versions. GitHub currently executes these suites on Windows; Linux/macOS runs are useful local checks but not proof of Windows compatibility.

Tests use fake source, inference and SSH adapters; they do not need GPU weights or your audiobook library. Actual NVIDIA runtime, SSH transport and audiobook playback must be qualified on the target workstation.

## Ebook-assisted enrichment (E.0)

The library shows the primary ebook format hint from Audiobookshelf's minified list when available. Selecting a single audiobook automatically checks its expanded companion metadata; there is no manual discovery button. The normal transcription batch also checks every selected audiobook independently before processing, unless the default-on **Include ebook enrichment when available** option is unchecked. The hint is not authoritative and its absence does not prevent batch discovery. The former diagnostic actions are under **Advanced ebook diagnostics**. The Workbench uses the existing authenticated Audiobookshelf session to fetch the expanded item and list the primary ebook and attached/supplementary ebook files, deduplicated by file ID. Library refresh uses the list hint immediately; visible rows are then checked sequentially for actual companions, even if older Audiobookshelf versions omit the hint. Selecting a book prioritizes its lookup and shares any in-flight request. Results are cached until refresh; errors are shown as unknown, not absent. Discovery checks remain read-only. No ebook contents are downloaded, no server paths or credentials are returned to the browser, and an attachment is not proof of a matching edition. EPUB is the first planned extraction format; PDF and other recognized attachments are listed for future work. Permission, malformed metadata, unexpected failures and unavailable-item errors remain distinct from a successful empty result in the UI. After successful narration import, the batch automatically prepares and renders a local candidate using the unique primary EPUB or sole attached EPUB; multiple EPUBs without a unique primary are reported rather than guessed. Audio success is preserved even if enrichment fails. No visual publication occurs until the transcriber server transport is implemented. The current server's metadata shape must be qualified using an actual attached ebook.

## EPUB inventory (E.1)

After checking companion files, click **Inspect EPUB** next to an EPUB attachment. The workbench revalidates its item/file identity and metadata, streams the authenticated file into a temporary file, checks the byte count and metadata again, then computes SHA-256 and inventories the package and ordered spine. The browser receives counts, basic bibliographic metadata and the content digest, not internal paths, raw ebook text or images. No persistent ebook copy, external network resource, model call, or the transcriber server publication is created. Ordinary transcription remains independent.

This conservative first reader accepts UTF-8 XML in a single EPUB 2/3 package, with local XHTML/SVG spine resources. It rejects encrypted/obfuscated archives, remote manifest references, unsafe paths, duplicate entries and unsupported compression. Limits: 64 MiB download, 256 MiB declared expanded size, 32 MiB per member, 2 MiB per metadata XML document, 4,096 ZIP entries, and 120 seconds for the transfer (subject to the existing per-read socket timeout). Only package metadata is inflated; other member contents, CRCs, and actual expanded sizes are not yet qualified. The archive is never extracted or rendered. An inventory is not a full EPUB conformance check or proof of an audiobook edition match. The actual Audiobookshelf file endpoint and supported EPUB variants still need target-workstation qualification.

## EPUB alignment preview (E.2)

After transcribing an audiobook on the current workstation, check companion files and click **Test alignment** next to an EPUB. The preview requires every retained five-minute checkpoint for the current audio revision and active Large-v3 profile; it never generates new transcription, queries the transcriber server for text, or changes existing checkpoints. It uses the same bounded authenticated EPUB transfer as E.1, rechecks the current audio revision after matching and returns only aggregate counts to the UI.

The deterministic baseline tokenizes normalized Unicode words from linear XHTML spine entries, ignoring markup, navigation, figures, scripts, non-XHTML content and explicitly hidden nodes. Unique exact eight-word sequences must occur once in both the eligible ebook text and the narration. A cue's anchors must agree on the same section and offset; only the longest contiguous exact run is reported, and overlapping or reversed candidate positions are rejected on both sides. Matching is at cue granularity, not word timing. Short cues, transcription errors, repeated phrases and altered editions may yield few or no anchors. No interpolation, fuzzy match, edition verification or calibrated confidence is implied. The internal preview identifies the EPUB content hash, canonical transcript digest, audio revision, model profile and ordered spine/token coordinates; no raw text, anchors or archive paths are returned to the browser or persisted. Limits: 500,000 normalized words on each side, 100,000 cues, 32 MiB canonical transcript and 32 MiB total declared linear XHTML; individual XML limits remain in force. CSS visibility, alternative readings, non-linear sections and scanned pages are not interpreted.

The alignment baseline still requires qualification against real matched and mismatched books.

## Original ebook visuals (E.3)

Click **Find visuals** in Advanced ebook diagnostics next to a discovered EPUB. This explicit operation uses the same authenticated temporary download to extract original inline MathML, inline SVG and local manifest-declared PNG, JPEG, GIF, WebP or SVG images referenced from linear XHTML. Standalone linear SVG spine entries are also supported. The internal catalogue contains original resource bytes or reserialized inline XML subtrees, media types, SHA-256 digests, content-addressed asset IDs and individual occurrences in source order (spine index, document path, zero-based element-child path relative to XHTML body, and enclosing figure path when applicable). Identical media type and payload are deduplicated without collapsing occurrence locations. Standalone SVG uses the document root as its location.

The browser receives aggregate counts only; payloads and source paths are discarded after the request. Nothing is rendered, executed, fetched externally, persisted or published. Extracted XML and image bytes are untrusted; a matching signature or parseable XML does not establish safe rendering, complete decoding, or self-contained SVG. Inline serialization preserves element structure but not original lexical bytes or inherited styling. Raster images are not classified as equations or diagrams. Non-linear sections, remote or undeclared resources, responsive image containers, CSS backgrounds, hidden elements marked in HTML, and non-supported formats are outside this baseline. The scan does not infer visual meaning, extract math from raster pixels, evaluate CSS, or establish edition equivalence.

Limits: 4 MiB per asset (the existing 2 MiB XML limit applies to XML documents), 16 MiB total unique payload, 32 MiB declared linear document bytes, 2,048 visual candidates and 128 levels of nesting. An invalid or oversized supported payload fails the preview; unsupported references are counted and skipped. XML/HTML base overrides fail closed rather than silently resolving to the wrong image. The preview does not claim timestamps or word coordinates. Safe rendering and delivery are later phases.

## Visual timing evidence (E.4)

Click **Test visual timing** in Advanced ebook diagnostics after completing local transcription. One authenticated EPUB download is used for both original asset extraction and text alignment. Both passes verify the same EPUB digest; the current audio revision, profile and complete checkpoint contract are revalidated through the existing retained-transcript path. The shared text projection maps DOM locations to normalized word boundaries without changing the E.2 token stream. A figure uses its enclosing figure start, not its caption or an inferred semantic reference. If splitting at marked DOM boundaries changes tokenization, that section's coordinates are withheld. Standalone SVG and visuals inside excluded prose subtrees lack coordinates.

The versioned exact-anchor-bounds/v1 policy records an interval, never a guessed point timestamp: either an exact cue anchor extends at least four words on both sides of the visual location, or two adjacent narration cues have ordered exact anchors within 24 ebook words on either side in the same spine entry. The interval spans the whole supporting cue or pair of cues and must be at most 30 seconds. No interpolation, nearest-chapter fallback, fabricated duration or calibrated confidence is provided. Missing, distant, conflicting, nonadjacent or overly wide evidence leaves the occurrence untimed with a reason. This locates a visual in surrounding narration, not necessarily the precise instant it is discussed.

The internal preview carries EPUB and transcript digests, source/audio/profile identity, occurrence coordinates, supporting cue indices and word ranges, and earliest/latest bounds. The browser receives counts and reason/method summaries only. No payloads, paths, intervals or raw text are returned or persisted; no GPU, model calls, rendering, publication or bike behavior changes. Edition, rendering and playback remain unqualified. Thresholds are conservative engineering defaults pending matched/mismatched real-book measurements. E.5 builds on this evidence contract, not a production playback schedule.

## Local enrichment preparation (E.5)

For a manual diagnostic, click **Prepare enrichment** beside a discovered EPUB after completing the current audio revision's local Large-v3 transcription. This replaces the need to run the individual diagnostic previews first: one temporary authenticated EPUB download feeds asset extraction, alignment and timing association. Complete checkpoint validation and the final audio revision check finish before any artifact is written. No model, GPU, SSH publication or the transcriber server changes are involved.

A canonical JSON artifact (fitbaus.epub-enrichment/v1) is saved under the work directory at enrichment/<SHA-256-of-file>.json. It binds the source, audiobook, companion file, audio revision, model profile, duration, EPUB digest, canonical transcript digest and timing policy to deduplicated base64-encoded original visual payloads and per-occurrence evidence or abstention reasons. Asset hashes, media representations, references, summary counts and timing bounds are checked before storage. Both timed and untimed occurrences are retained for review; the artifact has no scheduled playback points. All three edition/render/playback qualification flags remain false.

The same canonical content yields the same filename and is reused only if the existing bytes match. New files use a flushed temporary file and atomic replacement; a failed preparation does not publish a partial artifact. The local store is limited to 32 MiB per artifact, 512 MiB total JSON files and 128 artifacts in the supported single-workbench process model. No automatic eviction or cross-process coordination is provided. Remove obsolete artifacts manually if the store fills. The default work directory is ignored by Git; treat custom work directories and backups as private audiobook-derived data. The browser receives only the artifact ID, byte count, summary and reuse status, not payloads or internal paths. The digest is content integrity, not a signature or proof of edition equivalence.

E.6 must independently validate the artifact and current source identities at the delivery boundary, qualify safe rendering (never execute extracted SVG/XML), establish playback eligibility and integrate only the approved delivery format. Do not serve these local JSON artifacts directly to the bike.

## Local raster delivery candidates (E.6A.1)

Install the independently pinned raster dependency in the workbench virtual environment: `python -m pip install --only-binary=:all: -r requirements-delivery.txt`. Core CI installs this same dependency, but the normal transcription and E.0–E.5 paths do not import Pillow. Run `python -m epub_delivery <full-enrichment-artifact-id> --work-dir work` to create a local candidate from a prepared E.5 artifact. No audiobook download, model call or publication occurs.

The input file name and canonical contents must agree with the SHA-256 artifact ID; asset digests, timing evidence, summary and provenance are rechecked using the E.5 contract. Only unique raster assets with bounded timing evidence are decoded. Each decode runs in a separate Python isolated-mode subprocess with a 10-second timeout, a pinned Pillow version, restricted formats, 4 MiB input, 8 million source pixels, maximum 8192 source edge, and no animation. Original bytes never go to the consumer: the worker verifies and loads the image, applies EXIF orientation, fits within 1024×600 without upscaling, and writes fresh metadata-free RGBA PNG. The parent independently checks chunk types, CRCs, dimensions, bounded decompression and scanline filters. Output is limited to 1 MiB per PNG, 128 eligible source assets and 16 MiB total unique PNGs. Invalid or unsupported rasters are withheld; an unexpected worker failure or exceeded aggregate budget aborts preparation. This subprocess is not an OS security sandbox.

The versioned fitbaus.epub-delivery-candidate/v1 JSON stores only normalized PNGs, source asset and artifact identities, and original bounded timing evidence for candidate occurrences. Untimed and unsupported occurrences are counted, not delivered. It uses the same atomic content-addressed storage policy under work/delivery (separate limits from enrichment). No raw XML, archive paths or original image metadata are included. No edition, rendering or playback qualification flag is promoted. The format is a local candidate, not a playback schedule or proof that an image is discussed in narration. Real-device memory/decode checks and current source identity validation remain mandatory before the transcriber server publication.

## Local MathML and SVG delivery candidates (E.6A.2)

Install Node.js 24 and run `npm install --ignore-scripts --no-audit --no-fund --prefix delivery_renderer` in addition to the pinned Python decoder. The existing epub_delivery CLI now processes eligible original MathML and SVG as well as raster assets. The policy changes to static-rgba-png/v2; v1 artifacts remain separate. The active worker uses pinned MathJax 4.1.3 with MathML input only, the New Computer Modern font package, and Resvg 2.6.2. No dormant STEM code, TeX generation, LLM or browser execution is involved. Top-level npm versions are pinned; transitive resolution is not locked yet.

The XML preflight accepts a conservative presentation MathML subset (tokens, fractions, radicals, scripts, rows and basic tables) and an SVG subset of local geometric shapes with explicit bounded attributes. It rejects unsupported markup rather than dropping potentially meaningful content: CSS, links, scripts, images, external references, text in SVG, filters, gradients and reusable symbols are unsupported. A semantics wrapper with a presentation child and plain-text TeX/text annotations is accepted after discarding only those non-rendered annotations; annotation-xml and other annotation types are rejected. Input and generated SVG are separately validated, namespace-normalized and capped at 256 KiB, 4096 nodes and 48 levels of nesting. MathJax output must be path/shape-only and free of error nodes. SVG uses a bounded viewport and a white background, with no system fonts. Each renderer process has a 20-second timeout and Node heap limit; native memory is not OS-sandboxed. The PNG then passes through the existing raster normalization and independent PNG validator. Unsupported or timed-out visuals are withheld; missing dependencies or unexpected worker failure abort preparation.

Core CI runs actual MathML and SVG render tests as well as policy rejection cases. This establishes candidate output, not real-book visual fidelity, edition equivalence or physical bike qualification. E.6B onward handles independent ingestion and delivery eligibility; no artifacts are published by this command.

## Dormant spoken-math research

See [STEM dictionary and corpus acquisition](stem/README.md). All existing research code, corpus, fixtures and evidence formats are retained. The spoken-math engine is suspended, not a production fallback, and is not imported by normal processing. Run ci.bat stem (or ./ci.sh stem) explicitly to exercise its regression suite; renderer qualification is also opt-in. No research data, model downloads or renderer dependencies are required for the new approach.
