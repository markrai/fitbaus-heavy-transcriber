from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".upstream"))

from transcriber.audiobookshelf import Audiobookshelf, SourceConfig, SourceError, identifier, valid_bearer
from transcriber.contract import TranscriptWindow, Cue, MAX_WINDOW_MS, SCHEMA
from transcriber.engine import normalize_segments, FORMATS, BYTES_PER_MS

REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
PROFILE_PREFIX = "faster-whisper-1.2.1-large-v3-fp16-" + REVISION + "-beam5-segments-v1:"
BUNDLE_SCHEMA = "fitbaus.heavy-transcript/v1"
MAX_BUNDLE = 32 * 1024 * 1024
MAX_BOOK_MS = 100 * 60 * 60 * 1000


class Vega:
    def __init__(self, host, remote_dir):
        import shlex
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}", host):
            raise ValueError("Invalid SSH host")
        if not remote_dir.startswith("/"):
            raise ValueError("Use an absolute remote Compose directory")
        self.prefix = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host]
        self.remote = "cd " + shlex.quote(remote_dir) + " && docker compose exec -T transcriber "

    def call(self, command, data=None, timeout=180):
        result = subprocess.run(self.prefix + [self.remote + command], input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError("VEGA command failed; check SSH, Compose and importer availability")
        return json.loads(result.stdout)

    def configuration(self):
        import shlex
        code = ("import json; from transcriber.config import Config; "
                "from transcriber.background import heavy_profile; "
                "c=Config.from_env(); print(json.dumps(dict(source_id=c.source.source_id,profile=heavy_profile(c.engine))))")
        value = self.call("python -c " + shlex.quote(code))
        identifier(value["source_id"])
        profile = value["profile"]
        if not re.fullmatch(re.escape(PROFILE_PREFIX) + r"(auto|[a-z]{2})", profile):
            raise ValueError("Incompatible VEGA heavy profile")
        return value

    def publish(self, token, bundle):
        payload = json.dumps(bundle, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        if len(payload) > MAX_BUNDLE:
            raise ValueError("Transcript bundle exceeds import limit")
        value = self.call("python -m transcriber import-heavy --token-stdin",
                          token.encode("ascii") + b"\n" + payload)
        if (value.get("state") != "completed" or value.get("model") != "large-v3" or
                value.get("audio_revision") != bundle["audio_revision"] or
                value.get("windows") != len(bundle["windows"])):
            raise ValueError("Invalid import acknowledgement")
        return value


class Library:
    def __init__(self, address, source_id, token, refresh=None):
        self.source = Audiobookshelf(SourceConfig(source_id, address))
        self._set_session(token, refresh)
        self._lock = threading.Lock()

    @classmethod
    def login(cls, address, source_id, username, password):
        source = Audiobookshelf(SourceConfig(source_id, address))
        token, refresh = source.login_session(username, password)
        return cls(address, source_id, token, refresh)

    def _set_session(self, token, refresh):
        if not valid_bearer(token) or (refresh is not None and not valid_bearer(refresh)):
            raise ValueError("Invalid Audiobookshelf credential")
        self._session = (token, refresh)

    def authorized(self, action):
        with self._lock:
            session = self._session
        try:
            return action(session[0])
        except SourceError as error:
            if error.code != "unauthorized":
                raise
        with self._lock:
            if self._session is session:
                if session[1] is None:
                    raise SourceError("unauthorized")
                self._set_session(*self.source.refresh_session(session[1]))
            token = self._session[0]
        return action(token)

    def get_json(self, path):
        def fetch(token):
            with self.source._get(path, token) as response:
                if response.headers.get_content_type() != "application/json":
                    raise ValueError("Unexpected library response")
                data = b"".join(self.source._chunks(response, 4 * 1024 * 1024, time.monotonic() + 30))
            return json.loads(data)
        return self.authorized(fetch)

    def books(self):
        result = {}
        for library in self.get_json("/api/libraries")["libraries"]:
            if library.get("mediaType") != "book":
                continue
            library_id = identifier(library["id"])
            for page in range(1000):
                data = self.get_json(f"/api/libraries/{library_id}/items?limit=100&page={page}&minified=1")
                rows = data["results"]
                if not isinstance(rows, list) or len(rows) > 100:
                    raise ValueError("Invalid library page")
                for row in rows:
                    if row.get("isMissing") or row.get("isInvalid"):
                        continue
                    item_id = identifier(row["id"])
                    media = row.get("media") or {}
                    meta = media.get("metadata") or {}
                    tracks = media.get("numTracks", media.get("numAudioTracks"))
                    if tracks == 0:
                        continue
                    result[item_id] = {"id": item_id, "title": str(meta.get("title") or item_id)[:300],
                                       "author": str(meta.get("authorName") or "")[:200],
                                       "duration": media.get("duration") or 0}
                if len(rows) < 100 or (page + 1) * 100 >= data.get("total", float("inf")):
                    break
            else:
                raise ValueError("Library page limit exceeded")
        return sorted(result.values(), key=lambda book: book["title"].casefold())

    def companions(self, item_id):
        from companions import discover

        identifier(item_id)
        item = self.get_json(f"/api/items/{item_id}?expanded=1")
        return discover(item, item_id)

    def epub_inventory(self, item_id, file_id):
        from epub_inventory import inspect_epub

        return self.inspect_companion(item_id, file_id, inspect_epub)

    def inspect_companion(self, item_id, file_id, inspect):
        from epub_inventory import MAX_EPUB_BYTES

        identifier(item_id)
        identifier(file_id)
        candidate = next((row for row in self.companions(item_id) if row.file_id == file_id), None)
        if candidate is None or candidate.format != "epub":
            raise ValueError("Unknown EPUB companion")
        if candidate.size > MAX_EPUB_BYTES:
            raise SourceError("size_limit")

        def fetch(token):
            with tempfile.TemporaryFile() as target:
                with self.source._get(f"/api/items/{item_id}/file/{file_id}", token) as response:
                    length = response.headers.get("Content-Length")
                    if length is not None and length != str(candidate.size):
                        raise SourceError("stale_revision")
                    for chunk in self.source._chunks(response, candidate.size, time.monotonic() + 120):
                        target.write(chunk)
                if target.tell() != candidate.size:
                    raise SourceError("incomplete_epub")
                current = next((row for row in self.companions(item_id) if row.file_id == file_id), None)
                if current != candidate:
                    raise SourceError("stale_revision")
                return inspect(target)

        return {"item_id": item_id, "file_id": file_id, **self.authorized(fetch)}

    def cover(self, item_id):
        identifier(item_id)
        def fetch(token):
            with self.source._get(f"/api/items/{item_id}/cover?width=256", token) as response:
                kind = response.headers.get_content_type()
                if kind not in ("image/jpeg", "image/png", "image/webp"):
                    raise ValueError("Unsupported cover")
                return kind, b"".join(self.source._chunks(response, 1024 * 1024, time.monotonic() + 15))
        return self.authorized(fetch)


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, separators=(",", ":")), encoding="ascii")
    temporary.replace(path)


def read_window(path, identity, start, end):
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Checkpoint exceeds result limit")
    value = json.loads(raw)
    window = TranscriptWindow(identity, start, end, tuple(
        Cue(c["start_ms"], c["end_ms"], c["text"]) for c in value["cues"]))
    if value != window.to_json():
        raise ValueError("Checkpoint identity or coverage mismatch")
    return window.to_json()


def checkpoint_directory(root, identity, profile):
    key = hashlib.sha256(profile.encode("ascii")).hexdigest()[:16]
    return root / identity.cache_key() / key


def preview_alignment(library, profile, item_id, file_id, root):
    from epub_alignment import AlignmentError, preview

    identifier(item_id)
    identifier(file_id)
    source = library.source
    manifest = library.authorized(lambda token: source.manifest(item_id, token))
    identity, duration = manifest.identity, manifest.duration_ms
    if not 0 < duration <= MAX_BOOK_MS:
        raise AlignmentError("Audio duration exceeds preview limit")
    directory = checkpoint_directory(root, identity, profile)

    def windows():
        for start in range(0, duration, MAX_WINDOW_MS):
            try:
                yield read_window(directory / f"{start}.json", identity, start,
                                  min(start + MAX_WINDOW_MS, duration))
            except FileNotFoundError:
                raise AlignmentError("Complete local narration checkpoints are required; transcribe this revision first") from None
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                raise AlignmentError("Retained narration checkpoint is invalid") from None

    if not all((directory / f"{start}.json").is_file() for start in range(0, duration, MAX_WINDOW_MS)):
        raise AlignmentError("Complete local narration checkpoints are required; transcribe this revision first")
    result = library.inspect_companion(item_id, file_id, lambda stream: preview(stream, windows()))
    current = library.authorized(lambda token: source.manifest(item_id, token))
    if current.identity != identity or current.duration_ms != duration:
        raise AlignmentError("Audio revision changed during alignment preview")
    return {**result, "source_id": identity.source_id, "audio_revision": identity.audio_revision,
            "profile": profile, "duration_ms": duration}


class WorkbenchError(RuntimeError):
    pass


def require_ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise WorkbenchError("FFmpeg executable not found on PATH. Install FFmpeg or restore its bin directory, then restart the workbench.")
    return executable


def decode(path, start, end):
    expected = (end - start) * BYTES_PER_MS
    command = [require_ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
               "-protocol_whitelist", "file,pipe", "-format_whitelist", FORMATS, "-threads", "1",
               "-ss", f"{start / 1000:.3f}", "-i", str(path), "-t", f"{(end-start)/1000:.3f}",
               "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", "-f", "s16le", "-fs", str(expected + 4096), "pipe:1"]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, check=True, timeout=120)
    except FileNotFoundError:
        raise WorkbenchError("FFmpeg executable disappeared or could not be launched. Check PATH.") from None
    except subprocess.CalledProcessError:
        raise WorkbenchError("FFmpeg could not decode the downloaded audio window.") from None
    except subprocess.TimeoutExpired:
        raise WorkbenchError("FFmpeg audio decoding timed out.") from None
    pcm = result.stdout
    if not pcm or len(pcm) % 2 or len(pcm) > expected + 4096 or len(pcm) < expected - min(expected // 10, 8000):
        raise WorkbenchError("FFmpeg returned incomplete or invalid decoded audio.")
    return pcm[:expected]


class GpuEngine:
    def __init__(self, language):
        self.language = None if language == "auto" else language
        self.model = None

    def transcribe(self, pcm, start, end):
        import numpy as np
        if self.model is None:
            import ctranslate2
            from faster_whisper import WhisperModel
            from huggingface_hub import snapshot_download
            if ctranslate2.get_cuda_device_count() < 1 or "float16" not in ctranslate2.get_supported_compute_types("cuda"):
                raise RuntimeError("CUDA FP16 unavailable")
            model = snapshot_download("Systran/faster-whisper-large-v3", revision=REVISION,
                                      allow_patterns=["config.json", "model.bin", "tokenizer.json",
                                                      "vocabulary.json", "preprocessor_config.json"])
            self.model = WhisperModel(model, device="cuda", compute_type="float16", num_workers=1, local_files_only=True)
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        segments, _ = self.model.transcribe(audio, language=self.language, task="transcribe",
                                             beam_size=5, temperature=0.0, condition_on_previous_text=False,
                                             vad_filter=True)
        return normalize_segments(segments, start, end, audio_duration_ms=len(pcm) // BYTES_PER_MS)


def process_book(library, vega, engine, profile, item_id, root, report):
    source = library.source
    report("Checking FFmpeg", 0, 0)
    require_ffmpeg()
    report("Checking audio revision", 0, 0)
    manifest = library.authorized(lambda token: source.manifest(item_id, token))
    identity, duration = manifest.identity, manifest.duration_ms
    if not 0 < duration <= MAX_BOOK_MS:
        raise ValueError("Book exceeds import duration limit")
    directory = checkpoint_directory(root, identity, profile)
    directory.mkdir(parents=True, exist_ok=True)
    windows = []
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        files = {}
        for start in range(0, duration, MAX_WINDOW_MS):
            end = min(start + MAX_WINDOW_MS, duration)
            path = directory / f"{start}.json"
            if path.exists():
                value = read_window(path, identity, start, end)
            else:
                cues = []
                previous = start
                for track in manifest.tracks:
                    left = max(start, track.offset_ms, previous)
                    right = min(end, track.offset_ms + track.duration_ms)
                    if left >= right:
                        continue
                    if track.file_id not in files:
                        report("Downloading audio", start, duration)
                        if shutil.disk_usage(directory).free < track.size + 256 * 1024 * 1024:
                            raise RuntimeError("Insufficient temporary disk space")
                        destination = Path(scratch) / track.file_id
                        def download(token):
                            with destination.open("w+b") as target:
                                with source.materialize_track(identity, track.file_id, token, directory, target=target):
                                    pass
                        library.authorized(download)
                        files[track.file_id] = destination
                    report("Decoding audio", start, duration)
                    pcm = decode(files[track.file_id], left - track.offset_ms, right - track.offset_ms)
                    report("Loading model / transcribing on GPU", start, duration)
                    cues.extend(engine.transcribe(pcm, left, right))
                    previous = right
                value = TranscriptWindow(identity, start, end, tuple(cues)).to_json()
                if len(json.dumps(value, ensure_ascii=True).encode("ascii")) > 1024 * 1024:
                    raise ValueError("Window exceeds import limit")
                atomic_json(path, value)
            windows.append(value)
            report("Transcribing on GPU", end, duration)
            for track in manifest.tracks:
                if track.offset_ms + track.duration_ms <= end and track.file_id in files:
                    files.pop(track.file_id).unlink()
    report("Publishing to VEGA", duration, duration)
    bundle = {"schema": BUNDLE_SCHEMA, "profile": profile, "source_id": identity.source_id,
              "item_id": identity.item_id, "audio_revision": identity.audio_revision,
              "duration_ms": duration, "windows": windows}
    def publish(token):
        current = source.manifest(item_id, token)
        if current.identity != identity or current.duration_ms != duration:
            raise ValueError("Audio revision changed; select the book again")
        return vega.publish(token, bundle)
    result = library.authorized(publish)
    atomic_json(directory / "published.json", result)
    report("Imported", duration, duration)
