# FitBaus Heavy Transcriber

A standalone GPU workbench for preparing high-quality audiobook transcripts for FitBaus. Run it manually on a Windows PC with an NVIDIA GPU; VEGA remains the Audiobookshelf and FitBaus Transcriber server.

## Setup

1. Merge and deploy the companion FitBaus Transcriber heavy-import change on VEGA.
2. Install Python 3.12, Git, FFmpeg, Windows OpenSSH, NVIDIA driver, and compatible CUDA 12 cuBLAS / cuDNN 9 DLLs on the GPU workstation. Ensure FFmpeg and the CUDA DLLs are on PATH. See the [Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu).
3. Set up SSH key authentication and a host alias for VEGA. Verify `ssh -o BatchMode=yes vega` works and the remote account can use Docker Compose.
4. Clone this repository and run:

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe app.py --abs-url http://YOUR_VEGA_IP:13378
```

For a different SSH host or Compose directory, pass `--ssh-host user@host --remote-dir /absolute/path/to/fitbaus-transcriber`. The defaults use the host alias `vega` and the standard development checkout `/home/vega/dev/project/fitbaus-transcriber`. Use HTTPS when available, or HTTP only on a trusted LAN.

At the terminal prompt, choose username and password (default) or an Audiobookshelf API key/access token. The password is exchanged directly with Audiobookshelf and is never sent to VEGA's importer. Access and refresh tokens stay in memory; renewable sessions retry a rejected request once using a refreshed access token. Only the current access token is transferred to the importer over SSH stdin. Credentials are not exposed to the browser, persisted, placed in command-line arguments, or sent to the model. If an older Audiobookshelf server does not issue a refresh token, restart the workbench and select the book again if the session expires; existing checkpoints are retained.

The interface opens at [http://127.0.0.1:8780](http://127.0.0.1:8780). Search the library, select books and click **Transcribe selected**. The UI is bound to loopback only. No separate GPU service, public import endpoint or Bike Bridge update is required.

## Troubleshooting

The application checks that FFmpeg is on PATH before opening the workbench and before downloading a book. On Windows, use `Get-Command ffmpeg` and `ffmpeg -version` to verify it. Restart the terminal after changing PATH. Batch failures identify the failed stage and safe diagnostic in both the UI and terminal; valid checkpoints are retained for retry.

## Processing

- The first job downloads the pinned [Systran Large-v3 model](https://huggingface.co/Systran/faster-whisper-large-v3/tree/edaa852ec7e145841d8ffdb056a99866b5f0a478) into the local Hugging Face cache. CUDA FP16 is required; there is no silent CPU fallback.
- Faster-Whisper 1.2.1, beam size 5, temperature 0, VAD and the VEGA transcription language are used. The pinned upstream checkout provides the existing audio identity, source validation, timestamp normalization and transcript contract; the utility does not modify that checkout.
- Tracks are downloaded directly from Audiobookshelf once per processing attempt, temporarily stored and removed when no longer needed. Five-minute transcript windows are saved under the ignored local `work/` directory. Retrying the same book and revision reuses valid checkpoints, including when upload failed. New audio revisions use a fresh checkpoint directory.
- A complete transcript is sent over SSH to the operator-only importer. VEGA checks the source identity, current revision, full aligned coverage, profile and storage limits before atomically publishing it. Existing CPU transcripts remain intact and usable until then.
- Imported windows are preferred over Small, Base and Tiny. The library badge means the local workbench previously received a successful import acknowledgement; it is not a live server inventory or proof that the book revision is still current.

## Scope

This is a personal single-workstation batch utility, not a distributed scheduler. One batch runs at a time (up to 32 selected books); individual failed books can be selected again. Closing the browser does not stop processing; Ctrl+C closes the UI and the current batch finishes before the process exits. The first version has no cancellation button or background daemon. Work files contain audiobook-derived text; keep them private. Delete the local work directory to discard checkpoints and reprocess.

VEGA's existing prepared-transcript quotas still apply. Full-book imports are limited to 100 hours, 32 MiB of serialized transcript data and the existing per-window limit. Imported Large-v3 data is operator-managed and not displayed in the bike's ordinary CPU-model preparation job list.

## Verification

Run the same checks used by GitHub Actions from a local checkout. Requires Git, Python 3.12, and Node.js 24 with npm for the renderer suite. No CUDA runtime, model weights, Audiobookshelf credentials, or VEGA connection is needed.

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

With no argument, only core CI runs, matching the required ordinary GitHub workflow. Core prepares the pinned contract, compiles active Python modules and runs all current top-level tests except test_stem*.py. The opt-in stem suite prepares the same contract, compiles the dormant STEM modules, validates the corpus and runs all test_stem*.py tests. The renderer suite installs npm dependencies and performs policy and real rendering checks. Both research workflows are manual dispatch only. Use all explicitly to run all three suites, stopping at the first failure. The shared test selector keeps core and STEM discovery disjoint; new top-level test modules are included automatically by naming convention. All suites report elapsed time, pass/fail/skip counts and exit status. Core refuses dirty or invalid upstream checkouts. No Node.js, renderer dependency, GPU, or research corpus download is required for core CI.

The GitHub workflow also provisions the toolchains and uploads the generated renderer package-lock artifact. Local runs leave that lockfile in `stem/renderer/`. Until the renderer lockfile is committed, transitive npm resolution is not guaranteed identical between fresh installs. The scripts reproduce the checks and version requirements, not the hosted runner image or exact Python/Node patch versions. GitHub currently executes these suites on Windows; Linux/macOS runs are useful local checks but not proof of Windows compatibility.

Tests use fake source, inference and SSH adapters; they do not need GPU weights or your audiobook library. Actual NVIDIA runtime, SSH transport and audiobook playback must be qualified on the target workstation.

## Ebook-assisted enrichment (E.0)

Select exactly one audiobook in the Workbench and click **Check companion files**. The Workbench uses the existing authenticated Audiobookshelf session to fetch the expanded item and list the primary ebook and attached/supplementary ebook files, deduplicated by file ID. This is explicit read-only metadata discovery: library refresh, ordinary transcription, and publication make no additional companion requests. No ebook contents are downloaded, no server paths or credentials are returned to the browser, and an attachment is not proof of a matching edition. EPUB is the first planned extraction format; PDF and other recognized attachments are listed for future work. Permission, malformed metadata, and unavailable-item errors remain distinct from a successful empty result in the UI. The current server's metadata shape must be qualified using an actual attached ebook.

## EPUB inventory (E.1)

After checking companion files, click **Inspect EPUB** next to an EPUB attachment. The workbench revalidates its item/file identity and metadata, streams the authenticated file into a temporary file, checks the byte count and metadata again, then computes SHA-256 and inventories the package and ordered spine. The browser receives counts, basic bibliographic metadata and the content digest, not internal paths, raw ebook text or images. No persistent ebook copy, external network resource, model call, or VEGA publication is created. Ordinary transcription remains independent.

This conservative first reader accepts UTF-8 XML in a single EPUB 2/3 package, with local XHTML/SVG spine resources. It rejects encrypted/obfuscated archives, remote manifest references, unsafe paths, duplicate entries and unsupported compression. Limits: 64 MiB download, 256 MiB declared expanded size, 32 MiB per member, 2 MiB per metadata XML document, 4,096 ZIP entries, and 120 seconds for the transfer (subject to the existing per-read socket timeout). Only package metadata is inflated; other member contents, CRCs, and actual expanded sizes are not yet qualified. The archive is never extracted or rendered. An inventory is not a full EPUB conformance check or proof of an audiobook edition match. The actual Audiobookshelf file endpoint and supported EPUB variants still need target-workstation qualification.

## EPUB alignment preview (E.2)

After transcribing an audiobook on the current workstation, check companion files and click **Test alignment** next to an EPUB. The preview requires every retained five-minute checkpoint for the current audio revision and active Large-v3 profile; it never generates new transcription, queries VEGA for text, or changes existing checkpoints. It uses the same bounded authenticated EPUB transfer as E.1, rechecks the current audio revision after matching and returns only aggregate counts to the UI.

The deterministic baseline tokenizes normalized Unicode words from linear XHTML spine entries, ignoring markup, navigation, figures, scripts, non-XHTML content and explicitly hidden nodes. Unique exact eight-word sequences must occur once in both the eligible ebook text and the narration. A cue's anchors must agree on the same section and offset; only the longest contiguous exact run is reported, and overlapping or reversed candidate positions are rejected on both sides. Matching is at cue granularity, not word timing. Short cues, transcription errors, repeated phrases and altered editions may yield few or no anchors. No interpolation, fuzzy match, edition verification or calibrated confidence is implied. The internal preview identifies the EPUB content hash, canonical transcript digest, audio revision, model profile and ordered spine/token coordinates; no raw text, anchors or archive paths are returned to the browser or persisted. Limits: 500,000 normalized words on each side, 100,000 cues, 32 MiB canonical transcript and 32 MiB total declared linear XHTML; individual XML limits remain in force. CSS visibility, alternative readings, non-linear sections and scanned pages are not interpreted.

The alignment baseline still requires qualification against real matched and mismatched books.

## Original ebook visuals (E.3)

Click **Find visuals** next to a discovered EPUB. This explicit operation uses the same authenticated temporary download to extract original inline MathML, inline SVG and local manifest-declared PNG, JPEG, GIF, WebP or SVG images referenced from linear XHTML. Standalone linear SVG spine entries are also supported. The internal catalogue contains original resource bytes or reserialized inline XML subtrees, media types, SHA-256 digests, content-addressed asset IDs and individual occurrences in source order (spine index, document path, zero-based element-child path relative to XHTML body, and enclosing figure path when applicable). Identical media type and payload are deduplicated without collapsing occurrence locations. Standalone SVG uses the document root as its location.

The browser receives aggregate counts only; payloads and source paths are discarded after the request. Nothing is rendered, executed, fetched externally, persisted or published. Extracted XML and image bytes are untrusted; a matching signature or parseable XML does not establish safe rendering, complete decoding, or self-contained SVG. Inline serialization preserves element structure but not original lexical bytes or inherited styling. Raster images are not classified as equations or diagrams. Non-linear sections, remote or undeclared resources, responsive image containers, CSS backgrounds, hidden elements marked in HTML, and non-supported formats are outside this baseline. The scan does not infer visual meaning, extract math from raster pixels, evaluate CSS, or establish edition equivalence.

Limits: 4 MiB per asset (the existing 2 MiB XML limit applies to XML documents), 16 MiB total unique payload, 32 MiB declared linear document bytes, 2,048 visual candidates and 128 levels of nesting. An invalid or oversized supported payload fails the preview; unsupported references are counted and skipped. The preview does not claim timestamps or word coordinates. E.4 must connect DOM locations with the same text projection used by alignment, establish bounded timing evidence, and abstain when evidence is insufficient. Safe rendering and delivery are later phases.

## Dormant spoken-math research

See [STEM dictionary and corpus acquisition](stem/README.md). All existing research code, corpus, fixtures and evidence formats are retained. The spoken-math engine is suspended, not a production fallback, and is not imported by normal processing. Run ci.bat stem (or ./ci.sh stem) explicitly to exercise its regression suite; renderer qualification is also opt-in. No research data, model downloads or renderer dependencies are required for the new approach.
