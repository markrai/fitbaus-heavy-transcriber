import io
import json
from pathlib import Path
import tempfile
import unittest

from stem.acquire import store_snapshot
from stem.prioritize import classify_label, prioritize, markdown


def binding(entity, label, formula):
    return {"item": {"value": "http://www.wikidata.org/entity/" + entity},
            "itemLabel": {"value": label}, "formula": {"value": formula}}


class PrioritizationTests(unittest.TestCase):
    def test_label_classification(self):
        cases = [
            ("Q1", "98087154^65536 + 1", "numeric_expression"),
            ("Q1", "−⅔", "numeric_expression"),
            ("Q1", "10^100", "numeric_expression"),
            ("Q1", "Mersenne number", "potentially_named"),
            ("Q1", "de Broglie wavelength", "potentially_named"),
            ("Q1", "Équation", "potentially_named"),
            ("Q1", "Q1234", "unresolved"),
            ("Q1", "−i", "symbolic_or_uncertain"),
            ("Q1", "x=1", "symbolic_or_uncertain"),
            ("P1", "property name", "property"),
        ]
        for entity, label, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(classify_label(entity, label), expected)

    def test_partition_provenance_and_collisions(self):
        rows = [
            binding("Q1", "Energy", "E=mc^2"),
            binding("Q1", " ENERGY ", "E=mc^3"),
            binding("Q2", "Different label", "E=mc^2"),
            binding("Q3", "Named rejection", r"\input{file}"),
            binding("Q4", "98087154^65536 + 1", "x=1"),
            binding("Q5", "Q123", "x=1"),
            binding("Q6", "x=1", "x=1"),
            binding("P1", "property", "x=1"),
        ]
        raw = json.dumps({"results": {"bindings": rows}}).encode()
        with tempfile.TemporaryDirectory() as root:
            manifest = store_snapshot(root, raw, acquisition="local_export")
            path = Path(root) / manifest["sha256"]
            streams = [io.StringIO() for _ in range(3)]
            report = prioritize(path, *streams)
            named, rejected, deferred = [
                [json.loads(line) for line in stream.getvalue().splitlines()] for stream in streams
            ]
            self.assertEqual(report["rows"], 8)
            self.assertEqual(report["named_conversion_outcomes"], {"screened_candidate": 3, "conversion_rejected": 1})
            self.assertEqual(report["named_unique_latex"], 2)
            self.assertEqual(report["named_labels_with_multiple_screened_formulas"], 1)
            self.assertEqual(report["named_entities_with_multiple_screened_formulas"], 1)
            self.assertEqual(report["named_latex_shared_by_multiple_rows"], 1)
            self.assertTrue(named[0]["review_flags"]["label_has_multiple_formulas"])
            self.assertTrue(named[0]["review_flags"]["entity_has_multiple_formulas"])
            self.assertTrue(named[2]["review_flags"]["formula_shared_by_multiple_rows"])
            self.assertFalse(named[2]["review_flags"]["label_has_multiple_formulas"])
            self.assertEqual(rejected[0]["row_index"], 3)
            self.assertEqual(report["deferred_rows"], 4)
            self.assertEqual(sorted(r["row_index"] for r in named + rejected + deferred), list(range(8)))
            self.assertTrue(all(r["status"] == "candidate_only" and r["source_sha256"] == manifest["sha256"]
                                for r in named + rejected + deferred))
            self.assertEqual((path / "snapshot.json").read_bytes(), raw)
            again = [io.StringIO() for _ in range(3)]
            self.assertEqual(report, prioritize(path, *again))
            self.assertEqual([s.getvalue() for s in streams], [s.getvalue() for s in again])
            self.assertIn("No spoken aliases are verified", markdown(report))

    def test_deferred_rows_do_not_require_conversion(self):
        rows = [binding("Q1", "123^456", r"\input{file}")]
        with tempfile.TemporaryDirectory() as root:
            manifest = store_snapshot(root, json.dumps({"results": {"bindings": rows}}).encode(), acquisition="local_export")
            streams = [io.StringIO() for _ in range(3)]
            report = prioritize(Path(root) / manifest["sha256"], *streams)
            self.assertEqual(report["named_conversion_outcomes"], {})
            self.assertEqual(report["deferred_rows"], 1)
            self.assertEqual(streams[0].getvalue(), "")
            self.assertEqual(streams[1].getvalue(), "")


if __name__ == "__main__":
    unittest.main()
