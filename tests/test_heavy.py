import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import contextmanager

from heavy import PROFILE_PREFIX, Vega, process_book
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


class FakeVega:
    def __init__(self):
        self.bundles = []
        self.fail = True

    def publish(self, token, bundle):
        self.bundles.append(bundle)
        if self.fail:
            raise RuntimeError("Offline")
        return {"state": "completed", "job_id": "a" * 64}


class HeavyTest(unittest.TestCase):
    @patch("heavy.decode", return_value=b"audio")
    def test_checkpoints_survive_failed_publish_and_avoid_redownload(self, decode):
        source = FakeSource()
        library = SimpleNamespace(source=source, token="token")
        vega = FakeVega()
        calls = []
        engine = SimpleNamespace(transcribe=lambda pcm, start, end: (
            calls.append((start, end)) or (Cue(start, min(end, start + 1000), "text"),)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                process_book(library, vega, engine, PROFILE_PREFIX + "auto", "book", root, lambda *args: None)
            self.assertEqual(source.downloads, 1)
            self.assertEqual(calls, [(0, 300000), (300000, 301000)])
            vega.fail = False
            process_book(library, vega, engine, PROFILE_PREFIX + "auto", "book", root, lambda *args: None)
            self.assertEqual(source.downloads, 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(vega.bundles[0], vega.bundles[1])
            self.assertEqual(vega.bundles[1]["windows"][-1]["coverage"], {"start_ms": 300000, "end_ms": 301000})

    def test_publish_credential_is_stdin_only(self):
        vega = Vega("vega", "/srv/transcriber")
        bundle = {"audio_revision": "a" * 64, "windows": [{}]}
        with patch.object(vega, "call", return_value={"state": "completed", "model": "large-v3",
                           "audio_revision": "a" * 64, "windows": 1}) as call:
            vega.publish("secret", bundle)
            command, payload = call.call_args.args
            self.assertNotIn("secret", command)
            token, raw = payload.split(b"\n", 1)
            self.assertEqual(token, b"secret")
            self.assertEqual(json.loads(raw), bundle)
