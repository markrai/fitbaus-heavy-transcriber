import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image

from epub_delivery import DeliveryError, normalize_raster, png_dimensions, prepare_delivery
from epub_enrichment import prepare_artifact
from epub_timing import collect_timing
from test_epub_alignment import A, B, window
from test_epub_assets import MATHML, book
from test_epub_enrichment import PROFILE


def image_bytes(fmt="PNG", size=(32, 16), **options):
    stream = io.BytesIO()
    Image.new("RGB", size, "red").save(stream, format=fmt, **options)
    return stream.getvalue()


def source():
    data = collect_timing(book("<p>" + A + "</p><img src='figure.png'/>" + MATHML +
                               "<p>" + B + "</p><img src='figure.png'/>",
                               image=image_bytes()), [window(A, B)])
    return {**data, "source_id": "home", "item_id": "book", "file_id": "42",
            "audio_revision": "a" * 64, "profile": PROFILE, "duration_ms": 301000}


class DeliveryTests(unittest.TestCase):
    def test_real_worker_formats_and_resize(self):
        for fmt, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"),
                          ("GIF", "image/gif"), ("WEBP", "image/webp")):
            with self.subTest(fmt=fmt):
                output, reason = normalize_raster({"media_type": mime, "payload": image_bytes(fmt, (1200, 300))})
                self.assertIsNone(reason)
                data = base64.b64decode(output["payload_base64"])
                self.assertEqual(png_dimensions(data), (1024, 256))
                self.assertEqual(output["png_sha256"], hashlib.sha256(data).hexdigest())
                with Image.open(io.BytesIO(data)) as result:
                    result.load()
                    self.assertEqual(result.mode, "RGBA")
                    self.assertEqual(result.info, {})

    def test_reject_corrupt_mismatched_and_animated_input(self):
        stream = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(stream, format="GIF", save_all=True,
            append_images=[Image.new("RGB", (4, 4), "blue")], duration=100)
        for mime, payload in (("image/png", b"bad"), ("image/jpeg", image_bytes()),
                              ("image/gif", stream.getvalue())):
            output, reason = normalize_raster({"media_type": mime, "payload": payload})
            self.assertIsNone(output)
            self.assertEqual(reason, "unsupported_or_invalid_raster")

    def test_metadata_removed_and_timeout_withholds(self):
        from PIL.PngImagePlugin import PngInfo

        metadata = PngInfo()
        metadata.add_text("private", "discard this")
        output, reason = normalize_raster({"media_type": "image/png",
                                          "payload": image_bytes(pnginfo=metadata)})
        self.assertIsNone(reason)
        with Image.open(io.BytesIO(base64.b64decode(output["payload_base64"]))) as image:
            self.assertEqual(image.info, {})
        with patch("epub_delivery.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 10)):
            self.assertEqual(normalize_raster({"media_type": "image/png", "payload": b"x"}),
                             (None, "decode_timeout"))

    def test_png_validator_rejects_trailing_and_corrupt_data(self):
        output, _ = normalize_raster({"media_type": "image/png", "payload": image_bytes()})
        raw = base64.b64decode(output["payload_base64"])
        for invalid in (raw + b"x", raw[:-1], raw[:40] + bytes([raw[40] ^ 1]) + raw[41:]):
            with self.assertRaises(DeliveryError):
                png_dimensions(invalid)

    def test_local_candidate_excludes_markup_and_untimed_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = prepare_artifact(root, source())
            result = prepare_delivery(root, original["artifact_id"])
            path = root / "delivery" / (result["artifact_id"] + ".json")
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), result["artifact_id"])
            candidate = json.loads(raw)
            self.assertEqual(candidate["source_artifact_id"], original["artifact_id"])
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(result["unique_png_count"], 2)
            self.assertEqual(result["withheld_reasons"], {"no_timing_evidence": 1})
            self.assertFalse(candidate["playback_qualified"])
            self.assertNotIn("document", candidate["occurrences"][0])
            self.assertNotIn("assets", candidate)
            self.assertTrue(prepare_delivery(root, original["artifact_id"])["reused"])
            source_path = root / "enrichment" / (original["artifact_id"] + ".json")
            source_path.write_bytes(b"changed")
            with self.assertRaisesRegex(DeliveryError, "digest"):
                prepare_delivery(root, original["artifact_id"])

    def test_failed_worker_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = prepare_artifact(root, source())
            with patch("epub_delivery.normalize_raster", side_effect=DeliveryError("worker failed")):
                with self.assertRaises(DeliveryError):
                    prepare_delivery(root, original["artifact_id"])
            self.assertFalse((root / "delivery").exists())


if __name__ == "__main__":
    unittest.main()
