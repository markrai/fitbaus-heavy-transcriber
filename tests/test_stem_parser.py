import unittest

from stem.expression import (
    Binary, BinaryOp, Call, Group, Number, Power, Relation, RelationOp, Span,
    Subscript, Symbol, Unary, structural_key, validate,
)
from stem.parser import MAX_PARSE_CHARS, MAX_PARSE_TOKENS, ParseError, parse_expression


def key(source):
    return structural_key(parse_expression(source), source)


class ParserTests(unittest.TestCase):
    def test_pythagorean_variable_names_and_spoken_numbers(self):
        text = "x squared plus y squared equals z squared"
        tree = parse_expression(text)
        self.assertIsInstance(tree, Relation)
        self.assertEqual(tree.span, Span(0, len(text)))
        self.assertEqual(key(text), key("x²+y²=z²"))
        self.assertNotEqual(key(text), key("a²+b²=c²"))
        self.assertEqual(key("i times i equals negative 1"), key("i*i=-1"))

    def test_precedence_and_order(self):
        self.assertEqual(key("a+b*c"), (
            "binary", "+", ("symbol", "a"), ("binary", "*", ("symbol", "b"), ("symbol", "c"))))
        self.assertNotEqual(key("a+b*c"), key("(a+b)*c"))
        self.assertEqual(key("a-b-c"), (
            "binary", "-", ("binary", "-", ("symbol", "a"), ("symbol", "b")), ("symbol", "c")))
        self.assertEqual(key("-x^2"), ("unary", "-", ("power", ("symbol", "x"), ("number", "2"))))
        self.assertEqual(key("x^2^3"), ("power", ("symbol", "x"), ("power", ("number", "2"), ("number", "3"))))

    def test_explicit_exponent_boundaries(self):
        symbolic = "e^(i*pi)+1=0"
        for spoken in (
            "e raised to the power of open parenthesis i times pi close parenthesis plus one equals zero",
            "e to the power of the quantity i times pi end exponent plus 1 equals 0",
            "e to the open parenthesis i times pi close parenthesis plus one equals zero",
        ):
            with self.subTest(spoken=spoken):
                self.assertEqual(key(spoken), key(symbolic))
        self.assertEqual(key("x to the second power plus 1"), key("x²+1"))
        self.assertEqual(key("x raised to the power of 2 equals y"), key("x²=y"))

    def test_ambiguous_exponents_are_not_guessed(self):
        for text in (
            "e to the i pi plus 1 equals 0", "x raised to the power of n plus one",
            "x to the power of 2 times y", "x to the second",
            "x to the power of the quantity n plus one",
            "x raised to the power of n end exponent", "x squared squared",
        ):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_expression(text)

    def test_fractions_and_function_scopes(self):
        self.assertEqual(key("open parenthesis a plus b close parenthesis divided by c"),
                         key("(a+b)/c"))
        self.assertEqual(key("a divided by open parenthesis b plus c close parenthesis"), key("a/(b+c)"))
        self.assertEqual(key("cosine of open parenthesis pi over 2 close parenthesis equals 0"),
                         key("cos(pi/2)=0"))
        self.assertEqual(key("square root of negative one"), key("√(-1)"))
        self.assertEqual(key("sin(x)+1"), key("sine of open parenthesis x close parenthesis plus 1"))

    def test_ambiguous_fractions_and_function_arguments(self):
        for text in (
            "a plus b over c", "a over b plus c", "a over b times c",
            "a times b over c", "a over b over c", "a over b squared",
            "cosine of pi over 2 equals 0", "square root of x plus y",
            "negative x squared", "negative 3 factorial",
        ):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_expression(text)

    def test_subscripts_factorials_and_case(self):
        self.assertEqual(key("x sub 1 equals 3 factorial"), key("x₁=3!"))
        self.assertEqual(key("x_1"), key("x₁"))
        self.assertEqual(key("capital x equals lowercase X"), key("X=x"))
        self.assertEqual(key("capital delta"), key("Δ"))
        for text in ("x sub 1.5", "2 sub x", "x sub i sub j", "capital infinity", "3 !"):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_expression(text)

    def test_relations_and_signs(self):
        self.assertEqual(key("a is less than or equal to b equals c"), key("a<=b=c"))
        self.assertEqual(key("a plus or minus b"), key("a±b"))
        self.assertEqual(key("negative open parenthesis x squared close parenthesis"), key("-(x²)"))
        self.assertNotEqual(key("a>b"), key("b>a"))
        self.assertEqual(parse_expression("a=b=c").operators, (RelationOp.EQUAL, RelationOp.EQUAL))

    def test_bounded_implicit_multiplication(self):
        self.assertEqual(key("3x"), key("3*x"))
        self.assertEqual(key("2(x+1)"), key("2*(x+1)"))
        for text in ("mc²", "m c squared", "x(y)", "3 x", "3pi", "2 3", "twenty one"):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_expression(text)

    def test_complete_input_and_punctuation(self):
        for text in (
            "", " \t", "The formula is x squared equals y", "x=1.",
            "x=1?", "x=1, plus two", "x=1; y=2", "x=1\n", "x\u200b=1",
            "x=1 garbage", "x=", "=x", "(x=1)", "(x+1]", "x+)", "x +",
            "x plus pie", "x all divided by y", "x′=1", "x={1}",
        ):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_expression(text)

    def test_source_spans_and_validation(self):
        text = " \tX squared plus pi equals 1 "
        tree = parse_expression(text)
        self.assertEqual(tree.span, Span(2, len(text) - 1))
        self.assertEqual(text[tree.span.start:tree.span.end], "X squared plus pi equals 1")
        left = tree.operands[0]
        self.assertIsInstance(left, Binary)
        self.assertIsInstance(left.left, Power)
        self.assertEqual(text[left.left.exponent.span.start:left.left.exponent.span.end], "squared")
        self.assertEqual(text[left.right.span.start:left.right.span.end], "pi")
        self.assertEqual(validate(tree, text).nodes, 7)
        self.assertEqual(key("π²=1"), key("pi squared equals one"))

    def test_complexity_and_input_limits(self):
        for text in (
            None, "x" * (MAX_PARSE_CHARS + 1), "x\x00", "\ud800",
            "+".join("x" for _ in range(MAX_PARSE_TOKENS)),
            "(" * 40 + "x" + ")" * 40, "-" * 40 + "x",
            "+".join("x" for _ in range(40)), "9" * 65,
        ):
            with self.subTest(text_type=type(text).__name__), self.assertRaises(ParseError):
                parse_expression(text)


if __name__ == "__main__":
    unittest.main()
