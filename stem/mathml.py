import re
import xml.etree.ElementTree as ET

from .dictionary import validate_latex

VERSION = "mathml-subset-v1"
NS = "{http://www.w3.org/1998/Math/MathML}"
MAX_XML_BYTES = 65536
MAX_NODES = 1024
MAX_DEPTH = 32
MAX_OUTPUT = 512
GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "λ": r"\lambda", "θ": r"\theta", "σ": r"\sigma", "μ": r"\mu",
    "ρ": r"\rho", "ω": r"\omega", "π": r"\pi", "Δ": r"\Delta",
    "Σ": r"\Sigma", "Ω": r"\Omega", "ℏ": r"\hbar",
}
OPERATORS = {
    "−": "-", "×": r"\times", "·": r"\cdot", "⋅": r"\cdot",
    "±": r"\pm", "∓": r"\mp", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "∝": r"\propto", "→": r"\to",
    "∞": r"\infty", "∂": r"\partial", "∫": r"\int", "∑": r"\sum",
    "\u2062": r"\cdot",
}
FUNCTIONS = {"sin", "cos", "tan", "log", "ln", "lim"}
WRAPPERS = {"math", "mrow", "mstyle"}
ARITY = {"mfrac": 2, "msup": 2, "msub": 2, "msubsup": 3, "mroot": 2}


class ConversionError(ValueError):
    pass


def local_name(tag):
    if not isinstance(tag, str) or not tag.startswith(NS):
        raise ConversionError("foreign_or_missing_namespace")
    return tag[len(NS):]


def parse_mathml(source):
    if len(source.encode("utf-8")) > MAX_XML_BYTES:
        raise ConversionError("xml_size_limit")
    if "<!" in source or "<?" in source:
        raise ConversionError("xml_declaration_or_markup")
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        raise ConversionError("malformed_xml") from None
    if local_name(root.tag) != "math":
        raise ConversionError("unexpected_root")
    stack = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ConversionError("xml_structure_limit")
        local_name(node.tag)
        stack.extend((child, depth + 1) for child in node)
    return root


def attributes(node, tag):
    for key, value in node.attrib.items():
        if tag == "math" and key == "class":
            continue
        if tag in {"math", "mstyle"} and key == "displaystyle" and value in {"true", "false"}:
            continue
        if tag in {"math", "mstyle"} and key == "scriptlevel" and value == "0":
            continue
        if tag == "mrow" and key == "data-mjx-texclass" and value == "ORD":
            continue
        if tag == "mo" and key == "stretchy" and value == "false":
            continue
        raise ConversionError("unsupported_attribute:" + tag + ":" + key)


def join(parts):
    result = ""
    for part in parts:
        if not part:
            continue
        if re.search(r"\\[A-Za-z]+$", result) and re.match(r"[A-Za-z]", part):
            result += " "
        result += part
        if len(result) > MAX_OUTPUT:
            raise ConversionError("latex_size_limit")
    return result


def token(node, tag):
    if len(node):
        raise ConversionError("unexpected_token_children")
    value = (node.text or "").strip()
    if not value:
        raise ConversionError("empty_token")
    if tag == "mn" and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return value
    if tag == "mi":
        if value in GREEK:
            return GREEK[value]
        if value in FUNCTIONS:
            return "\\" + value
        if re.fullmatch(r"[A-Za-z]", value):
            return value
        if value == "∞":
            return r"\infty"
    if tag == "mo":
        if value in OPERATORS:
            return OPERATORS[value]
        if re.fullmatch(r"[=+\-*/(),.<>|!:]", value):
            return value
    raise ConversionError("unsupported_token:" + tag)


def render(node):
    tag = local_name(node.tag)
    attributes(node, tag)
    if tag in {"mi", "mn", "mo"}:
        return token(node, tag)
    if tag not in WRAPPERS and tag not in ARITY and tag != "msqrt":
        raise ConversionError("unsupported_element:" + tag)
    if (node.text or "").strip() or any((child.tail or "").strip() for child in node):
        raise ConversionError("unexpected_mixed_content")
    if tag in ARITY and len(node) != ARITY[tag]:
        raise ConversionError("invalid_arity:" + tag)
    if not len(node):
        raise ConversionError("empty_container:" + tag)
    parts = [render(child) for child in node]
    if tag in WRAPPERS:
        return join(parts)
    if tag == "mfrac":
        return r"\frac{" + parts[0] + "}{" + parts[1] + "}"
    if tag == "msqrt":
        return r"\sqrt{" + join(parts) + "}"
    if tag == "mroot":
        raise ConversionError("unsupported_element:mroot")
    base = "{" + parts[0] + "}"
    if tag == "msup":
        return base + "^{" + parts[1] + "}"
    if tag == "msub":
        return base + "_{" + parts[1] + "}"
    return base + "_{" + parts[1] + "}^{" + parts[2] + "}"


def convert_mathml(source):
    latex = render(parse_mathml(source))
    try:
        return validate_latex(latex)
    except ValueError as error:
        raise ConversionError("latex_screen:" + str(error)) from None
