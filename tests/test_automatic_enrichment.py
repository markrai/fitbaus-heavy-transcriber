from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import Workbench
from companions import discover
from heavy import Library, PROFILE_PREFIX
from test_companions import item


class AutomaticEnrichmentTests(unittest.TestCase):
    def test_default_batch_runs_enrichment_after_success(self):
        library = Library("https://example.test", "home", "token")
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(library, None, PROFILE_PREFIX + "auto", Path(directory))
            bench.catalog["book"] = {"title": "Measurement"}
            bench.jobs["book"] = {"state": "Queued"}
            with patch.object(library, "companions", return_value=discover(item(), "book")), \
                    patch("app.process_book", side_effect=lambda *args: args[-1]("Imported", 1, 1)), \
                    patch("app.prepare_enrichment", return_value={"artifact_id": "a" * 64}) as prepare, \
                    patch("app.prepare_delivery", return_value={"artifact_id": "b" * 64}) as delivery:
                bench.run(["book"])
                prepare.assert_called_once_with(library, bench.profile, "book", "42", bench.root)
                delivery.assert_called_once_with(bench.root, "a" * 64)
            self.assertEqual(bench.jobs["book"]["state"], "Imported")
            self.assertEqual(bench.jobs["book"]["enrichment_state"], "Prepared locally")

    def test_discovery_failure_does_not_block_audio_and_opt_out_skips_discovery(self):
        library = Library("https://example.test", "home", "token")
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(library, None, PROFILE_PREFIX + "auto", Path(directory))
            for enabled in (True, False):
                bench.jobs["book"] = {"state": "Queued"}
                with patch.object(library, "companions", side_effect=RuntimeError("private path")) as lookup, \
                        patch("app.process_book", side_effect=lambda *args: args[-1]("Imported", 1, 1)), \
                        patch("app.prepare_enrichment") as prepare:
                    bench.run(["book"], enabled)
                    self.assertEqual(lookup.call_count, int(enabled))
                    prepare.assert_not_called()
                self.assertEqual(bench.jobs["book"]["state"], "Imported")
                if enabled:
                    self.assertEqual(bench.jobs["book"]["enrichment_state"], "Failed")
                    self.assertNotIn("private path", bench.jobs["book"]["enrichment_error"])

    def test_render_failure_preserves_import_and_enrichment_artifact(self):
        library = Library("https://example.test", "home", "token")
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(library, None, PROFILE_PREFIX + "auto", Path(directory))
            bench.jobs["book"] = {"state": "Queued"}
            with patch.object(library, "companions", return_value=discover(item(), "book")), \
                    patch("app.process_book", side_effect=lambda *args: args[-1]("Imported", 1, 1)), \
                    patch("app.prepare_enrichment", return_value={"artifact_id": "a" * 64}), \
                    patch("app.prepare_delivery", side_effect=RuntimeError("renderer failure")):
                bench.run(["book"])
            self.assertEqual(bench.jobs["book"]["state"], "Imported")
            self.assertEqual(bench.jobs["book"]["enrichment_state"], "Failed")
            self.assertEqual(bench.jobs["book"]["enrichment_artifact"]["artifact_id"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
