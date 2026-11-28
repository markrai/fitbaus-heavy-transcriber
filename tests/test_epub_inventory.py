from contextlib import contextmanager
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from app import Workbench
from companions import Companion
from epub_inventory import EpubError, inspect_epub
from heavy import Library, PROFILE_PREFIX, SourceError


CONTAINER = b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
PACKAGE = b'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Example</dc:title></metadata>
<manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
<item id="picture" href="figure.png" media-type="image/png"/></manifest>
<spine><itemref idref="chapter"/></spine></package>'''


def epub(package=PACKAGE, container=CONTAINER, extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in (("mimetype", b"application/epub+zip"),
                           ("META-INF/container.xml", container), ("OPS/book.opf", package),
                           ("OPS/chapter.xhtml", b"<html/>"), ("OPS/figure.png", b"image"), *extra):
            archive.writestr(name, data)
    return stream.getvalue()


class InventoryTests(unittest.TestCase):
    def test_inventory_and_provenance(self):
        data = epub()
        result = inspect_epub(io.BytesIO(data))
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["size"], len(data))
        self.assertEqual(result["title"], "Example")
        self.assertFalse(result["edition_verified"])
        self.assertEqual(result["manifest_count"], 2)
        self.assertEqual(result["image_count"], 1)
        self.assertEqual(result["spine"], [{"path": "OPS/chapter.xhtml",
                                            "media_type": "application/xhtml+xml", "linear": True}])

    def test_reject_invalid_archive_and_unsafe_members(self):
        for data in (b"not an epub", epub(extra=(("../outside", b"x"),)),
                     epub(extra=(("META-INF/encryption.xml", b"x"),)),
                     epub(extra=(("OPS/../outside", b"x"),))):
            with self.subTest(data=data[:20]), self.assertRaises(EpubError):
                inspect_epub(io.BytesIO(data))

    def test_reject_external_missing_and_traversal_references(self):
        for href in (b"https://example.test/chapter.xhtml", b"missing.xhtml",
                     b"../../outside.xhtml", b"%2e%2e/%2e%2e/outside.xhtml"):
            with self.subTest(href=href), self.assertRaises(EpubError):
                inspect_epub(io.BytesIO(epub(PACKAGE.replace(b"chapter.xhtml", href))))
        with self.assertRaises(EpubError):
            inspect_epub(io.BytesIO(epub(PACKAGE.replace(b'idref="chapter"', b'idref="missing"'))))

    def test_reject_dtd_and_size_limits(self):
        data = epub(b'<!DOCTYPE package [<!ENTITY x "boom">]>' + PACKAGE)
        with self.assertRaises(EpubError):
            inspect_epub(io.BytesIO(data))
        for limit, value in (("MAX_EPUB_BYTES", 8), ("MAX_MEMBERS", 2),
                             ("MAX_EXPANDED_BYTES", 10), ("MAX_XML_BYTES", 10)):
            with patch("epub_inventory." + limit, value), self.assertRaises(EpubError):
                inspect_epub(io.BytesIO(epub()))


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.data = epub()
        self.file = Companion("42", "Book.epub", "epub", len(self.data), 1, "primary")
        self.library = Library("https://example.test", "home", "token")
        self.requests = []

    @contextmanager
    def response(self, path, token):
        self.requests.append((path, token))
        yield type("Response", (), {"headers": {"Content-Length": str(len(self.data))}})()

    def test_acquire_exact_file_and_revalidate(self):
        with patch.object(self.library, "companions", return_value=(self.file,)) as discover, \
                patch.object(self.library.source, "_get", side_effect=self.response), \
                patch.object(self.library.source, "_chunks", return_value=[self.data]):
            result = self.library.epub_inventory("book", "42")
        self.assertEqual(discover.call_count, 2)
        self.assertEqual(self.requests, [("/api/items/book/file/42", "token")])
        self.assertEqual(result["file_id"], "42")

    def test_reject_unknown_file_before_download(self):
        with patch.object(self.library, "companions", return_value=(self.file,)), \
                patch.object(self.library.source, "_get") as get:
            for file_id in ("43", "../42"):
                with self.assertRaises(ValueError):
                    self.library.epub_inventory("book", file_id)
            get.assert_not_called()

    def test_reject_stale_and_truncated_download(self):
        changed = Companion("42", "Book.epub", "epub", len(self.data), 2, "primary")
        for chunks, current, code in (([self.data], changed, "stale_revision"),
                                      ([self.data[:-1]], self.file, "incomplete_epub")):
            with patch.object(self.library, "companions", side_effect=[(self.file,), (current,)]), \
                    patch.object(self.library.source, "_get", side_effect=self.response), \
                    patch.object(self.library.source, "_chunks", return_value=chunks):
                with self.assertRaises(SourceError) as failure:
                    self.library.epub_inventory("book", "42")
                self.assertEqual(failure.exception.code, code)

    def test_workbench_gates_and_redacts(self):
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(self.library, None, PROFILE_PREFIX + "auto", Path(directory))
            with patch.object(self.library, "epub_inventory", return_value={"spine": ["private"], "size": 10}) as inspect:
                with self.assertRaises(ValueError):
                    bench.epub_inventory("book", "42")
                bench.catalog["book"] = {"id": "book"}
                bench.running = True
                with self.assertRaises(ValueError):
                    bench.epub_inventory("book", "42")
                inspect.assert_not_called()
                bench.running = False
                self.assertEqual(bench.epub_inventory("book", "42"), {"size": 10})
                self.assertFalse(bench.inspecting_epub)
                inspect.side_effect = ValueError("bad ebook")
                with self.assertRaises(ValueError):
                    bench.epub_inventory("book", "42")
                self.assertFalse(bench.inspecting_epub)


if __name__ == "__main__":
    unittest.main()
