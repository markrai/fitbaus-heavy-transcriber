from dataclasses import FrozenInstanceError
import unittest

from stem.expression import (
    Binary, BinaryOp, Call, Factorial, Function, Group, MAX_DEPTH, MAX_NODES,
    Number, Power, Relation, RelationOp, Span, Subscript, Symbol, Unary, UnaryOp,
    structural_key, validate,
)


class ExpressionTests(unittest.TestCase):
    def test_explicit_euler_structure(self):
        source = "e^(i*pi)+1=0"
        product = Binary(Span(3, 7), BinaryOp.MULTIPLY,
                         Symbol(Span(3, 4), "i"), Symbol(Span(5, 7), "pi"))
        exponent = Group(Span(2, 8), product)
        power = Power(Span(0, 8), Symbol(Span(0, 1), "e"), exponent)
        left = Binary(Span(0, 10), BinaryOp.ADD, power, Number(Span(9, 10), "1"))
        tree = Relation(Span(0, 12), (left, Number(Span(11, 12), "0")), (RelationOp.EQUAL,))
        self.assertEqual(validate(tree, source).nodes, 10)
        self.assertEqual(structural_key(tree, source), (
            "relation", ("=",), (
                ("binary", "+", ("power", ("symbol", "e"),
                                  ("binary", "*", ("symbol", "i"), ("symbol", "pi"))),
                 ("number", "1")), ("number", "0"))))

    def test_scope_and_operand_order_are_significant(self):
        source = "a+b*c"
        a, b, c = Symbol(Span(0, 1), "a"), Symbol(Span(2, 3), "b"), Symbol(Span(4, 5), "c")
        left = Binary(Span(0, 5), BinaryOp.MULTIPLY,
                      Binary(Span(0, 3), BinaryOp.ADD, a, b), c)
        right = Binary(Span(0, 5), BinaryOp.ADD, a,
                       Binary(Span(2, 5), BinaryOp.MULTIPLY, b, c))
        self.assertNotEqual(structural_key(left, source), structural_key(right, source))
        self.assertNotEqual(structural_key(Symbol(Span(0, 1), "X"), "X"),
                            structural_key(Symbol(Span(0, 1), "x"), "x"))
        self.assertNotEqual(structural_key(Number(Span(0, 4), "1.00"), "1.00"),
                            structural_key(Number(Span(0, 1), "1"), "1"))

    def test_grouping_wrappers_do_not_change_structural_identity(self):
        one = Group(Span(0, 3), Symbol(Span(1, 2), "x"))
        two = Symbol(Span(0, 1), "x")
        self.assertEqual(structural_key(one, "(x)"), structural_key(two, "x"))

    def test_spoken_postfix_power_and_unicode_prefix(self):
        text = "📘 x squared"
        tree = Power(Span(2, 11), Symbol(Span(2, 3), "x"), Number(Span(4, 11), "2"))
        symbolic = Power(Span(0, 2), Symbol(Span(0, 1), "x"), Number(Span(1, 2), "2"))
        self.assertEqual(structural_key(tree, text), structural_key(symbolic, "x²"))
        self.assertEqual(text[tree.span.start:tree.span.end], "x squared")

    def test_relation_chain_subscript_and_factorial(self):
        text = "a_1=3!=b"
        indexed = Subscript(Span(0, 3), Symbol(Span(0, 1), "a"), Number(Span(2, 3), "1"))
        tree = Relation(Span(0, 8), (indexed, Number(Span(4, 5), "3"), Symbol(Span(7, 8), "b")),
                        (RelationOp.EQUAL, RelationOp.NOT_EQUAL))
        self.assertEqual(validate(tree, text).nodes, 6)
        self.assertEqual(structural_key(tree, text)[1], ("=", "!="))
        self.assertEqual(structural_key(Factorial(Span(0, 2), Number(Span(0, 1), "3")), "3!"),
                         ("factorial", ("number", "3")))

    def test_explicit_function_fraction_and_signed_argument(self):
        source = "sin(-x)/2"
        negative = Unary(Span(4, 6), UnaryOp.MINUS, Symbol(Span(5, 6), "x"))
        call = Call(Span(0, 7), Function.SIN, Group(Span(3, 7), negative))
        tree = Binary(Span(0, 9), BinaryOp.DIVIDE, call, Number(Span(8, 9), "2"))
        self.assertEqual(structural_key(tree, source), (
            "binary", "/", ("call", "sin", ("unary", "-", ("symbol", "x"))), ("number", "2")))

    def test_implicit_multiplication_shape_is_supported_not_inferred(self):
        tree = Binary(Span(0, 2), BinaryOp.MULTIPLY, Number(Span(0, 1), "3"), Symbol(Span(1, 2), "x"))
        self.assertEqual(validate(tree, "3x").nodes, 3)

    def test_invalid_payloads_and_types(self):
        for node in (
            Number(Span(0, 1), "NaN"), Number(Span(0, 1), "-1"),
            Number(Span(0, 1), "1" * 65), Symbol(Span(0, 1), r"\input"),
            Symbol(Span(0, 1), "mc"), Unary(Span(0, 2), "-", Symbol(Span(1, 2), "x")),
            Call(Span(0, 2), "eval", Symbol(Span(1, 2), "x")),
        ):
            with self.subTest(node=node), self.assertRaises(ValueError):
                validate(node, "xx")

    def test_invalid_spans_and_order(self):
        for node in (
            Symbol(Span(True, 2), "x"), Symbol(Span(-1, 1), "x"), Symbol(Span(0, 4), "x"),
            Symbol(Span(1, 1), "x"), Symbol(Span(1, 2), "x"),
            Binary(Span(0, 3), BinaryOp.ADD, Symbol(Span(2, 3), "x"), Symbol(Span(0, 1), "y")),
            Binary(Span(0, 3), BinaryOp.ADD, Symbol(Span(0, 2), "x"), Symbol(Span(1, 3), "y")),
            Binary(Span(0, 2), BinaryOp.ADD, Symbol(Span(0, 1), "x"), Symbol(Span(1, 2), "y")),
            Group(Span(0, 3), Symbol(Span(0, 3), "x")),
            Unary(Span(0, 3), UnaryOp.MINUS, Symbol(Span(1, 2), "x")),
        ):
            with self.subTest(node=node), self.assertRaises(ValueError):
                validate(node, "x y")

    def test_invalid_relations_and_subscripts(self):
        child = Relation(Span(0, 3), (Symbol(Span(0, 1), "x"), Number(Span(2, 3), "1")), (RelationOp.EQUAL,))
        for node in (
            Relation(Span(0, 3), child.operands, ()),
            Relation(Span(0, 3), child.operands, ("=",)),
            Relation(Span(0, 3), list(child.operands), (RelationOp.EQUAL,)),
            Binary(Span(0, 5), BinaryOp.ADD, child, Number(Span(4, 5), "2")),
            Subscript(Span(0, 3), Number(Span(0, 1), "1"), Number(Span(2, 3), "2")),
            Subscript(Span(0, 3), Symbol(Span(0, 1), "x"), Number(Span(2, 3), "1.5")),
        ):
            with self.subTest(node=node), self.assertRaises(ValueError):
                validate(node, "x=1+2")

    def test_complexity_limits_and_shared_nodes(self):
        node = Symbol(Span(MAX_DEPTH, MAX_DEPTH + 1), "x")
        for start in reversed(range(MAX_DEPTH)):
            node = Unary(Span(start, MAX_DEPTH + 1), UnaryOp.MINUS, node)
        with self.assertRaisesRegex(ValueError, "complexity"):
            validate(node, "-" * MAX_DEPTH + "x")
        operands = tuple(Number(Span(i * 2, i * 2 + 1), "1") for i in range(MAX_NODES))
        relation = Relation(Span(0, 2 * MAX_NODES - 1), operands, (RelationOp.EQUAL,) * (MAX_NODES - 1))
        with self.assertRaisesRegex(ValueError, "complexity"):
            validate(relation, "=".join("1" for _ in operands))
        shared = Symbol(Span(0, 1), "x")
        with self.assertRaisesRegex(ValueError, "shared"):
            validate(Binary(Span(0, 1), BinaryOp.MULTIPLY, shared, shared), "x")

    def test_nodes_are_immutable_and_source_is_bounded(self):
        node = Symbol(Span(0, 1), "x")
        with self.assertRaises(FrozenInstanceError):
            node.name = "y"
        for source in (None, "x\x00", "x\ud800", "x" * 32769):
            with self.subTest(source_type=type(source)), self.assertRaises(ValueError):
                validate(node, source)


if __name__ == "__main__":
    unittest.main()
