import re
import xml.etree.ElementTree as ET

from .dictionary import validate_latex

VERSION = "mathml-subset-v3"
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
    "ε": r"\varepsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "ν": r"\nu",
    "ξ": r"\xi",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ϵ": r"\epsilon",
    "ϑ": r"\vartheta",
    "ϕ": r"\phi",
    "ϱ": r"\varrho",
    "ς": r"\varsigma",
    "Γ": r"\Gamma",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
}
OPERATORS = {
    "−": "-", "×": r"\times", "·": r"\cdot", "⋅": r"\cdot",
    "±": r"\pm", "∓": r"\mp", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "∝": r"\propto", "→": r"\to",
    "∞": r"\infty", "∂": r"\partial", "∫": r"\int", "∑": r"\sum",
    "\u2062": r"\cdot",
    "÷": r"\div",
    "∗": r"\ast",
    "∏": r"\prod",
    "∮": r"\oint",
    "∇": r"\nabla",
    "∈": r"\in",
    "∉": r"\notin",
    "∋": r"\ni",
    "∅": r"\emptyset",
    "∪": r"\cup",
    "∩": r"\cap",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "≡": r"\equiv",
    "∼": r"\sim",
    "≃": r"\simeq",
    "≅": r"\cong",
    "≪": r"\ll",
    "≫": r"\gg",
    "↔": r"\leftrightarrow",
    "←": r"\leftarrow",
    "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow",
    "∀": r"\forall",
    "∃": r"\exists",
    "¬": r"\neg",
    "∧": r"\land",
    "∨": r"\lor",
    "⊗": r"\otimes",
    "⊕": r"\oplus",
    "∘": r"\circ",
    "⊥": r"\perp",
    "∥": r"\parallel",
    "…": r"\ldots",
    "⋯": r"\cdots",
    "∣": r"\mid",
    "[": r"\lbrack",
    "]": r"\rbrack",
    "{": r"\lbrace",
    "}": r"\rbrace",
    "⟨": r"\langle",
    "⟩": r"\rangle",
    "‖": r"\Vert",
    "⌊": r"\lfloor",
    "⌋": r"\rfloor",
    "⌈": r"\lceil",
    "⌉": r"\rceil",
    "⟹": r"\Longrightarrow",
    "⟺": r"\Longleftrightarrow",
    "↦": r"\mapsto",
    "∖": r"\setminus",
    "⋃": r"\bigcup",
    "⋂": r"\bigcap",
    "⋆": r"\star",
    "†": r"\dagger",
    "↑": r"\uparrow",
    "↓": r"\downarrow",
    "⋮": r"\vdots",
    "⋱": r"\ddots",
    "∄": r"\nexists",
    "⊤": r"\top",
    "⊖": r"\ominus",
    "∬": r"\iint",
    "∭": r"\iiint",
    "⊢": r"\vdash",
    "⊨": r"\models",
    "∴": r"\therefore",
    "∵": r"\because",
    "∉": r"\notin",
    "⊊": r"\subsetneq",
    "≺": r"\prec",
    "≻": r"\succ",
    "⪯": r"\preceq",
    "⪰": r"\succeq",
    "⪽": r"\leqslant",
    "⪾": r"\geqslant",
    "ℓ": r"\ell",
    "ℵ": r"\aleph",
}
FUNCTIONS = {"sin", "cos", "tan", "log", "ln", "lim",
             "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "cot", "sec", "csc", "exp", "min", "max", "sup", "inf", "det", "gcd"}
FUNCTIONS.update({"deg", "dim", "hom", "ker", "arg", "Pr", "lg"})
BLACKBOARD = {"ℝ": "R", "ℤ": "Z", "ℂ": "C", "ℕ": "N", "ℙ": "P", "ℚ": "Q", "ℍ": "H"}
TEX_CLASSES = {"ORD": "mathord", "INNER": "mathinner", "OPEN": "mathopen",
               "CLOSE": "mathclose", "OP": "mathop", "REL": "mathrel",
               "BIN": "mathbin", "PUNCT": "mathpunct"}
SPACES = {"0.167em": r"\,", "-0.167em": r"\!", "0.278em": r"\;",
          "1em": r"\quad", "2em": r"\qquad", "0.333em": r"\,\,",
          "0.444em": r"\;\,"}
ACCENTS = {"¯": "bar", "‾": "overline", "̂": "hat", "˙": "dot",
           "¨": "ddot", "⃗": "vec"}
LIMIT_OPERATORS = {r"\sum", r"\prod", r"\bigcup", r"\bigcap", r"\int",
                   r"\oint", r"\iint", r"\iiint", r"\lim", r"\min",
                   r"\max", r"\sup", r"\inf"}
IDENTIFIER_STYLES = {
    "normal": "mathrm",
    "bold": "mathbf",
    "italic": "mathit",
    "double-struck": "mathbb",
    "script": "mathcal",
    "fraktur": "mathfrak",
    "sans-serif": "mathsf",
    "monospace": "mathtt",
}
WRAPPERS = {"math", "mrow", "mstyle"}
ARITY = {"mfrac": 2, "msup": 2, "msub": 2, "msubsup": 3, "mroot": 2,
         "mover": 2, "munder": 2, "munderover": 3}


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
        if any("\ufffd" in value for value in (node.text or "", node.tail or "", *node.attrib.values())):
            raise ConversionError("source_replacement_character")
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
        if tag in {"mrow", "mi", "mo"} and key == "data-mjx-texclass" and value in TEX_CLASSES:
            continue
        if tag == "mi" and key == "mathvariant" and value in IDENTIFIER_STYLES:
            continue
        if tag == "mo" and key == "stretchy" and value == "false":
            continue
        if tag == "mo" and key in {"lspace", "rspace"} and value in {"0", "0.278em", "2.5pt"}:
            continue
        if tag == "mo" and key == "movablelimits" and value == "false":
            continue
        if tag == "mspace" and key == "width" and value in SPACES:
            continue
        if tag == "mtext" and key == "mathvariant" and value == "normal":
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
    if tag == "mtext":
        if re.fullmatch(r"[A-Za-z0-9 .,():;!+/-]{1,128}", node.text or ""):
            return r"\text{" + node.text + "}"
        raise ConversionError("unsupported_text")
    if tag == "mi":
        variant = node.get("mathvariant")
        if value in BLACKBOARD and variant in {None, "normal", "double-struck"}:
            return r"\mathbb{" + BLACKBOARD[value] + "}"
        if value in OPERATORS and variant is None:
            return OPERATORS[value]
        if node.get("data-mjx-texclass") == "OP" and variant in {None, "normal"}:
            if value in FUNCTIONS:
                return "\\" + value
            if re.fullmatch(r"[A-Za-z]{1,32}", value):
                return r"\operatorname{" + value + "}"
        if value in {"ℓ", "ℵ"} and variant is None:
            return OPERATORS[value]
        if variant is not None:
            if variant == "normal" and value in FUNCTIONS:
                return "\\" + value
            if not re.fullmatch(r"[A-Za-z]+", value):
                raise ConversionError("unsupported_styled_identifier")
            if variant != "normal" and len(value) != 1:
                raise ConversionError("unsupported_styled_identifier")
            if variant in {"double-struck", "script"} and not re.fullmatch(r"[A-Z]", value):
                raise ConversionError("unsupported_styled_identifier")
            return "\\" + IDENTIFIER_STYLES[variant] + "{" + value + "}"
        if value in GREEK:
            return GREEK[value]
        if value in FUNCTIONS:
            return "\\" + value
        if re.fullmatch(r"[A-Za-z]", value):
            return value
        if value == "∞":
            return r"\infty"
    if tag == "mo":
        if value in FUNCTIONS:
            return "\\" + value
        if value == ":=":
            return ":="
        if value in GREEK:
            return GREEK[value]
        if value in OPERATORS:
            return OPERATORS[value]
        if re.fullmatch(r"[=+\-*/(),.<>|!:;]", value):
            return value
    raise ConversionError("unsupported_token:" + tag)


def apply_tex_class(node, latex):
    tex_class = node.get("data-mjx-texclass")
    if tex_class in {None, "ORD"}:
        return latex
    if tex_class == "OP" and (latex in LIMIT_OPERATORS or latex.startswith(r"\operatorname{")
                               or latex in {"\\" + name for name in FUNCTIONS}):
        return latex
    return "\\" + TEX_CLASSES[tex_class] + "{" + latex + "}"


def wrapper_parts(node):
    parts = []
    children = list(node)
    for index, child in enumerate(children):
        if local_name(child.tag) == "mo" and (child.text or "").strip() == "\u2061":
            attributes(child, "mo")
            if len(child) or index == 0 or index + 1 == len(children):
                raise ConversionError("ambiguous_function_application")
            previous, following = children[index - 1], children[index + 1]
            if (local_name(previous.tag) != "mi" or local_name(following.tag) != "mo"
                    or (following.text or "").strip() != "("):
                raise ConversionError("ambiguous_function_application")
            continue
        parts.append(render(child))
    return parts


def render(node):
    tag = local_name(node.tag)
    attributes(node, tag)
    if tag in {"mi", "mn", "mo", "mtext"}:
        return apply_tex_class(node, token(node, tag))
    if tag == "mspace":
        if len(node) or (node.text or "").strip() or node.get("width") not in SPACES:
            raise ConversionError("unsupported_space")
        return SPACES[node.get("width")]
    if tag not in WRAPPERS and tag not in ARITY and tag != "msqrt":
        raise ConversionError("unsupported_element:" + tag)
    if (node.text or "").strip() or any((child.tail or "").strip() for child in node):
        raise ConversionError("unexpected_mixed_content")
    if tag in ARITY and len(node) != ARITY[tag]:
        raise ConversionError("invalid_arity:" + tag)
    if not len(node):
        raise ConversionError("empty_container:" + tag)
    if tag in WRAPPERS:
        return apply_tex_class(node, join(wrapper_parts(node)))
    if tag == "mover" and local_name(node[1].tag) == "mo":
        accent = (node[1].text or "").strip()
        if accent in ACCENTS:
            attributes(node[1], "mo")
            if len(node[1]):
                raise ConversionError("unexpected_token_children")
            return "\\" + ACCENTS[accent] + "{" + render(node[0]) + "}"
    parts = [render(child) for child in node]
    if tag in {"munder", "mover", "munderover"}:
        if parts[0] not in LIMIT_OPERATORS:
            raise ConversionError("unsupported_limit_base:" + tag)
        base = parts[0] + r"\limits"
        if tag == "munder":
            return base + "_{" + parts[1] + "}"
        if tag == "mover":
            return base + "^{" + parts[1] + "}"
        return base + "_{" + parts[1] + "}^{" + parts[2] + "}"
    if tag == "mfrac":
        return r"\frac{" + parts[0] + "}{" + parts[1] + "}"
    if tag == "msqrt":
        return r"\sqrt{" + join(parts) + "}"
    if tag == "mroot":
        if not re.fullmatch(r"[A-Za-z]|[0-9]{1,4}", parts[1]):
            raise ConversionError("unsupported_root_index")
        return r"\sqrt[" + parts[1] + "]{" + parts[0] + "}"
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
