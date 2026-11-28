import copy
import unittest

from transcriber.contract import AudioIdentity, Cue, TranscriptWindow

from stem.context_observations import verify_context
from stem.corpus_model import digest
from stem.cue_recognition import recognize_window
from stem.hybrid import EULER, MASS_ENERGY, PYTHAGORAS, build_hybrid
from stem.qualify_hybrid import structural_cases
from stem.qualify_recognition import context_challenges, synthetic_cases


class ProseContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, cls.rows, _ = build_hybrid()
        cls.identity = AudioIdentity("home", "book", "a" * 64)

    def window(self, *texts, gap=100):
        cues = tuple(Cue(i * (1000 + gap), i * (1000 + gap) + 1000, text)
                     for i, text in enumerate(texts))
        return TranscriptWindow(self.identity, 0, 300000, cues)

    def recognize(self, *texts, **kwargs):
        return recognize_window(self.window(*texts, **kwargs), self.hybrid).matches

    def assert_match(self, texts, phrase, identity, latex, evidence, index):
        matches = self.recognize(*texts)
        self.assertEqual(len(matches), 1, texts)
        match = matches[0]
        self.assertEqual((match.dictionary_id, match.latex), (identity, latex))
        self.assertEqual((match.evidence_start_cue, match.evidence_end_cue), (evidence, index))
        self.assertEqual(len(match.spans), 1)
        part = match.spans[0]
        self.assertEqual(part.cue_index, index)
        self.assertEqual((part.start, part.end), (texts[index].index(phrase), texts[index].index(phrase) + len(phrase)))
        self.assertEqual(part.source_text, phrase)

    def test_referential_structural_clause(self):
        self.assert_match(("The expression written as E=m*c², where the symbols denote physical quantities.",),
                          "E=m*c²", MASS_ENERGY, "E=mc^2", 0, 0)

    def test_named_triangle_context_preserves_variables(self):
        texts = ("Consider the Pythagorean theorem.",
                 "Its relation concerns right triangle side lengths.",
                 "The relationship can be written as follows:",
                 "x squared plus y squared equals z squared, where the letters denote lengths.")
        self.assert_match(texts, "x squared plus y squared equals z squared",
                          PYTHAGORAS, "x^2+y^2=z^2", 0, 3)

    def test_interpretation_question_not_truth_question(self):
        self.assert_match(("What is the meaning of Euler's identity written as",
                           "e to the i pi plus one equals zero? This expression has many applications."),
                          "e to the i pi plus one equals zero", EULER, r"e^{i\pi}+1=0", 0, 1)
        self.assert_match(("What is the physical interpretation of the equation E=m*c²?",),
                          "E=m*c²", MASS_ENERGY, "E=mc^2", 0, 0)

    def test_no_unlicensed_substrings_or_uncertain_scope(self):
        for text in (
            "We noticed e to the i pi plus one equals zero in a textbook.",
            "The expression written as e to the i pi plus one equals zero, where the symbols denote constants.",
            "Is Euler's identity e to the i pi plus one equals zero?",
            "What is the meaning of Euler's identity written as e to the i pi plus two equals zero?",
            "What is the meaning of Euler's identity written as e to the i pi plus one equals zero? Plus one.",
            "What is the meaning of Euler's identity written as e to the i pi plus one equals zero? This is incorrect.",
            "Suppose the expression written as E=m*c², where the symbols denote quantities.",
            "The expression E=m*c², which is not true.",
            "The expression E=m*c², plus one.",
            "The expression E=m*c², where x equals one.",
            "The expression x²+y²=z², where the symbols denote lengths.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.recognize(text), ())

    def test_stale_missing_and_conflicting_triangle_context(self):
        anchor = "x²+y²=z², where the symbols denote lengths."
        for texts in (
            ("The theorem is useful.", "Right triangle sides can be written as follows:", anchor),
            ("The Pythagorean theorem concerns right triangle sides.", "Another chapter begins.", anchor),
            ("The Pythagorean theorem concerns right triangle sides.", "Suppose the relation is written as follows:", anchor),
            ("This is not the Pythagorean theorem for right triangle sides.", "The relation is written as follows:", anchor),
            ("Suppose the Pythagorean theorem concerns right triangle sides.", "The relation is written as follows:", anchor),
            ("The Pythagorean theorem concerns right triangle sides.", "Ordinary narration.", "Ordinary narration.",
             "The relation is written as follows:", anchor),
        ):
            with self.subTest(texts=texts):
                self.assertEqual(self.recognize(*texts), ())
        self.assertEqual(self.recognize("The Pythagorean theorem for right triangles is written as follows:", anchor,
                                        gap=1001), ())

    def test_all_existing_single_cue_regressions_preserved(self):
        cases = (*synthetic_cases(self.hybrid.dictionary, self.rows),
                 *context_challenges(self.hybrid.dictionary), *structural_cases())
        for case in cases:
            expected = tuple((item.id, item.start, item.end, item.latex) for item in case.expected)
            matches = self.recognize(case.text)
            actual = tuple((match.dictionary_id, match.spans[0].start, match.spans[0].end, match.latex)
                           for match in matches)
            self.assertEqual(actual, expected, case.id)

    def test_requalification_binds_unchanged_evidence(self):
        original = {"schema": "sample", "windows": [{"text": "original"}],
                    "hybrid_policy_sha256": "a" * 64, "implementation_sha256": "b" * 64}
        original["context_sha256"] = digest(original)
        current = {**original, "hybrid_policy_sha256": "c" * 64, "implementation_sha256": "d" * 64}
        current["context_sha256"] = digest({k: v for k, v in current.items() if k != "context_sha256"})
        with self.assertRaises(ValueError):
            verify_context(original, current)
        verify_context(original, current, requalify=True)
        changed = copy.deepcopy(original)
        changed["windows"][0]["text"] = "different"
        changed["context_sha256"] = digest({k: v for k, v in changed.items() if k != "context_sha256"})
        with self.assertRaises(ValueError):
            verify_context(changed, current, requalify=True)


if __name__ == "__main__":
    unittest.main()
