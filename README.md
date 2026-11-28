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

Next: bounded EPUB acquisition, format/edition validation, alignment of retained narration with ebook text, original equation/figure extraction, and independently versioned enrichment artifacts.

## Dormant spoken-math research

See [STEM dictionary and corpus acquisition](stem/README.md). All existing research code, corpus, fixtures and evidence formats are retained. The spoken-math engine is suspended, not a production fallback, and is not imported by normal processing. Run ci.bat stem (or ./ci.sh stem) explicitly to exercise its regression suite; renderer qualification is also opt-in. No research data, model downloads or renderer dependencies are required for the new approach.
