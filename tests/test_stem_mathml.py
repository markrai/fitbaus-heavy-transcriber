import io
import json
from pathlib import Path
import tempfile
import unittest

from stem.acquire import store_snapshot
from stem.convert import convert_snapshot
from stem.mathml import ConversionError, convert_mathml


def math(body):
    return '<math xmlns="http://www.w3.org/1998/Math/MathML">' + body + '</math>'


class MathMLTests(unittest.TestCase):
    def test_equation_and_power(self):
        self.assertEqual(convert_mathml(math(
            "<mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup>"
        )), "E=m{c}^{2}")

    def test_fraction_and_greek(self):
        self.assertEqual(convert_mathml(math(
            '<mfrac><mrow><mstyle displaystyle="true" scriptlevel="0"><mi>σ</mi></mstyle></mrow>'
            '<mrow><mi>ρ</mi></mrow></mfrac>'
        )), r"\frac{\sigma}{\rho}")

    def test_grouping_and_scripts(self):
        self.assertEqual(convert_mathml(math(
            "<msubsup><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mi>i</mi><mn>2</mn></msubsup>"
        )), "{a+b}_{i}^{2}")
        self.assertEqual(convert_mathml(math(
            "<msqrt><mi>x</mi><mo>+</mo><mn>1</mn></msqrt>"
        )), r"\sqrt{x+1}")

    def test_command_boundaries_and_invisible_times(self):
        self.assertEqual(convert_mathml(math("<mi>π</mi><mi>r</mi>")), r"\pi r")
        self.assertEqual(convert_mathml(math("<mn>2</mn><mo>&#x2062;</mo><mi>x</mi>")), r"2\cdot x")

    def test_rejects_unsupported_or_semantically_significant_markup(self):
        cases = (
            "<mfrac><mi>x</mi></mfrac>",
            "<mi mathvariant='bold'>x</mi>",
            "<mfrac linethickness='0'><mi>x</mi><mi>y</mi></mfrac>",
            "<mstyle scriptlevel='1'><mi>x</mi></mstyle>",
            "<mtable><mtr><mtd><mi>x</mi></mtd></mtr></mtable>",
            "<mroot><mi>x</mi><mn>3</mn></mroot>",
            "<mi>xy</mi>", "<mo>&#x2061;</mo>",
            "<mrow>unexpected<mi>x</mi></mrow>",
            "<mi xmlns='urn:foreign'>x</mi>",
            "<mrow><mi>x</mi></mrow><mspace width='1em'/>",
            "<mo>&#xFFFD;</mo>", "<mi/>",
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ConversionError):
                convert_mathml(math(case))

    def test_xml_security_and_bounds(self):
        for source in (
            '<!DOCTYPE math [<!ENTITY x "hello">]>' + math("<mi>&x;</mi>"),
            "<?xml version='1.0'?>" + math("<mi>x</mi>"),
            "<math><mi>x</mi></math>",
            math("<mi>x</mi>" * 1025),
            math("<mrow>" * 33 + "<mi>x</mi>" + "</mrow>" * 33),
            math("<mi>" + "x" * 65536 + "</mi>"),
        ):
            with self.subTest(source=source[:80]), self.assertRaises(ConversionError):
                convert_mathml(source)

    def test_snapshot_conversion_is_review_only(self):
        sources = [math("<mi>x</mi><mo>=</mo><mn>1</mn>"),
                   math("<mi>x</mi><mo>=</mo><mn>1</mn>"),
                   math("<mtext>unknown</mtext>"), "x=2"]
        rows = [{"item": {"value": f"http://www.wikidata.org/entity/Q{i+1}"},
                 "itemLabel": {"value": "Example"}, "formula": {"value": source}}
                for i, source in enumerate(sources)]
        with tempfile.TemporaryDirectory() as temp:
            raw = json.dumps({"results": {"bindings": rows}}).encode()
            manifest = store_snapshot(temp, raw, acquisition="local_export")
            path = Path(temp) / manifest["sha256"]
            out = io.StringIO()
            report = convert_snapshot(path, out)
            second = io.StringIO()
            self.assertEqual(report, convert_snapshot(path, second))
            self.assertEqual(out.getvalue(), second.getvalue())
            self.assertEqual(report["representation_rows"], {"mathml": 3, "latex_candidate": 1})
            self.assertEqual(report["candidate_rows_written"], 3)
            self.assertEqual(report["unique_candidate_latex"], 2)
            self.assertEqual(report["row_outcomes"]["unsupported_element:mtext"], 1)
            self.assertEqual(report["spoken_aliases_verified"], 0)
            candidates = [json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual([c["row_index"] for c in candidates], [0, 1, 3])
            self.assertTrue(all(c["status"] == "candidate_only" for c in candidates))
            self.assertEqual((path / "snapshot.json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
