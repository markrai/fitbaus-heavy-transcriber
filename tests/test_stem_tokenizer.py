import unittest

from stem.tokenizer import Form, Kind, MAX_SOURCE_CHARS, MAX_TOKENS, tokenize


def math_tokens(text):
    return [(token.kind, token.value) for token in tokenize(text)
            if token.kind != Kind.WHITESPACE]


class TokenizerTests(unittest.TestCase):
    def test_spoken_and_symbolic_numbers_and_powers(self):
        self.assertEqual(math_tokens("x squared plus one equals zero"), math_tokens("x² + 1 = 0"))
        self.assertEqual(math_tokens("x cubed"), math_tokens("x³"))
        self.assertEqual(math_tokens("x¹²"), [(Kind.SYMBOL, "x"), (Kind.EXPONENT, "12")])
        self.assertEqual(math_tokens("x₁₂"), [(Kind.SYMBOL, "x"), (Kind.SUBSCRIPT, "12")])

    def test_unscoped_euler_recitation_stays_unscoped(self):
        self.assertEqual(math_tokens("e to the i pi plus 1 equals 0"), [
            (Kind.SYMBOL, "e"), (Kind.POWER_HINT, "^"), (Kind.SYMBOL, "i"),
            (Kind.SYMBOL, "pi"), (Kind.OPERATOR, "+"), (Kind.NUMBER, "1"),
            (Kind.RELATION, "="), (Kind.NUMBER, "0"),
        ])
        self.assertNotIn(Kind.GROUP, [token.kind for token in tokenize("e to the i pi plus 1 equals 0")])

    def test_exact_lossless_codepoint_spans(self):
        text = "📘 Résumé. \tX squared\r\nis equal to π²; café\u0301!"
        tokens = tokenize(text)
        self.assertEqual("".join(token.source_text for token in tokens), text)
        previous = 0
        for token in tokens:
            self.assertEqual(token.start, previous)
            self.assertGreater(token.end, token.start)
            self.assertEqual(text[token.start:token.end], token.source_text)
            previous = token.end
        self.assertEqual(previous, len(text))
        relation = next(token for token in tokens if token.kind == Kind.RELATION)
        self.assertEqual(relation.source_text, "is equal to")
        self.assertEqual(relation.start, text.index("is equal to"))

    def test_longest_phrase_and_case_insensitive_spoken_form(self):
        tokens = [t for t in tokenize("X IS GREATER\tTHAN OR EQUAL TO 2") if t.kind != Kind.WHITESPACE]
        self.assertEqual([(t.kind, t.value) for t in tokens], [
            (Kind.SYMBOL, "X"), (Kind.RELATION, ">="), (Kind.NUMBER, "2"),
        ])
        self.assertEqual(tokens[1].form, Form.SPOKEN)
        self.assertEqual(tokens[1].source_text, "IS GREATER\tTHAN OR EQUAL TO")
        self.assertEqual(math_tokens("not equal to"), [(Kind.RELATION, "!=")])
        self.assertEqual(math_tokens("all divided by"), [(Kind.SCOPE, "all_divided_by")])

    def test_symbol_case_and_unknown_words_preserved(self):
        self.assertEqual(math_tokens("X x Δ δ π"), [
            (Kind.SYMBOL, "X"), (Kind.SYMBOL, "x"), (Kind.SYMBOL, "Delta"),
            (Kind.SYMBOL, "delta"), (Kind.SYMBOL, "pi"),
        ])
        for word in ("pie", "sign", "for", "too", "mc", "Newton", "café", "πx"):
            with self.subTest(word=word):
                self.assertEqual(math_tokens(word), [(Kind.WORD, word)])

    def test_adjacent_numeric_and_symbolic_tokens_are_not_multiplied(self):
        self.assertEqual(math_tokens("3x"), [(Kind.NUMBER, "3"), (Kind.SYMBOL, "x")])
        self.assertEqual(math_tokens("mc²"), [(Kind.WORD, "mc"), (Kind.EXPONENT, "2")])
        self.assertEqual(math_tokens("1.00"), [(Kind.NUMBER, "1.00")])
        self.assertEqual(math_tokens("2..3"), [
            (Kind.NUMBER, "2"), (Kind.PUNCTUATION, "."), (Kind.PUNCTUATION, "."), (Kind.NUMBER, "3"),
        ])

    def test_phrase_boundaries_and_line_breaks(self):
        self.assertEqual(math_tokens("equal today"), [(Kind.RELATION, "="), (Kind.WORD, "today")])
        self.assertEqual(math_tokens("divided\nby"), [(Kind.WORD, "divided"), (Kind.WORD, "by")])
        self.assertEqual(math_tokens("to theatric"), [(Kind.WORD, "to"), (Kind.WORD, "theatric")])
        self.assertEqual(math_tokens("is equal to2"), [
            (Kind.WORD, "is"), (Kind.RELATION, "="), (Kind.WORD, "to"), (Kind.NUMBER, "2"),
        ])

    def test_no_silent_unicode_normalization_or_group_repair(self):
        self.assertEqual(math_tokens("（x"), [(Kind.PUNCTUATION, "（"), (Kind.SYMBOL, "x")])
        self.assertEqual(math_tokens("x\u200b=1"), [
            (Kind.SYMBOL, "x"), (Kind.UNKNOWN, "\u200b"), (Kind.RELATION, "="), (Kind.NUMBER, "1"),
        ])
        self.assertEqual(math_tokens("open parenthesis x"), [(Kind.GROUP, "("), (Kind.SYMBOL, "x")])

    def test_terminal_symbol_spans_and_two_character_relations(self):
        for text in ("+", "=", "≥", "√", "x=", "x<=", "x!=", "x>="):
            with self.subTest(text=text):
                tokens = tokenize(text)
                self.assertEqual(tokens[-1].end, len(text))
                self.assertEqual("".join(t.source_text for t in tokens), text)
        self.assertEqual(math_tokens("x<=2"), [
            (Kind.SYMBOL, "x"), (Kind.RELATION, "<="), (Kind.NUMBER, "2"),
        ])

    def test_bounds_and_invalid_input(self):
        self.assertEqual(tokenize(""), ())
        for value in (None, 4, "x\x00y", "\ud800", " " * (MAX_SOURCE_CHARS + 1), "+" * (MAX_TOKENS + 1)):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                tokenize(value)
        self.assertEqual(len(tokenize("+" * MAX_TOKENS)), MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
