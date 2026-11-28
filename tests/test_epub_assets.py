import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from app import Workbench
from epub_assets import AssetError, MATH, extract_assets
from epub_inventory import inspect_epub
from heavy import Library, PROFILE_PREFIX
from test_epub_inventory import CONTAINER, PACKAGE


PNG = b"\x89PNG\r\n\x1a\noriginal-image-data"
MATHML = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi><mo>=</mo><mn>2</mn></math>'
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M 0 0 L 1 1"/></svg>'


def book(body, image=PNG, package=PACKAGE, extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (("mimetype", b"application/epub+zip"),
                            ("META-INF/container.xml", CONTAINER), ("OPS/book.opf", package),
                            ("OPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + '</body></html>'),
                            ("OPS/figure.png", image), *extra):
            archive.writestr(name, value)
    return stream


class VisualTests(unittest.TestCase):
    def test_original_bytes_deduplicate_and_preserve_occurrences(self):
        result = extract_assets(book("<figure><img src='figure.png'/><img src='figure.png'/>"
                                     "<figcaption>Illustration</figcaption></figure>" + MATHML + SVG))
        self.assertEqual(result["raster_count"], 2)
        self.assertEqual(result["mathml_count"], 1)
        self.assertEqual(result["svg_count"], 1)
        self.assertEqual(result["figure_count"], 1)
        self.assertEqual(result["unique_asset_count"], 3)
        self.assertFalse(result["edition_verified"])
        self.assertFalse(result["render_qualified"])
        first, second, math, svg = result["occurrences"]
        self.assertEqual(first["asset_id"], second["asset_id"])
        self.assertEqual(first["node_path"], [0, 0])
        self.assertEqual(second["node_path"], [0, 1])
        self.assertEqual(first["figure_path"], [0])
        self.assertEqual(math["node_path"], [1])
        self.assertEqual(svg["node_path"], [2])
        self.assertEqual(first["document"], "OPS/chapter.xhtml")
        self.assertEqual(first["resource"], "OPS/figure.png")
        assets = {asset["asset_id"]: asset for asset in result["assets"]}
        self.assertEqual(assets[first["asset_id"]]["payload"], PNG)
        self.assertEqual(assets[first["asset_id"]]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(ET.fromstring(assets[math["asset_id"]]["payload"]).tag, MATH + "math")
        self.assertNotIn("start_ms", first)

    def test_original_svg_resource_and_standalone_spine(self):
        package = PACKAGE.replace(b"</manifest>", b'<item id="diagram" href="diagram.svg" media-type="image/svg+xml"/></manifest>')
        package = package.replace(b"</spine>", b'<itemref idref="diagram"/></spine>')
        result = extract_assets(book("<img src='diagram.svg'/>", package=package,
                                     extra=(("OPS/diagram.svg", SVG),)))
        self.assertEqual(result["svg_count"], 2)
        self.assertEqual(result["unique_asset_count"], 1)
        self.assertEqual(result["assets"][0]["payload"], SVG.encode())
        self.assertEqual(result["occurrences"][1]["spine_index"], 1)
        self.assertEqual(result["occurrences"][1]["node_path"], [])

    def test_skips_remote_undeclared_hidden_and_responsive_assets(self):
        result = extract_assets(book("<img src='https://example.test/figure.png'/>"
                                     "<img src='unlisted.png'/><img src='../../other.png'/>"
                                     "<img src='figure.png' srcset='other.png 2x'/>"
                                     "<picture><img src='figure.png'/></picture>"
                                     "<div hidden='hidden'>" + MATHML + "</div><nav>" + SVG + "</nav>",
                                     extra=(("OPS/unlisted.png", PNG),)))
        self.assertEqual(result["occurrence_count"], 0)
        self.assertEqual(result["skipped_count"], 5)
        self.assertEqual(result["skipped"]["unsupported_reference"], 2)
        self.assertEqual(result["skipped"]["unsupported_or_undeclared_resource"], 1)

    def test_limits_and_invalid_payload(self):
        with self.assertRaises(AssetError):
            extract_assets(book("<img src='figure.png'/>", image=b"invalid"))
        for limit, value in (("MAX_ASSET_BYTES", 4), ("MAX_TOTAL_BYTES", 4),
                             ("MAX_DOCUMENT_BYTES", 4), ("MAX_OCCURRENCES", 0), ("MAX_DEPTH", 0)):
            with self.subTest(limit=limit), patch("epub_assets." + limit, value), self.assertRaises(AssetError):
                extract_assets(book("<img src='figure.png'/>"))
        with self.assertRaises(ValueError):
            extract_assets(book("<p>&undefined;</p>"))

    def test_base_overrides_are_rejected_instead_of_resolving_wrong_image(self):
        with self.assertRaisesRegex(AssetError, "base overrides"):
            extract_assets(book("<div xml:base='other/'><img src='figure.png'/></div>"))
        with self.assertRaisesRegex(AssetError, "base overrides"):
            extract_assets(book("<base href='other/'/><img src='figure.png'/>"))
        package = PACKAGE.replace(b"<manifest>", b"<manifest xml:base='other/'>")
        with self.assertRaisesRegex(ValueError, "base overrides"):
            extract_assets(book("", package=package))

    def test_inventory_does_not_expose_resource_map_by_default(self):
        self.assertNotIn("resources", inspect_epub(book("")))
        result = inspect_epub(book(""), include_resources=True)
        self.assertEqual(result["resources"]["OPS/figure.png"], "image/png")

    def test_workbench_only_returns_summary(self):
        library = Library("https://example.test", "home", "token")
        with tempfile.TemporaryDirectory() as directory, patch("app.GpuEngine"):
            bench = Workbench(library, None, PROFILE_PREFIX + "auto", Path(directory))
            with patch.object(library, "epub_assets", return_value=extract_assets(book(MATHML))) as extract:
                with self.assertRaises(ValueError):
                    bench.epub_assets("book", "42")
                extract.assert_not_called()
                bench.catalog["book"] = {"id": "book"}
                result = bench.epub_assets("book", "42")
                self.assertEqual(result["mathml_count"], 1)
                self.assertNotIn("assets", result)
                self.assertNotIn("occurrences", result)
                self.assertFalse(bench.inspecting_epub)


if __name__ == "__main__":
    unittest.main()
