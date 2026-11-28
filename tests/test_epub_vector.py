import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from epub_delivery import normalize_visual, png_dimensions
from epub_vector import VectorRejected, mathml, svg


MATH = b'<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><msup><mi>x</mi><mn>2</mn></msup><mn>3</mn></mfrac></math>'
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 600"><rect width="1200" height="600" fill="red"/><path d="M 0 0 L 1200 600" stroke="black"/></svg>'


class VectorTests(unittest.TestCase):
    def test_real_mathml_and_svg_produce_visible_clean_png(self):
        for kind, raw in (("application/mathml+xml", MATH), ("image/svg+xml", SVG)):
            with self.subTest(kind=kind):
                result, reason = normalize_visual({"media_type": kind, "payload": raw})
                self.assertIsNone(reason)
                data = base64.b64decode(result["payload_base64"])
                width, height = png_dimensions(data)
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
                    self.assertEqual(image.info, {})
                    self.assertGreater(len(image.getcolors(width * height)), 1)
                    self.assertEqual(image.getextrema()[3], (255, 255))

    def test_reject_active_or_unsupported_svg_without_worker(self):
        for fragment in (b'<script/>', b'<image href="https://example.test/x"/>',
                         b'<use href="#x"/>', b'<text>label</text>',
                         b'<rect width="1" height="1" fill="url(#x)"/>',
                         b'<path d="M 1e999 0"/>', b'<rect onclick="evil()" width="1"/>'):
            raw = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' + fragment + b'</svg>'
            with self.subTest(fragment=fragment), patch("epub_vector.run_worker") as worker:
                result, reason = normalize_visual({"media_type": "image/svg+xml", "payload": raw})
                self.assertIsNone(result)
                self.assertTrue(reason)
                worker.assert_not_called()

    def test_reject_active_or_invalid_mathml_without_worker(self):
        for fragment in (b'<mi href="https://example.test">x</mi>', b'<mfrac><mi>x</mi></mfrac>',
                         b'<semantics><mi>x</mi><annotation-xml/></semantics>',
                         b'<mi><script/></mi>', b'<mi style="color:red">x</mi>'):
            raw = b'<math xmlns="http://www.w3.org/1998/Math/MathML">' + fragment + b'</math>'
            with self.subTest(fragment=fragment), patch("epub_vector.run_worker") as worker:
                result, reason = normalize_visual({"media_type": "application/mathml+xml", "payload": raw})
                self.assertIsNone(result)
                self.assertTrue(reason)
                worker.assert_not_called()

    def test_plain_annotation_is_not_sent_to_renderer(self):
        raw = b'<math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mi>x</mi><annotation encoding="application/x-tex">x</annotation></semantics></math>'
        clean = mathml(raw)
        self.assertNotIn(b"annotation", clean)
        self.assertIn(b"<mrow><mi>x</mi></mrow>", clean)

    def test_invalid_path_geometry_is_rejected(self):
        for path in (b"M 1", b"M 0 0 L", b"M 0 0 X 1 2", b"M 0 0 A 1 1 0 2 0 1 1"):
            with self.subTest(path=path), self.assertRaises(VectorRejected):
                svg(SVG.replace(b"M 0 0 L 1200 600", path))

    def test_generated_svg_revalidated(self):
        with patch("epub_vector.run_worker", return_value=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><script/></svg>') as worker:
            result, reason = normalize_visual({"media_type": "application/mathml+xml", "payload": MATH})
            self.assertIsNone(result)
            self.assertEqual(reason, "svg_element")
            self.assertEqual(worker.call_count, 1)

    def test_limits_and_namespace(self):
        for raw in (b'<!DOCTYPE math><math/>', b'<math><mi>x</mi></math>'):
            with self.assertRaises(VectorRejected):
                mathml(raw)
        with patch("epub_vector.MAX_NODES", 1), self.assertRaises(VectorRejected):
            mathml(MATH)
        with self.assertRaises(VectorRejected):
            svg(SVG.replace(b"0 0 1200 600", b"0 0 0 600"))


if __name__ == "__main__":
    unittest.main()
