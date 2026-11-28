from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from app import Workbench
from epub_alignment import Section, body_projection, words, match_anchors
from epub_timing import associate, preview_timing
from heavy import PROFILE_PREFIX, atomic_json, checkpoint_directory
from test_epub_alignment import A, B, C, window
from test_epub_assets import MATHML, book
from test_heavy import FakeSource
from transcriber.contract import Cue, TranscriptWindow


class TimingTests(unittest.TestCase):
    def test_two_sided_figure_and_inline_asset_share_exact_coordinates(self):
        result = preview_timing(book("<p>" + A + "</p><figure><img src='figure.png'/>"
                                     "<figcaption>ignored caption</figcaption></figure>" +
                                     MATHML + "<p>" + B + "</p>"), [window(A, B)])
        self.assertEqual(result["timed_count"], 2)
        self.assertEqual(result["untimed_count"], 0)
        for row in result["occurrences"]:
            self.assertEqual(row["ebook_word_position"], len(words(A)))
            self.assertEqual(row["evidence"]["method"], "between_adjacent_exact_cues")
            self.assertEqual(row["evidence"]["earliest_ms"], 0)
            self.assertEqual(row["evidence"]["latest_ms"], 1900)
            self.assertEqual(row["evidence"]["cue_indices"], [0, 1])
        self.assertFalse(result["playback_qualified"])
        self.assertNotIn("assets", result)

    def test_inside_exact_cue_requires_words_on_both_sides(self):
        left, right = " ".join(words(A)[:4]), " ".join(words(A)[4:])
        result = preview_timing(book("<p>" + left + MATHML + right + "</p>"), [window(A)])
        self.assertEqual(result["timed_count"], 1)
        row = result["occurrences"][0]
        self.assertEqual(row["evidence"]["method"], "within_exact_cue")
        self.assertEqual(row["evidence"]["latest_ms"], 900)
        result = preview_timing(book("<p>a" + MATHML + " bright morning carried the scent of fresh rain</p>"),
                                [window(A)])
        self.assertEqual(result["untimed_reasons"], {"weak_inside_anchor": 1})

    def test_unmatched_one_sided_distant_and_nonadjacent(self):
        for body, narration, reason in (
                (MATHML + "<p>" + A + "</p>", (A,), "missing_two_sided_anchor"),
                ("<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>", (C,), "missing_two_sided_anchor"),
                ("<p>" + A + "</p>" + "<p>" + "gap " * 25 + "</p>" + MATHML + "<p>" + B + "</p>",
                 (A, B), "distant_anchor"),
                ("<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>", (A, C, B), "nonadjacent_cues")):
            with self.subTest(reason=reason):
                result = preview_timing(book(body), [window(*narration)])
                self.assertEqual(result["timed_count"], 0)
                self.assertEqual(result["untimed_reasons"], {reason: 1})

    def test_wide_interval_and_reversed_anchors_abstain(self):
        body = "<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>"
        data = window(A, B)
        data["cues"][1].update(start_ms=40000, end_ms=41000)
        result = preview_timing(book(body), [data])
        self.assertEqual(result["untimed_reasons"], {"wide_time_interval": 1})
        self.assertEqual(preview_timing(book(body), [window(B, A)])["timed_count"], 0)

    def test_excluded_ancestor_and_split_word_abstain(self):
        body = "<p>" + A + "</p><aside>" + MATHML + "</aside><p>" + B + "</p>"
        self.assertEqual(preview_timing(book(body), [window(A, B)])["untimed_reasons"],
                         {"no_text_coordinate": 1})
        root = ET.fromstring('<body xmlns="http://www.w3.org/1999/xhtml">tele<img/>scope</body>')
        tokens, positions = body_projection(root, [(0,)])
        self.assertEqual(tokens, ("telescope",))
        self.assertEqual(positions, {})

    def test_never_borrows_evidence_from_another_spine_entry(self):
        sections = [Section(0, "first", words(A), {(0,): len(words(A))}),
                    Section(1, "second", words(B))]
        alignment = match_anchors(sections, [window(A, B)])
        catalogue = {"occurrences": [{"spine_index": 0, "document": "first",
                                      "node_path": [0], "figure_path": None, "asset_id": "asset"}]}
        result = associate(catalogue, sections, alignment)
        self.assertEqual(result["timed_count"], 0)
        self.assertEqual(result["untimed_reasons"], {"missing_two_sided_anchor": 1})

    def test_repeated_assets_keep_independent_evidence(self):
        body = "<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>" + MATHML
        result = preview_timing(book(body), [window(A, B)])
        self.assertEqual(result["unique_asset_count"], 1)
        self.assertEqual(result["timed_count"], 1)
        self.assertEqual(result["untimed_count"], 1)
        self.assertEqual(result["occurrences"][0]["asset_id"], result["occurrences"][1]["asset_id"])

    def test_retained_path_and_browser_redaction(self):
        source = FakeSource()
        profile = PROFILE_PREFIX + "auto"
        class Library:
            def authorized(self, action):
                return action("token")

            def inspect_companion(self, item, file_id, inspect):
                self.downloads += 1
                return {"item_id": item, "file_id": file_id,
                        **inspect(book("<p>" + A + "</p>" + MATHML + "<p>" + B + "</p>"))}

        library = Library()
        library.source = source
        library.downloads = 0
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            root = Path(directory)
            cache = checkpoint_directory(root, source.identity, profile)
            cache.mkdir(parents=True)
            atomic_json(cache / "0.json", TranscriptWindow(source.identity, 0, 300000,
                        (Cue(0, 900, A), Cue(1000, 1900, B))).to_json())
            atomic_json(cache / "300000.json", TranscriptWindow(source.identity, 300000, 301000, ()).to_json())
            bench = Workbench(library, None, profile, root)
            bench.catalog["book"] = {"id": "book"}
            result = bench.epub_timing("book", "42")
            self.assertEqual(result["timed_count"], 1)
            self.assertEqual(result["audio_revision"], source.identity.audio_revision)
            self.assertNotIn("occurrences", result)
            self.assertEqual(library.downloads, 1)
            self.assertFalse(bench.inspecting_epub)
            self.assertEqual(len(list(cache.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
