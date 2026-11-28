import unittest

from transcriber.contract import AudioIdentity, Cue, TranscriptWindow

from stem.cue_recognition import (
    MAX_GAP_MS, MAX_JOIN_DURATION_MS, CueSpan, recognize_window,
)
from stem.hybrid import EULER, MASS_ENERGY, PYTHAGORAS, build_hybrid


class CueRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, _, _ = build_hybrid()
        cls.identity = AudioIdentity("home", "book", "a" * 64)

    def window(self, *texts, gap=100, duration=1000, start=0):
        cues = tuple(Cue(start + i * (duration + gap),
                         start + i * (duration + gap) + duration, text)
                     for i, text in enumerate(texts))
        return TranscriptWindow(self.identity, start, start + 300000, cues)

    def recognize(self, *texts, **kwargs):
        return recognize_window(self.window(*texts, **kwargs), self.hybrid).matches

    def test_split_equation_maps_exact_cue_spans(self):
        one = "The formula is a squared plus"
        two = "b squared equals c squared."
        window = self.window(one, two)
        result = recognize_window(window, self.hybrid)
        self.assertEqual(result.book_key, self.identity.cache_key())
        self.assertEqual(result.window_start_ms, window.start_ms)
        self.assertEqual(result.window_end_ms, window.end_ms)
        self.assertEqual(result.policy_sha256, self.hybrid.policy_sha256)
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual((match.dictionary_id, match.latex), (PYTHAGORAS, "a^2+b^2=c^2"))
        self.assertEqual(match.spans, (
            CueSpan(0, len("The formula is "), len(one), 0, 1000, "a squared plus"),
            CueSpan(1, 0, len(two) - 1, 1100, 2100, "b squared equals c squared"),
        ))
        self.assertEqual((match.evidence_start_cue, match.evidence_end_cue), (0, 1))

    def test_three_cues_and_relation_boundary(self):
        matches = self.recognize("a squared", "plus b squared equals", "c squared.")
        self.assertEqual(len(matches), 1)
        self.assertEqual([s.source_text for s in matches[0].spans],
                         ["a squared", "plus b squared equals", "c squared"])

    def test_named_intro_only_cue_is_evidence_not_annotation(self):
        matches = self.recognize("Euler's identity is", "e to the i pi plus 1 equals 0.")
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.dictionary_id, EULER)
        self.assertEqual([s.cue_index for s in match.spans], [1])
        self.assertEqual((match.evidence_start_cue, match.evidence_end_cue), (0, 1))

    def test_restatement_cue_is_evidence_not_annotation(self):
        first = "e to the i pi plus one equals zero,"
        matches = self.recognize(first, "or e to the i pi equals negative one.")
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.dictionary_id, EULER)
        self.assertEqual([s.source_text for s in match.spans], [first[:-1]])
        self.assertEqual((match.evidence_start_cue, match.evidence_end_cue), (0, 1))

    def test_preserved_variable_notation_and_whitespace(self):
        first = "  The Pythagorean theorem: x squared plus  "
        second = "\ty squared equals z squared. "
        matches = self.recognize(first, second)
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.latex, "x^2+y^2=z^2")
        for part in match.spans:
            text = (first, second)[part.cue_index]
            self.assertEqual(text[part.start:part.end], part.source_text)

    def test_unlinked_single_cue_matches_unchanged(self):
        texts = ("A chapter begins.", "E=m*c².", "a²+b²=c².", "Ordinary narration.")
        matches = self.recognize(*texts)
        self.assertEqual([match.dictionary_id for match in matches], [MASS_ENERGY, PYTHAGORAS])
        self.assertEqual([match.spans[0].cue_index for match in matches], [1, 2])

    def test_abstain_on_continuation_not_prefix(self):
        for texts in (
            ("a²+b²=c²", "plus one."),
            ("a²+b²=c².", "Plus one."),
            ("a²+b²=c²?", "plus one."),
            ("a squared plus", "b squared equals c squared plus", "one."),
            ("a squared plus", "b squared equals c squared", "plus", "one."),
            ("a squared plus", "b squared equals c squared.", "Plus one."),
            ("Suppose a squared plus", "b squared equals c squared."),
            ("a squared plus", "b squared equals c squared?"),
            ("Euler's identity is", "e to the i pi plus 2 equals 0."),
            ("e to the i pi plus one equals zero,", "or e to the i pi equals one."),
        ):
            with self.subTest(texts=texts):
                self.assertEqual(self.recognize(*texts), ())

    def test_gap_duration_and_missing_bridge(self):
        self.assertEqual(self.recognize("a squared plus", "b squared equals c squared.",
                                        gap=MAX_GAP_MS + 1), ())
        self.assertEqual(self.recognize("a squared plus", "b squared equals c squared.",
                                        duration=MAX_JOIN_DURATION_MS // 2), ())
        self.assertEqual(self.recognize("a squared", "b squared equals c squared."), ())
        self.assertEqual(self.recognize("a squared plus", "A new sentence. b squared equals c squared."), ())

    def test_gap_limit_is_inclusive(self):
        self.assertEqual(len(self.recognize("a squared plus", "b squared equals c squared.",
                                            gap=MAX_GAP_MS)), 1)

    def test_window_boundary_never_joined(self):
        left = self.window("a squared plus", start=0)
        right = self.window("b squared equals c squared.", start=300000)
        for window in (left, right):
            self.assertEqual(recognize_window(window, self.hybrid).matches, ())

    def test_empty_window_and_invalid_input(self):
        self.assertEqual(recognize_window(self.window(), self.hybrid).matches, ())
        with self.assertRaises(ValueError):
            recognize_window([], self.hybrid)
        for text in ("x\x00", "\ud800"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.recognize(text)


if __name__ == "__main__":
    unittest.main()
