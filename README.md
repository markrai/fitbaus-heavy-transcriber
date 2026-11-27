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

Enter your own Audiobookshelf API key at the terminal prompt. It stays in memory and is transferred to VEGA over SSH stdin for authorization; it is not exposed to the browser, persisted, placed in command-line arguments, or sent to the model. Use a key with access to the desired books rather than an expiring login token.

The interface opens at [http://127.0.0.1:8780](http://127.0.0.1:8780). Search the library, select books and click **Transcribe selected**. The UI is bound to loopback only. No separate GPU service, public import endpoint or Bike Bridge update is required.

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

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fake source, inference and SSH adapters; they do not need GPU weights or your audiobook library. Actual NVIDIA runtime, SSH transport and audiobook playback must be qualified on the target workstation.
