import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stem.analyze import analyze, markdown
from stem.acquire import store_snapshot


def binding(entity, label, formula):
    return {"item": {"value": "http://www.wikidata.org/entity/" + entity},
            "itemLabel": {"value": label}, "formula": {"value": formula}}


class StemAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def snapshot(self, rows):
        raw = json.dumps({"results": {"bindings": rows}}).encode()
        manifest = store_snapshot(self.root, raw, acquisition="local_export")
        return self.root / manifest["sha256"]

    def test_counts_exact_duplicates_and_collisions(self):
        first = binding("Q1", "Energy", "E=mc^2")
        path = self.snapshot([first, first, binding("Q2", "energy", "E=mc^3"),
                              binding("Q1", "Energy", "E=mc^3"),
                              binding("Q3", "Different label", "E=mc^2")])
        report = analyze(path)
        self.assertEqual(report["rows"], 5)
        self.assertEqual(report["unique_exact_formulas"], 2)
        self.assertEqual(report["duplicate_binding_rows"], 1)
        self.assertEqual(report["repeated_formula_rows"], 3)
        self.assertEqual(report["labels_with_multiple_formulas"], 1)
        self.assertEqual(report["entities_with_multiple_formulas"], 1)
        self.assertEqual(report["spoken_aliases_verified"], 0)

    def test_screen_is_not_admission(self):
        path = self.snapshot([binding("Q1", "fraction", r"\frac{x}{y}=1"),
                              binding("Q2", "malformed", r"\frac{x"),
                              binding("Q3", "unsafe", r"\input{file}"),
                              binding("P1", "property", "x=1"),
                              binding("Q4", "bad encoding", "\ufffd")])
        report = analyze(path)
        self.assertEqual(report["unique_formula_lexical_screen"]["passes_lexical_screen"], 2)
        self.assertEqual(report["commands_outside_current_allowlist"]["input"], 1)
        self.assertEqual(report["command_document_frequency"]["frac"], 2)
        self.assertEqual(report["row_relevance_heuristic"]["property_entity"], 1)
        self.assertEqual(report["row_relevance_heuristic"]["encoding_or_control_issue"], 1)
        self.assertEqual(report["status"], "candidate_only")
        self.assertIn("No entries have been admitted", markdown(report))

    def test_formula_case_and_whitespace_are_preserved(self):
        path = self.snapshot([binding("Q1", "x", "x=1"), binding("Q2", "X", "X=1"),
                              binding("Q3", "x", "x = 1")])
        report = analyze(path)
        self.assertEqual(report["unique_exact_formulas"], 3)
        self.assertEqual(report["unique_normalized_labels"], 1)

    def test_hash_and_row_count_verified(self):
        path = self.snapshot([binding("Q1", "x", "x=1")])
        raw = path / "snapshot.json"
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            analyze(path)
        manifest = path / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        data["rows"] = 2
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "row count"):
            analyze(path)

    def test_repeatable_and_read_only(self):
        path = self.snapshot([binding("Q1", "x", "x=1")])
        before = {p.name: p.read_bytes() for p in path.iterdir()}
        first = analyze(path)
        self.assertEqual(first, analyze(path))
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_invalid_entity_counted(self):
        path = self.snapshot([binding("BAD", "x", "x=1")])
        report = analyze(path)
        self.assertEqual(report["valid_binding_rows"], 0)
        self.assertEqual(report["invalid_binding_rows"]["Unexpected entity identifier"], 1)


if __name__ == "__main__":
    unittest.main()
