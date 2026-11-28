from contextlib import contextmanager

from .expression import (
    Binary, BinaryOp, Call, Factorial, Function, Group, Number, Power,
    Relation, RelationOp, Span, Subscript, Symbol, Tree, Unary, UnaryOp, validate,
)
from .tokenizer import Form, Kind, tokenize

PARSER_VERSION = "restricted-math-v1"
MAX_PARSE_CHARS = 4096
MAX_PARSE_TOKENS = 256
MAX_NESTING = 24
ORDINAL_POWERS = {"second": "2", "third": "3", "fourth": "4", "fifth": "5",
                  "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10"}
ADDITIVE = frozenset({"+", "-", "+/-", "-/+"})
MULTIPLICATIVE = frozenset({"*", "/", "dot"})


class ParseError(ValueError):
    pass


def span(left, right):
    return Span(left.span.start, right.span.end)


def token_span(token):
    return Span(token.start, token.end)


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0
        self.nesting = 0

    @contextmanager
    def nested(self):
        if self.nesting >= MAX_NESTING:
            raise ParseError("nesting_limit")
        self.nesting += 1
        try:
            yield
        finally:
            self.nesting -= 1

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def is_token(self, kind, value=None):
        token = self.peek()
        return token is not None and token.kind == kind and (value is None or token.value == value)

    def take(self):
        token = self.peek()
        if token is None:
            raise ParseError("unexpected_end")
        self.position += 1
        return token

    def require(self, kind, value=None):
        if not self.is_token(kind, value):
            raise ParseError("expected_" + kind.value)
        return self.take()

    def word(self, value):
        token = self.peek()
        return token is not None and token.kind == Kind.WORD and token.value.lower() == value

    def boundary(self):
        return (self.peek() is None or self.is_token(Kind.RELATION)
                or self.is_token(Kind.GROUP, ")") or self.is_token(Kind.GROUP, "]")
                or self.is_token(Kind.SCOPE, "end_exponent"))

    def tree(self):
        operands = [self.sum()]
        operators = []
        while self.is_token(Kind.RELATION):
            operators.append(RelationOp(self.take().value))
            operands.append(self.sum())
        if self.peek() is not None:
            raise ParseError("unconsumed_tokens")
        if not operators:
            return operands[0]
        return Relation(span(operands[0], operands[-1]), tuple(operands), tuple(operators))

    def sum(self):
        left, division = self.product()
        while self.is_token(Kind.OPERATOR) and self.peek().value in ADDITIVE:
            op = self.take()
            right, right_division = self.product()
            if division or right_division:
                raise ParseError("ambiguous_spoken_fraction")
            left = Binary(span(left, right), BinaryOp(op.value), left, right)
        return left

    def product(self):
        left = self.unary()
        count = 0
        spoken_division = False
        while True:
            token = self.peek()
            implicit = (type(left) is Number and token is not None
                        and token.start == left.span.end
                        and token.form is Form.SYMBOLIC
                        and (token.kind == Kind.SYMBOL
                             or (token.kind == Kind.GROUP and token.value == "(")))
            if implicit:
                op = BinaryOp.MULTIPLY
                current_division = False
            elif self.is_token(Kind.OPERATOR) and token.value in MULTIPLICATIVE:
                op = BinaryOp(self.take().value)
                current_division = op is BinaryOp.DIVIDE and token.form is Form.SPOKEN
            else:
                break
            if spoken_division or (current_division and count):
                raise ParseError("ambiguous_spoken_fraction")
            right = self.unary()
            if current_division and type(right) not in (Number, Symbol, Group, Subscript):
                raise ParseError("ambiguous_spoken_denominator")
            left = Binary(span(left, right), op, left, right)
            count += 1
            spoken_division = current_division
        return left, spoken_division

    def unary(self):
        if self.is_token(Kind.OPERATOR) and self.peek().value in ADDITIVE:
            token = self.take()
            with self.nested():
                operand = self.unary()
            if token.form is Form.SPOKEN and type(operand) in (Power, Factorial):
                raise ParseError("ambiguous_spoken_sign")
            return Unary(Span(token.start, operand.span.end), UnaryOp(token.value), operand)
        return self.power()

    def power(self):
        base = self.atom()
        if self.is_token(Kind.SUBSCRIPT) or self.is_token(Kind.SCOPE, "subscript"):
            if type(base) is not Symbol:
                raise ParseError("unsupported_subscript_base")
            marker = self.take()
            if marker.kind == Kind.SUBSCRIPT:
                index = Number(token_span(marker), marker.value)
            else:
                index = self.scalar()
            base = Subscript(span(base, index), base, index)
        if self.word("factorial") or self.is_token(Kind.PUNCTUATION, "!"):
            marker = self.take()
            if marker.value == "!" and marker.start != base.span.end:
                raise ParseError("ambiguous_factorial_punctuation")
            base = Factorial(Span(base.span.start, marker.end), base)
        if self.is_token(Kind.EXPONENT):
            exponent = self.take()
            return Power(Span(base.span.start, exponent.end), base,
                         Number(token_span(exponent), exponent.value))
        if self.is_token(Kind.POWER) or self.is_token(Kind.POWER_HINT):
            marker = self.take()
            with self.nested():
                exponent = self.exponent(marker)
            return Power(span(base, exponent), base, exponent)
        return base

    def exponent(self, marker):
        if marker.form is Form.SYMBOLIC:
            return self.unary()
        if self.is_token(Kind.GROUP, "(") or self.is_token(Kind.GROUP, "["):
            return self.group()
        if self.is_token(Kind.SCOPE, "quantity"):
            opening = self.take()
            operand = self.sum()
            ending = self.require(Kind.SCOPE, "end_exponent")
            return Group(Span(opening.start, ending.end), operand)
        token = self.peek()
        if (token is not None and token.kind == Kind.WORD
                and token.value.lower() in ORDINAL_POWERS):
            ordinal = self.take()
            if not self.word("power"):
                raise ParseError("ambiguous_ordinal_power")
            ending = self.take()
            return Number(Span(ordinal.start, ending.end), ORDINAL_POWERS[ordinal.value.lower()])
        exponent = self.scalar()
        if not self.boundary():
            raise ParseError("ambiguous_spoken_exponent")
        return exponent

    def scalar(self):
        token = self.take()
        if token.kind == Kind.NUMBER:
            return Number(token_span(token), token.value)
        if token.kind == Kind.SYMBOL:
            return Symbol(token_span(token), token.value)
        if token.kind == Kind.MODIFIER and token.value in ("uppercase", "lowercase"):
            name = self.require(Kind.SYMBOL)
            if name.value in ("hbar", "infinity"):
                raise ParseError("unsupported_case_modifier")
            value = name.value.capitalize() if token.value == "uppercase" else name.value.lower()
            return Symbol(Span(token.start, name.end), value)
        raise ParseError("expected_scalar")

    def group(self):
        opening = self.require(Kind.GROUP)
        if opening.value not in ("(", "["):
            raise ParseError("unexpected_closing_group")
        with self.nested():
            operand = self.sum()
        closing = self.require(Kind.GROUP, ")" if opening.value == "(" else "]")
        return Group(Span(opening.start, closing.end), operand)

    def atom(self):
        if self.is_token(Kind.GROUP, "(") or self.is_token(Kind.GROUP, "["):
            return self.group()
        if self.is_token(Kind.FUNCTION):
            token = self.take()
            if self.word("of"):
                self.take()
            if self.is_token(Kind.GROUP, "(") or self.is_token(Kind.GROUP, "["):
                argument = self.group()
            else:
                if self.is_token(Kind.OPERATOR) and self.peek().value in ("+", "-"):
                    sign = self.take()
                    operand = self.scalar()
                    argument = Unary(Span(sign.start, operand.span.end), UnaryOp(sign.value), operand)
                else:
                    argument = self.scalar()
                if not self.boundary():
                    raise ParseError("ambiguous_function_argument")
            return Call(Span(token.start, argument.span.end), Function(token.value), argument)
        return self.scalar()


def parse_expression(source: str) -> Tree:
    if not isinstance(source, str) or len(source) > MAX_PARSE_CHARS:
        raise ParseError("source_limit")
    try:
        tokens = tokenize(source)
    except ValueError as error:
        raise ParseError("invalid_source") from error
    if any(token.kind == Kind.WHITESPACE and any(char not in " \t" for char in token.source_text)
           for token in tokens):
        raise ParseError("unsupported_whitespace")
    significant = tuple(token for token in tokens if token.kind != Kind.WHITESPACE)
    if not significant or len(significant) > MAX_PARSE_TOKENS:
        raise ParseError("token_count")
    try:
        tree = _Parser(significant).tree()
        if tree.span != Span(significant[0].start, significant[-1].end):
            raise ParseError("incomplete_source_span")
        validate(tree, source)
    except ParseError:
        raise
    except ValueError as error:
        raise ParseError("invalid_structure") from error
    return tree
