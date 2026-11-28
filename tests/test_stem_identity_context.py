import copy
import json
from pathlib import Path
import tempfile
import unittest

from stem.hybrid import EULER, PYTHAGORAS, build_hybrid
from stem.observation_labels import SCHEMA, load_hybrid_observations
from stem.qualify_recognition import evaluate


class IdentityContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, _, _ = build_hybrid()

    def assert_match(self, text, phrase, identity, latex):
        matches = self.hybrid.recognize(text)
        self.assertEqual(len(matches), 1, text)
        match = matches[0]
        self.assertEqual((match.dictionary_id, match.latex), (identity, latex))
        self.assertEqual((match.start, match.end), (text.index(phrase), text.index(phrase) + len(phrase)))
        self.assertEqual(match.source_text, phrase)

    def test_equivalent_euler_restatement(self):
        phrase = "e to the i pi plus one equals zero"
        for tail in ("", ", into another notation,"):
            text = phrase + ", or e to the i pi equals negative one" + tail
            self.assert_match(text, phrase, EULER, r"e^{i\pi}+1=0")

    def test_contextual_named_clause(self):
        phrase = "x squared plus y squared equals z squared"
        self.assert_match("The Pythagorean theorem is " + phrase + ", where x, y and z denote lengths.",
                          phrase, PYTHAGORAS, "x^2+y^2=z^2")
        phrase = "e to the i pi plus 1 equals 0"
        self.assert_match("Euler's identity is " + phrase + ", which is remarkable.",
                          phrase, EULER, r"e^{i\pi}+1=0")

    def test_no_suffix_salvage_or_unanchored_context(self):
        first = "e to the i pi plus one equals zero"
        second = "e to the i pi equals negative one"
        for text in (
            first, "which led to " + first + ",", "The closest thing to " + first + " that I know",
            "Suppose " + first + ", or " + second,
            first + ", or e to the i pi equals one",
            first + ", or " + second + " plus one",
            first + ", or " + second + ", plus one",
            first + ", or " + second + ", into plus one",
            first + ", or " + second + "?",
            first + ", or " + second + ". Plus one.",
            first + ", or " + second + ", or " + second,
            "Euler's identity is " + first + ", where x equals 2",
            "Euler's identity is " + first + ", which plus one",
            "Euler's identity is " + first + ", which is false",
            "Euler's identity is " + first + ", which is not correct",
            first + ", or " + second + ", into incorrect notation",
            "The Pythagorean theorem is x²+y²=z², where x + y",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.hybrid.recognize(text), ())

    def observation(self):
        text = "The Pythagorean theorem is x²+y²=z², where the symbols denote lengths."
        phrase = "x²+y²=z²"
        return {"schema": SCHEMA,
                "provenance": {"source": "synthetic fixture", "transcriber": "manual",
                               "labeling_method": "explicit annotation"},
                "cases": [{"id": "variant", "text": text, "expected": [
                    {"id": PYTHAGORAS, "start": text.index(phrase),
                     "end": text.index(phrase) + len(phrase), "latex": "x^2+y^2=z^2"}]}]}

    def test_notation_label_scores_exact_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.json"
            path.write_text(json.dumps(self.observation()), encoding="utf-8")
            cases, metadata = load_hybrid_observations(path, self.hybrid.dictionary)
            self.assertEqual(metadata["schema"], SCHEMA)
            self.assertFalse(metadata["provenance_verified"])
            result = evaluate(cases, self.hybrid.dictionary,
                              recognizer=lambda text, dictionary: self.hybrid.recognize(text))
            self.assertTrue(result["pass"])
            self.assertEqual(result["total"]["true_positive"], 1)

    def test_labels_are_independent_of_matcher_predictions(self):
        value = self.observation()
        phrase = "x²+y²=z²"
        row = value["cases"][0]
        row["text"] = phrase
        row["expected"][0].update(start=0, end=len(phrase))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            cases, _ = load_hybrid_observations(path, self.hybrid.dictionary)
            result = evaluate(cases, self.hybrid.dictionary,
                              recognizer=lambda text, dictionary: self.hybrid.recognize(text))
            self.assertEqual(result["total"]["false_negative"], 1)

    def test_invalid_notation_and_offsets_rejected(self):
        for change in ({"latex": r"\input{file}"}, {"latex": "x^2+x^2=z^2"},
                       {"latex": "x^2-y^2=z^2"}, {"latex": "X^2+y^2=z^2"},
                       {"latex": None}, {"start": True}, {"end": 9999}, {"id": EULER}):
            value = copy.deepcopy(self.observation())
            value["cases"][0]["expected"][0].update(change)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "labels.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(change=change), self.assertRaises(ValueError):
                    load_hybrid_observations(path, self.hybrid.dictionary)

    def test_v1_observation_compatibility(self):
        value = self.observation()
        value["schema"] = "fitbaus.stem.recognition-observations/v1"
        value["cases"][0]["expected"][0].pop("latex")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            cases, metadata = load_hybrid_observations(path, self.hybrid.dictionary)
            self.assertEqual(cases[0].expected[0].latex, "a^2+b^2=c^2")
            self.assertEqual(metadata["schema"], value["schema"])


if __name__ == "__main__":
    unittest.main()
