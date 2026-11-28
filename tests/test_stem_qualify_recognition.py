import copy
import json
from pathlib import Path
import tempfile
import unittest

from stem.corpus_model import digest
from stem.qualify_recognition import (
    Case, Expected, FIXTURES, OBSERVED_SCHEMA, build_review_dictionary, evaluate,
    load_observations, qualify,
)


class RecognitionQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary, cls.rows, cls.binding = build_review_dictionary()
        cls.report = qualify()

    def test_complete_regression_and_deterministic_report(self):
        report = self.report
        self.assertTrue(report["regression"]["pass"], report["regression"]["failures"])
        self.assertEqual(report["regression"]["expected_representation_coverage"], len(self.dictionary.entries))
        self.assertEqual(report["representations"], len(self.rows))
        self.assertEqual(report["aliases"], len(self.dictionary.aliases))
        self.assertEqual(report, qualify())
        self.assertEqual(report["report_sha256"], digest({
            key: value for key, value in report.items() if key != "report_sha256"
        }))
        self.assertFalse(report["recognition_qualified"])
        self.assertFalse(report["release_qualified"])
        self.assertIsNone(report["observations"])

    def test_context_challenges_are_separate_from_regression(self):
        report = self.report
        self.assertEqual(report["context_challenges"]["total"]["cases"], 3 * len(self.dictionary.entries))
        self.assertEqual(report["context_challenges"]["total"]["expected_matches"], 0)
        self.assertIsNone(report["context_challenges"]["total"]["recall"])
        if not report["context_challenges"]["pass"]:
            self.assertIn("context_abstention_gaps", report["blockers"])

    def test_wrong_identity_or_span_counts_as_both_error_types(self):
        first, second = self.dictionary.entries[:2]
        phrase = first.aliases[0]
        for expected in (Expected(second.id, 0, len(phrase), second.latex),
                         Expected(first.id, 1, len(phrase), first.latex)):
            with self.subTest(expected=expected):
                result = evaluate([Case("wrong", "test", phrase, (expected,))], self.dictionary)
                self.assertEqual(result["total"]["false_positive"], 1)
                self.assertEqual(result["total"]["false_negative"], 1)
                self.assertFalse(result["pass"])

    def test_incomplete_and_stale_fixtures_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = next(iter(sorted(FIXTURES.glob("stem_recitation_*.json"))))
            value = json.loads(path.read_text(encoding="utf-8"))
            (root / path.name).write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "entire authoring corpus"):
                build_review_dictionary(fixtures=root)
            value["rows"][0]["mathematical_sha256"] = "0" * 64
            (root / path.name).write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Stale"):
                build_review_dictionary(fixtures=root)

    def observations(self):
        entry = self.dictionary.entries[0]
        phrase = entry.aliases[0]
        return {"schema": OBSERVED_SCHEMA,
                "provenance": {"source": "synthetic test only", "transcriber": "test",
                               "labeling_method": "test fixture"},
                "cases": [{"id": "one", "text": "Résumé. " + phrase,
                           "expected": [{"id": entry.id, "start": len("Résumé. "),
                                         "end": len("Résumé. " + phrase)}]},
                          {"id": "two", "text": "Ordinary narration.", "expected": []}]}

    def test_observation_import_is_labeled_and_not_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_text(json.dumps(self.observations()), encoding="utf-8")
            report = qualify(observed=path)
            self.assertTrue(report["observations"]["results"]["pass"])
            self.assertFalse(report["observations"]["provenance_verified"])
            self.assertFalse(report["recognition_qualified"])
            self.assertFalse(report["release_qualified"])
            self.assertNotIn("no_operator_labeled_observations", report["blockers"])

    def test_observation_validation_rejects_invalid_spans_and_ids(self):
        value = self.observations()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            for replacement in ({"start": True}, {"end": 100000}, {"id": "unknown"}):
                bad = copy.deepcopy(value)
                bad["cases"][0]["expected"][0].update(replacement)
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "Invalid observation span"):
                    load_observations(path, self.dictionary)


if __name__ == "__main__":
    unittest.main()
