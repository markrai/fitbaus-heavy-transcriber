import copy
import json
import unittest
from stem.dictionary import CURATED, compile_dictionary, load_dictionary, validate_latex
from stem.matcher import recognize


class StemDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = load_dictionary()

    def test_all_aliases_round_trip(self):
        for entry in self.dictionary.entries:
            for phrase in entry.aliases:
                with self.subTest(phrase=phrase):
                    matches = recognize(phrase, self.dictionary)
                    self.assertEqual(len(matches), 1)
                    self.assertEqual(matches[0].latex, entry.latex)
                    self.assertEqual(matches[0].dictionary_id, entry.id)

    def test_source_spans_and_order(self):
        text = "Einstein showed that E equals M C squared. Newton's formula is F equals M A."
        matches = recognize(text, self.dictionary)
        self.assertEqual([m.latex for m in matches], ["E=mc^2", "F=ma"])
        for match in matches:
            self.assertEqual(text[match.start:match.end], match.source_text)

    def test_punctuation_whitespace_and_transcription_variant(self):
        matches = recognize("  A equals PIE   R square! ", self.dictionary)
        self.assertEqual(matches[0].latex, r"A=\pi r^2")
        self.assertEqual(matches[0].source_text, "A equals PIE   R square")

    def test_fail_closed_on_partial_and_ordinary_language(self):
        for text in (
            "E equals M C cubed.",
            "E equals M C squared plus one.",
            "E equals M C squared, plus one.",
            "X plus E equals M C squared.",
            "The root of the problem was pie.",
            "The letter e and the speed of light are interesting.",
            "Einstein described mass and energy.",
        ):
            with self.subTest(text=text):
                self.assertEqual(recognize(text, self.dictionary), ())

    def test_reproducible_digest(self):
        value = json.loads(CURATED.read_text(encoding="utf-8"))
        value["entries"].reverse()
        for row in value["entries"]:
            row["aliases"].reverse()
        self.assertEqual(compile_dictionary(value).digest, self.dictionary.digest)

    def test_collisions_and_unapproved_sources(self):
        value = json.loads(CURATED.read_text(encoding="utf-8"))
        duplicate = copy.deepcopy(value["entries"][0])
        duplicate["id"] = "physics.conflicting"
        duplicate["latex"] = "E=mc^3"
        value["entries"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Ambiguous alias"):
            compile_dictionary(value)
        value["entries"].pop()
        value["entries"][0]["source"] = "mathbridge"
        with self.assertRaisesRegex(ValueError, "Unapproved"):
            compile_dictionary(value)

    def test_restricted_latex(self):
        for expression in (r"\input{secret}", r"\write18{bad}", r"\href{bad}{x}", r"\frac{x}{", r"x}", "$x$", "\\"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    validate_latex(expression)
        self.assertEqual(validate_latex(r"\frac{-b\pm\sqrt{b^2-4ac}}{2a}"), r"\frac{-b\pm\sqrt{b^2-4ac}}{2a}")


if __name__ == "__main__":
    unittest.main()
