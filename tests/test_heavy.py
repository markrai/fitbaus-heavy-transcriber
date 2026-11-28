import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import contextmanager

from heavy import PROFILE_PREFIX, TranscriberServer, process_book, require_ffmpeg, WorkbenchError, decode
from transcriber.contract import AudioIdentity, Cue
from transcriber.audiobookshelf import Manifest, Track


class FakeSource:
    def __init__(self):
        self.identity = AudioIdentity("home", "book", "a" * 64)
        self.value = Manifest(self.identity, (Track("123", 0, 301000, 5, 0, 0),))
        self.downloads = 0

    def manifest(self, item, token):
        return self.value

    @contextmanager
    def materialize_track(self, identity, file_id, token, directory, target):
        self.downloads += 1
        target.write(b"audio")
        target.flush()
        yield target


class FakeServer:
    def __init__(self):
        self.bundles = []
        self.fail = True

    def publish(self, token, bundle):
        self.bundles.append(bundle)
        if self.fail:
            raise RuntimeError("Offline")
        return {"state": "completed", "job_id": "a" * 64}


class HeavyTest(unittest.TestCase):
    @patch("heavy.require_ffmpeg", return_value="ffmpeg")
    @patch("heavy.decode", return_value=b"audio")
    def test_checkpoints_survive_failed_publish_and_avoid_redownload(self, decode, ffmpeg):
        source = FakeSource()
        library = SimpleNamespace(source=source, authorized=lambda action: action("token"))
        server = FakeServer()
        calls = []
        engine = SimpleNamespace(transcribe=lambda pcm, start, end: (
            calls.append((start, end)) or (Cue(start, min(end, start + 1000), "text"),)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                process_book(library, server, engine, PROFILE_PREFIX + "auto", "book", root, lambda *args: None)
            self.assertEqual(source.downloads, 1)
            self.assertEqual(calls, [(0, 300000), (300000, 301000)])
            server.fail = False
            process_book(library, server, engine, PROFILE_PREFIX + "auto", "book", root, lambda *args: None)
            self.assertEqual(source.downloads, 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(server.bundles[0], server.bundles[1])
            self.assertEqual(server.bundles[1]["windows"][-1]["coverage"], {"start_ms": 300000, "end_ms": 301000})

    def test_publish_credential_is_stdin_only(self):
        server = TranscriberServer("server", "/srv/transcriber")
        bundle = {"audio_revision": "a" * 64, "windows": [{}]}
        with patch.object(server, "call", return_value={"state": "completed", "model": "large-v3",
                           "audio_revision": "a" * 64, "windows": 1}) as call:
            server.publish("secret", bundle)
            command, payload = call.call_args.args
            self.assertNotIn("secret", command)
            token, raw = payload.split(b"\n", 1)
            self.assertEqual(token, b"secret")
            self.assertEqual(json.loads(raw), bundle)

    @patch("heavy.shutil.which", return_value=None)
    def test_missing_ffmpeg_fails_before_fetching_audio(self, which):
        with self.assertRaisesRegex(WorkbenchError, "FFmpeg executable not found on PATH"):
            require_ffmpeg()
        source = FakeSource()
        library = SimpleNamespace(source=source, authorized=lambda action: action("token"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(WorkbenchError, "FFmpeg executable not found on PATH"):
                process_book(library, FakeServer(), None, PROFILE_PREFIX + "auto", "book",
                             Path(directory), lambda *args: None)
        self.assertEqual(source.downloads, 0)

    @patch("heavy.require_ffmpeg", return_value="ffmpeg")
    @patch("heavy.subprocess.run", side_effect=FileNotFoundError)
    def test_decoder_launch_failure_is_actionable(self, run, ffmpeg):
        with self.assertRaisesRegex(WorkbenchError, "FFmpeg executable disappeared"):
            decode(Path("audio"), 0, 1000)
