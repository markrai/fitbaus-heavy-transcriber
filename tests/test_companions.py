import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import Workbench
from companions import discover
from heavy import Library, PROFILE_PREFIX


def file(ino, filename, supplementary=None):
    return {"ino": ino, "fileType": "ebook", "isSupplementary": supplementary,
            "metadata": {"filename": filename, "ext": "." + filename.rsplit(".", 1)[-1],
                         "size": 1234, "mtimeMs": 123.5, "path": "/private/server/path"}}


def item():
    primary = file("42", "Book.epub", False)
    return {"id": "book", "mediaType": "book", "media": {"ebookFile": primary},
            "libraryFiles": [primary, file("43", "Figures.PDF", True),
                             {"ino": "44", "fileType": "audio", "metadata": {"ext": ".m4b"}}]}


class CompanionTests(unittest.TestCase):
    def test_primary_and_supplementary_deduplicate_and_redact(self):
        rows = discover(item(), "book")
        self.assertEqual([(r.file_id, r.format, r.role) for r in rows],
                         [("42", "epub", "primary"), ("43", "pdf", "supplementary")])
        self.assertEqual(set(rows[0].public()), {"file_id", "filename", "format", "size", "role"})
        self.assertNotIn("private", str(rows[0].public()))

    def test_supplementary_only_and_empty(self):
        data = item()
        data["media"]["ebookFile"] = None
        data["libraryFiles"].pop(0)
        self.assertEqual([r.file_id for r in discover(data, "book")], ["43"])
        data["libraryFiles"] = []
        self.assertEqual(discover(data, "book"), ())

    def test_primary_only(self):
        data = item()
        data["libraryFiles"] = []
        self.assertEqual([r.file_id for r in discover(data, "book")], ["42"])

    def test_invalid_identity_duplicate_conflict_and_path(self):
        data = item()
        with self.assertRaises(ValueError):
            discover(data, "other")
        duplicate = copy.deepcopy(data)
        duplicate["libraryFiles"].append(duplicate["libraryFiles"][1])
        with self.assertRaises(ValueError):
            discover(duplicate, "book")
        conflict = copy.deepcopy(data)
        conflict["media"]["ebookFile"] = copy.deepcopy(conflict["media"]["ebookFile"])
        conflict["media"]["ebookFile"]["metadata"]["size"] = 9
        with self.assertRaises(ValueError):
            discover(conflict, "book")
        for key, value in (("ino", "../42"), ("ino", "42?download=1")):
            bad = item()
            bad["libraryFiles"][1][key] = value
            with self.assertRaises(ValueError):
                discover(bad, "book")
        bad = item()
        bad["libraryFiles"][1]["metadata"]["filename"] = "../Figures.PDF"
        with self.assertRaises(ValueError):
            discover(bad, "book")

    def test_library_fetches_only_expanded_item(self):
        library = Library("https://example.test", "home", "token")
        with patch.object(library, "get_json", return_value=item()) as get:
            self.assertEqual(len(library.companions("book")), 2)
            get.assert_called_once_with("/api/items/book?expanded=1")
            with self.assertRaises(ValueError):
                library.companions("../book")
            self.assertEqual(get.call_count, 1)

    def test_workbench_requires_known_book_and_fetches_on_demand(self):
        library = Library("https://example.test", "home", "token")
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(library, None, PROFILE_PREFIX + "auto", Path(directory))
            with patch.object(library, "companions", return_value=discover(item(), "book")) as lookup:
                with self.assertRaises(ValueError):
                    bench.companions("book")
                lookup.assert_not_called()
                bench.catalog["book"] = {"id": "book"}
                result = bench.companions("book")
                lookup.assert_called_once_with("book")
                self.assertEqual(result["item_id"], "book")
                self.assertEqual(len(result["files"]), 2)


if __name__ == "__main__":
    unittest.main()
