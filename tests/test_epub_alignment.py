import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from epub_alignment import AlignmentError, Section, match_anchors, preview, words
from epub_inventory import EpubError
from heavy import PROFILE_PREFIX, checkpoint_directory, preview_alignment, atomic_json
from test_epub_inventory import CONTAINER, PACKAGE
from test_heavy import FakeSource
from transcriber.contract import Cue, TranscriptWindow


A = "a bright morning carried the scent of fresh rain"
B = "the small telescope revealed a distant spiral galaxy"
C = "another entirely separate passage describes the ancient river"


def window(*texts):
    return {"cues": [{"start_ms": index * 1000, "end_ms": index * 1000 + 900, "text": text}
                     for index, text in enumerate(texts)]}


def book(body):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (("mimetype", b"application/epub+zip"),
                            ("META-INF/container.xml", CONTAINER), ("OPS/book.opf", PACKAGE),
                            ("OPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + '</body></html>'),
                            ("OPS/figure.png", b"image")):
            archive.writestr(name, value)
    return stream


class AlignmentTests(unittest.TestCase):
    def test_preview_preserves_cue_times_and_source_coordinates(self):
        result = preview(book("<p>" + A.upper() + "</p><p>" + B + "</p>"), [window(A, B, "short")])
        self.assertEqual(result["matched_cue_count"], 2)
        self.assertEqual(result["eligible_cue_count"], 2)
        self.assertEqual(result["cue_count"], 3)
        self.assertFalse(result["edition_verified"])
        self.assertEqual(result["anchors"][1]["start_ms"], 1000)
        self.assertEqual(result["anchors"][1]["end_ms"], 1900)
        self.assertEqual(result["anchors"][1]["ebook_word_start"], len(words(A)))
        self.assertEqual(result["anchors"][1]["path"], "OPS/chapter.xhtml")
        self.assertEqual(len(result["transcript_sha256"]), 64)

    def test_repeated_ebook_or_narration_is_not_anchored(self):
        for section, narration in ((A + " " + A, (A,)), (A, (A, A))):
            with self.subTest(section=section, narration=narration):
                result = match_anchors([Section(0, "a", words(section))], [window(*narration)])
                self.assertEqual(result["matched_cue_count"], 0)

    def test_reversed_order_rejects_both_and_preserves_unrelated_anchor(self):
        result = match_anchors([Section(0, "a", words(A + " " + B + " " + C))], [window(B, A, C)])
        self.assertEqual(result["conflicting_cue_count"], 2)
        self.assertEqual([a["cue_index"] for a in result["anchors"]], [2])

    def test_no_cross_section_anchors(self):
        tokens = words(A)
        result = match_anchors([Section(0, "a", tokens[:4]), Section(1, "b", tokens[4:])], [window(A)])
        self.assertEqual(result["matched_cue_count"], 0)

    def test_excluded_content_and_inline_text(self):
        result = preview(book("<nav>" + A + "</nav><p hidden='hidden'>" + A +
                              "</p><figure>" + A + "</figure><p>the small tele<em>scope</em> revealed a distant spiral galaxy</p>"),
                         [window(A, B)])
        self.assertEqual(result["matched_cue_count"], 1)
        self.assertEqual(result["anchors"][0]["cue_index"], 1)

    def test_unrelated_book_and_limits(self):
        self.assertEqual(preview(book("<p>" + A + "</p>"), [window(B)])["matched_cue_count"], 0)
        with patch("epub_alignment.MAX_WORDS", 3), self.assertRaises(AlignmentError):
            preview(book("<p>" + A + "</p>"), [window(A)])
        with self.assertRaises(EpubError):
            preview(book("<p>&undefined;</p>"), [window(A)])


class LocalCheckpointTests(unittest.TestCase):
    def test_uses_only_current_complete_checkpoint_set(self):
        source = FakeSource()
        profile = PROFILE_PREFIX + "auto"

        class Library:
            def authorized(self, action):
                return action("token")

            def inspect_companion(self, item, file_id, inspect):
                self.downloads += 1
                return {"item_id": item, "file_id": file_id, **inspect(book("<p>" + A + "</p>"))}

        library = Library()
        library.source = source
        library.downloads = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = checkpoint_directory(root, source.identity, profile)
            cache.mkdir(parents=True)
            with self.assertRaisesRegex(AlignmentError, "Complete local"):
                preview_alignment(library, profile, "book", "42", root)
            self.assertEqual(library.downloads, 0)
            atomic_json(cache / "0.json", TranscriptWindow(source.identity, 0, 300000,
                        (Cue(0, 1000, A),)).to_json())
            atomic_json(cache / "300000.json", TranscriptWindow(source.identity, 300000, 301000, ()).to_json())
            result = preview_alignment(library, profile, "book", "42", root)
            self.assertEqual(result["audio_revision"], source.identity.audio_revision)
            self.assertEqual(result["matched_cue_count"], 1)
            self.assertEqual(library.downloads, 1)
            self.assertEqual(len(list(cache.iterdir())), 2)
            atomic_json(cache / "300000.json", {})
            with self.assertRaisesRegex(AlignmentError, "checkpoint is invalid"):
                preview_alignment(library, profile, "book", "42", root)


if __name__ == "__main__":
    unittest.main()
