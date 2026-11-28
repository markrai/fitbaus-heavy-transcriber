import unittest
from unittest.mock import patch

from stem.hybrid import EULER, MASS_ENERGY, PYTHAGORAS, build_hybrid
from stem.qualify_hybrid import qualify
from stem.qualify_recognition import build_review_dictionary


class HybridRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, cls.rows, cls.binding = build_hybrid()

    def assert_match(self, text, phrase, identity, latex):
        matches = self.hybrid.recognize(text)
        self.assertEqual(len(matches), 1, text)
        match = matches[0]
        self.assertEqual((match.dictionary_id, match.latex), (identity, latex))
        self.assertEqual(match.start, text.index(phrase))
        self.assertEqual(match.end, match.start + len(phrase))
        self.assertEqual(text[match.start:match.end], match.source_text)
        self.assertEqual(match.source_text, phrase)

    def test_structural_exact_identity(self):
        for text, identity, latex in (
            ("e^(i*pi)+1=0", EULER, r"e^{i\pi}+1=0"),
            ("a²+b²=c²", PYTHAGORAS, "a^2+b^2=c^2"),
            ("E=m*c²", MASS_ENERGY, "E=mc^2"),
        ):
            with self.subTest(text=text):
                self.assert_match("Résumé. The formula is " + text + ".", text, identity, latex)

    def test_legacy_alias_is_preserved(self):
        self.assert_match("The formula is E equals M C squared.", "E equals M C squared",
                          MASS_ENERGY, "E=mc^2")

    def test_named_euler_shorthand_is_narrow(self):
        for phrase in ("e to the i pi plus 1 equals 0", "e to the i π plus one equals zero"):
            self.assert_match("Euler's identity is " + phrase + ".", phrase, EULER, r"e^{i\pi}+1=0")

    def test_named_variable_substitution_preserves_source_notation(self):
        for phrase in ("x squared plus y squared equals z squared", "x²+y²=z²"):
            self.assert_match("The Pythagorean theorem: " + phrase + ".", phrase,
                              PYTHAGORAS, "x^2+y^2=z^2")

    def test_no_implicit_identity_scope_or_renaming(self):
        for text in (
            "e to the i pi plus 1 equals 0",
            "The formula is e to the i pi plus 1 equals 0.",
            "Euler's identity",
            "Euler's identity is e to the i pi plus 2 equals 0.",
            "Euler's identity is e to the i pi plus 1 equals 1.",
            "Euler's identity is e^(i*pi+1)=0.",
            "Euler's identity is a²+b²=c².",
            "The Pythagorean theorem is e^(i*pi)+1=0.",
            "x²+y²=z²",
            "The Pythagorean theorem is x²+x²=z².",
            "The Pythagorean theorem is e²+y²=z².",
            "The Pythagorean theorem is X²+y²=z².",
            "The Pythagorean theorem is z²=x²+y².",
            "The Pythagorean theorem is x²-y²=z².",
            "E=m*c³", "e=m*c²", "x=1",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.hybrid.recognize(text), ())

    def test_context_abstention_for_new_paths(self):
        phrase = "Euler's identity is e to the i pi plus 1 equals 0"
        for text in ("Not " + phrase + ".", "Suppose " + phrase + ".", phrase + "?",
                     phrase + ", plus one.", phrase + ". Plus one.", phrase + "...",
                     phrase + "\nplus one.", "Incorrect: " + phrase + "."):
            with self.subTest(text=text):
                self.assertEqual(self.hybrid.recognize(text), ())

    def test_multiple_matches_in_original_order(self):
        text = "a²+b²=c². The formula is E equals M C squared."
        matches = self.hybrid.recognize(text)
        self.assertEqual([m.dictionary_id for m in matches], [PYTHAGORAS, MASS_ENERGY])
        self.assertEqual([m.source_text for m in matches], ["a²+b²=c²", "E equals M C squared"])

    def test_rules_fail_closed_on_stale_corpus(self):
        dictionary, rows, binding = build_review_dictionary()
        changed = [dict(row, mathematical_sha256="0" * 64) if row["id"] == EULER else row for row in rows]
        with patch("stem.hybrid.build_review_dictionary", return_value=(dictionary, changed, binding)):
            with self.assertRaisesRegex(ValueError, "Stale structural identity rule"):
                build_hybrid()

    def test_existing_qualification_and_report_identity(self):
        report = qualify()
        self.assertTrue(report["regression"]["pass"], report["regression"]["failures"])
        self.assertTrue(report["context_challenges"]["pass"], report["context_challenges"]["failures"])
        self.assertEqual(report["structural_rule_count"], 3)
        self.assertEqual(report, qualify())
        self.assertFalse(report["recognition_qualified"])
        self.assertFalse(report["release_qualified"])

    def test_input_bounds(self):
        for text in (None, "x" * 32769, "x\x00", "\ud800"):
            with self.subTest(text_type=type(text)), self.assertRaises(ValueError):
                self.hybrid.recognize(text)


if __name__ == "__main__":
    unittest.main()
