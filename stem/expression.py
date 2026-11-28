from dataclasses import dataclass
from enum import Enum
import re

from .tokenizer import GREEK, MAX_SOURCE_CHARS

AST_VERSION = "math-ast-v1"
MAX_NODES = 256
MAX_DEPTH = 32
MAX_NUMBER_CHARS = 64
SYMBOLS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
) | frozenset(GREEK) | frozenset(name.capitalize() for name in GREEK) | {"hbar", "infinity"}
NUMBER_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")


class UnaryOp(str, Enum):
    PLUS = "+"
    MINUS = "-"
    PLUS_MINUS = "+/-"
    MINUS_PLUS = "-/+"


class BinaryOp(str, Enum):
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    DOT = "dot"
    PLUS_MINUS = "+/-"
    MINUS_PLUS = "-/+"


class Function(str, Enum):
    SIN = "sin"
    COS = "cos"
    TAN = "tan"
    LOG = "log"
    LN = "ln"
    SQRT = "sqrt"
    CBRT = "cbrt"


class RelationOp(str, Enum):
    EQUAL = "="
    NOT_EQUAL = "!="
    LESS = "<"
    LESS_EQUAL = "<="
    GREATER = ">"
    GREATER_EQUAL = ">="
    PROPORTIONAL = "proportional"


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Expr:
    span: Span


@dataclass(frozen=True, slots=True)
class Number(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class Symbol(Expr):
    name: str


@dataclass(frozen=True, slots=True)
class Unary(Expr):
    op: UnaryOp
    operand: Expr


@dataclass(frozen=True, slots=True)
class Binary(Expr):
    op: BinaryOp
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Power(Expr):
    base: Expr
    exponent: Expr


@dataclass(frozen=True, slots=True)
class Subscript(Expr):
    base: Expr
    index: Expr


@dataclass(frozen=True, slots=True)
class Call(Expr):
    function: Function
    argument: Expr


@dataclass(frozen=True, slots=True)
class Group(Expr):
    operand: Expr


@dataclass(frozen=True, slots=True)
class Factorial(Expr):
    operand: Expr


@dataclass(frozen=True, slots=True)
class Relation:
    span: Span
    operands: tuple[Expr, ...]
    operators: tuple[RelationOp, ...]


Expression = Number | Symbol | Unary | Binary | Power | Subscript | Call | Group | Factorial
Tree = Expression | Relation


@dataclass(frozen=True, slots=True)
class Validation:
    nodes: int
    depth: int


def validate(tree: Tree, source: str) -> Validation:
    if not isinstance(source, str) or len(source) > MAX_SOURCE_CHARS:
        raise ValueError("Invalid expression source")
    if any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in source):
        raise ValueError("Invalid expression source character")

    count, deepest = 0, 0
    seen = set()

    def visit(node, depth, parent=None):
        nonlocal count, deepest
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("Expression complexity limit")
        deepest = max(deepest, depth)
        kind = type(node)
        if kind not in (Number, Symbol, Unary, Binary, Power, Subscript, Call, Group, Factorial, Relation):
            raise ValueError("Unsupported expression node")
        if id(node) in seen:
            raise ValueError("Expression must be a tree without shared nodes")
        seen.add(id(node))
        span = node.span
        if (type(span) is not Span or type(span.start) is not int or type(span.end) is not int
                or not 0 <= span.start < span.end <= len(source)
                or not source[span.start:span.end].strip()):
            raise ValueError("Invalid expression span")
        if parent is not None and not parent.start <= span.start < span.end <= parent.end:
            raise ValueError("Child span outside parent")

        children = ()
        if kind is Number:
            if (not isinstance(node.value, str) or len(node.value) > MAX_NUMBER_CHARS
                    or not NUMBER_PATTERN.fullmatch(node.value)):
                raise ValueError("Unsupported number")
        elif kind is Symbol:
            if not isinstance(node.name, str) or node.name not in SYMBOLS:
                raise ValueError("Unsupported symbol")
        elif kind is Unary:
            if type(node.op) is not UnaryOp:
                raise ValueError("Unsupported unary operator")
            children = (node.operand,)
        elif kind is Binary:
            if type(node.op) is not BinaryOp:
                raise ValueError("Unsupported binary operator")
            children = (node.left, node.right)
        elif kind is Power:
            children = (node.base, node.exponent)
        elif kind is Subscript:
            if type(node.base) is not Symbol or type(node.index) not in (Number, Symbol):
                raise ValueError("Unsupported subscript")
            if type(node.index) is Number and (
                    not isinstance(node.index.value, str) or not node.index.value.isascii()
                    or not node.index.value.isdigit()):
                raise ValueError("Subscript index must be an integer or symbol")
            children = (node.base, node.index)
        elif kind is Call:
            if type(node.function) is not Function:
                raise ValueError("Unsupported function")
            children = (node.argument,)
        elif kind in (Group, Factorial):
            children = (node.operand,)
        elif kind is Relation:
            if parent is not None:
                raise ValueError("Relation is allowed only at the root")
            if (type(node.operands) is not tuple or type(node.operators) is not tuple
                    or not 2 <= len(node.operands) <= MAX_NODES
                    or len(node.operators) != len(node.operands) - 1
                    or any(type(op) is not RelationOp for op in node.operators)):
                raise ValueError("Invalid relation chain")
            children = node.operands

        previous_end = span.start
        for child in children:
            visit(child, depth + 1, span)
            if child.span.start < previous_end:
                raise ValueError("Overlapping or unordered child spans")
            previous_end = child.span.end

        if kind in (Unary, Call):
            if not span.start < children[0].span.start or children[0].span.end != span.end:
                raise ValueError("Invalid prefix span")
        elif kind is Group:
            if not span.start < children[0].span.start or not children[0].span.end < span.end:
                raise ValueError("Invalid group span")
        elif kind is Factorial:
            if children[0].span.start != span.start or not children[0].span.end < span.end:
                raise ValueError("Invalid postfix span")
        elif children:
            if children[0].span.start != span.start or children[-1].span.end != span.end:
                raise ValueError("Invalid compound span")
            if kind is Relation or (kind is Binary and node.op is not BinaryOp.MULTIPLY):
                if any(left.span.end == right.span.start for left, right in zip(children, children[1:])):
                    raise ValueError("Missing operator span")

    visit(tree, 1)
    return Validation(count, deepest)


def structural_key(tree: Tree, source: str) -> tuple:
    validate(tree, source)

    def key(node):
        kind = type(node)
        if kind is Number:
            return ("number", node.value)
        if kind is Symbol:
            return ("symbol", node.name)
        if kind is Unary:
            return ("unary", node.op.value, key(node.operand))
        if kind is Binary:
            return ("binary", node.op.value, key(node.left), key(node.right))
        if kind is Power:
            return ("power", key(node.base), key(node.exponent))
        if kind is Subscript:
            return ("subscript", key(node.base), key(node.index))
        if kind is Call:
            return ("call", node.function.value, key(node.argument))
        if kind is Group:
            return key(node.operand)
        if kind is Factorial:
            return ("factorial", key(node.operand))
        return ("relation", tuple(op.value for op in node.operators),
                tuple(key(operand) for operand in node.operands))

    return key(tree)
