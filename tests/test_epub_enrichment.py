import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import Workbench
from epub_enrichment import EnrichmentError, build_artifact, prepare_artifact
from epub_timing import collect_timing
from heavy import PROFILE_PREFIX, atomic_json, checkpoint_directory, prepare_enrichment
from test_epub_alignment import A, B, window
from test_epub_assets import MATHML, book
from test_heavy import FakeSource
from transcriber.contract import AudioIdentity, Cue, TranscriptWindow
from transcriber.audiobookshelf import Manifest


PROFILE = PROFILE_PREFIX + "auto"


def collected():
    result = collect_timing(book("<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>" + MATHML),
                            [window(A, B)])
    return {**result, "source_id": "home", "item_id": "book", "file_id": "42",
            "audio_revision": "a" * 64, "profile": PROFILE, "duration_ms": 301000}


class ArtifactTests(unittest.TestCase):
    def test_content_addressed_artifact_preserves_evidence_and_original_payloads(self):
        result = collected()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = prepare_artifact(root, result)
            path = root / "enrichment" / (first["artifact_id"] + ".json")
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), first["artifact_id"])
            artifact = json.loads(raw)
            self.assertEqual(artifact["identity"]["epub_sha256"], result["epub_sha256"])
            self.assertEqual(artifact["identity"]["transcript_sha256"], result["transcript_sha256"])
            self.assertEqual(artifact["identity"]["audio_revision"], "a" * 64)
            self.assertFalse(artifact["playback_qualified"])
            self.assertEqual(artifact["summary"]["timed_count"], 1)
            self.assertEqual(artifact["summary"]["untimed_count"], 1)
            self.assertEqual(len(artifact["assets"]), 1)
            self.assertEqual(base64.b64decode(artifact["assets"][0]["payload_base64"]), result["assets"][0]["payload"])
            self.assertIsNone(artifact["occurrences"][1]["evidence"])
            self.assertFalse(first["reused"])
            self.assertTrue(prepare_artifact(root, collected())["reused"])
            self.assertNotIn("assets", first)
            self.assertNotIn("occurrences", first)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_invalid_payload_reference_or_bounds_rejected(self):
        for mutate in (
                lambda result: result["assets"][0].update(sha256="0" * 64),
                lambda result: result["occurrences"][0].update(asset_id="missing"),
                lambda result: result["occurrences"][0]["evidence"].update(latest_ms=31000),
                lambda result: result["occurrences"][0]["evidence"].update(cue_indices=[0, 0]),
                lambda result: result["occurrences"][0].update(ebook_word_position=999),
                lambda result: result.update(timed_count=7),
                lambda result: result.update(playback_qualified=True)):
            result = collected()
            mutate(result)
            with self.assertRaises(EnrichmentError):
                build_artifact(result)

    def test_limits_corruption_and_failed_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for limit in ("MAX_ARTIFACT_BYTES", "MAX_STORE_BYTES", "MAX_STORE_FILES"):
                with patch("epub_enrichment." + limit, 0), self.assertRaises(EnrichmentError):
                    prepare_artifact(root, collected())
            with patch("epub_enrichment.os.replace", side_effect=OSError("write failed")):
                with self.assertRaises(OSError):
                    prepare_artifact(root, collected())
            self.assertEqual(list((root / "enrichment").iterdir()), [])
            first = prepare_artifact(root, collected())
            path = root / "enrichment" / (first["artifact_id"] + ".json")
            path.write_bytes(b"damaged")
            with self.assertRaisesRegex(EnrichmentError, "corrupt"):
                prepare_artifact(root, collected())
            self.assertEqual(path.read_bytes(), b"damaged")


class PipelineTests(unittest.TestCase):
    def test_unified_path_downloads_once_and_commits_only_after_revision_check(self):
        source = FakeSource()

        class Library:
            downloads = 0

            def authorized(self, action):
                return action("token")

            def inspect_companion(self, item, file_id, inspect):
                self.downloads += 1
                return {"item_id": item, "file_id": file_id,
                        **inspect(book("<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>"))}

        library = Library()
        library.source = source
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            root = Path(directory)
            cache = checkpoint_directory(root, source.identity, PROFILE)
            cache.mkdir(parents=True)
            bench = Workbench(library, None, PROFILE, root)
            bench.catalog["book"] = {"id": "book"}
            with self.assertRaisesRegex(ValueError, "Complete local"):
                bench.epub_enrichment("book", "42")
            self.assertEqual(library.downloads, 0)
            atomic_json(cache / "0.json", TranscriptWindow(source.identity, 0, 300000,
                        (Cue(0, 900, A), Cue(1000, 1900, B))).to_json())
            atomic_json(cache / "300000.json", TranscriptWindow(source.identity, 300000, 301000, ()).to_json())
            changed = Manifest(AudioIdentity("home", "book", "b" * 64), source.value.tracks)
            with patch.object(source, "manifest", side_effect=[source.value, changed]):
                with self.assertRaisesRegex(ValueError, "Audio revision changed"):
                    prepare_enrichment(library, PROFILE, "book", "42", root)
            self.assertFalse((root / "enrichment").exists())
            result = bench.epub_enrichment("book", "42")
            self.assertEqual(library.downloads, 2)
            self.assertEqual(result["timed_count"], 1)
            self.assertNotIn("identity", result)
            self.assertFalse(bench.inspecting_epub)
            self.assertEqual(len(list(cache.iterdir())), 2)
            self.assertEqual(len(list((root / "enrichment").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
