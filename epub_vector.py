import math
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from epub_assets import MATH, SVG


RENDERER = Path(__file__).resolve().parent / "delivery_renderer"
MAX_XML = 256 * 1024
MAX_NODES = 4096
MAX_DEPTH = 48
MAX_PNG = 1024 * 1024
TIMEOUT = 20
NUMBER = r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
NUMBERS = re.compile(r"[\s,0-9.eE+\-]+")
PATH = re.compile(r"[MmZzLlHhVvCcSsQqTtAa0-9.,+\-eE \t\n\r]+")
TRANSFORM = re.compile(r"(?:\s*(?:translate|scale|rotate|matrix|skewX|skewY)\([\s,0-9.eE+\-]+\)\s*)+")
COLOR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?")
COLORS = frozenset("none currentColor black white red green blue yellow gray grey orange purple brown navy teal silver lime maroon aqua fuchsia".split())
SHAPES = frozenset("g path rect line polygon polyline circle ellipse".split())
GEOMETRY = frozenset("x y x1 y1 x2 y2 width height rx ry cx cy r stroke-width stroke-dashoffset opacity fill-opacity stroke-opacity".split())
MATH_LEAVES = frozenset(("mi", "mn", "mo", "mtext", "ms"))
MATH_ARITY = {"mfrac": 2, "mroot": 2, "msub": 2, "msup": 2, "msubsup": 3,
              "munder": 2, "mover": 2, "munderover": 3}
MATH_GROUPS = frozenset(("math", "mrow", "msqrt", "mtable", "mtr", "mtd"))
VARIANTS = frozenset("normal bold italic bold-italic double-struck fraktur bold-fraktur script bold-script sans-serif bold-sans-serif sans-serif-italic sans-serif-bold-italic monospace".split())


class VectorRejected(ValueError):
    pass


class VectorUnavailable(RuntimeError):
    pass


def parse(raw, namespace, root_name):
    if not 0 < len(raw) <= MAX_XML:
        raise VectorRejected("xml_size")
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text or "<!" in text or "<?" in text.removeprefix('<?xml version="1.0"?>'):
            raise VectorRejected("xml_markup")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError):
        raise VectorRejected("xml_parse") from None
    if root.tag != namespace + root_name:
        raise VectorRejected("xml_root")
    stack, count = [(root, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise VectorRejected("xml_complexity")
        if not node.tag.startswith(namespace):
            raise VectorRejected("xml_namespace")
        if len(node.attrib) > 32 or any(len(v) > MAX_XML for v in node.attrib.values()):
            raise VectorRejected("xml_attributes")
        stack.extend((child, depth + 1) for child in node)
    return root


def serialize(root, namespace):
    for node in root.iter():
        node.tag = node.tag.removeprefix(namespace)
    root.set("xmlns", namespace[1:-1])
    return ET.tostring(root, encoding="utf-8")


def mathml(raw):
    root = parse(raw, MATH, "math")
    for node in list(root.iter()):
        if node.tag != MATH + "semantics":
            continue
        if (node.attrib or (node.text or "").strip() or len(node) < 2
                or node[0].tag in (MATH + "annotation", MATH + "annotation-xml")):
            raise VectorRejected("mathml_semantics")
        for annotation in list(node)[1:]:
            if (annotation.tag != MATH + "annotation" or len(annotation)
                    or set(annotation.attrib) != {"encoding"}
                    or annotation.get("encoding") not in ("application/x-tex", "text/plain")
                    or (annotation.tail or "").strip()):
                raise VectorRejected("mathml_annotation")
            node.remove(annotation)
        node.tag = MATH + "mrow"
    for node in root.iter():
        tag = node.tag.removeprefix(MATH)
        if tag not in MATH_GROUPS and tag not in MATH_LEAVES and tag not in MATH_ARITY:
            raise VectorRejected("mathml_element")
        if tag == "math" and node is not root:
            raise VectorRejected("mathml_nested_root")
        if (node.tail or "").strip():
            raise VectorRejected("mathml_mixed_text")
        if tag in MATH_LEAVES:
            if len(node) or len(node.text or "") > 512:
                raise VectorRejected("mathml_token")
        elif (node.text or "").strip() or (tag in MATH_ARITY and len(node) != MATH_ARITY[tag]):
            raise VectorRejected("mathml_structure")
        if tag in MATH_GROUPS and not len(node):
            raise VectorRejected("mathml_empty")
        if tag == "mtable" and any(child.tag != MATH + "mtr" for child in node):
            raise VectorRejected("mathml_table")
        if tag == "mtr" and any(child.tag != MATH + "mtd" for child in node):
            raise VectorRejected("mathml_table")
        for key, value in node.attrib.items():
            if key == "display" and node is root and value in ("block", "inline"):
                continue
            if key == "mathvariant" and tag in MATH_LEAVES and value in VARIANTS:
                continue
            if key in ("stretchy", "symmetric", "fence", "separator", "largeop", "movablelimits") and tag == "mo" and value in ("true", "false"):
                continue
            if key in ("accent", "accentunder") and tag in ("mover", "munder", "munderover") and value in ("true", "false"):
                continue
            raise VectorRejected("mathml_attribute")
    return serialize(root, MATH)


def numbers(value, limit=100000):
    result = [float(item) for item in re.findall(NUMBER, value)]
    if not result or any(not math.isfinite(n) or abs(n) > limit for n in result):
        raise VectorRejected("svg_numeric_range")
    return result


def numeric_list(value):
    if not NUMBERS.fullmatch(value):
        raise VectorRejected("svg_numeric")
    parts = re.split(r"[\s,]+", value.strip())
    if any(not re.fullmatch(NUMBER, part) for part in parts):
        raise VectorRejected("svg_numeric")
    return numbers(value)


def path_data(value):
    commands = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
                "Q": 4, "T": 2, "A": 7, "Z": 0}
    pattern = re.compile(NUMBER + r"|[MmZzLlHhVvCcSsQqTtAa]")
    tokens, previous = [], 0
    for match in pattern.finditer(value):
        if value[previous:match.start()].strip(" ,\t\n\r"):
            raise VectorRejected("svg_path_syntax")
        tokens.append(match.group())
        previous = match.end()
    if not tokens or tokens[0] not in ("M", "m") or value[previous:].strip(" ,\t\n\r"):
        raise VectorRejected("svg_path_syntax")
    command, params = None, []

    def validate():
        if command is None:
            return
        arity = commands[command.upper()]
        if (arity == 0 and params) or (arity and (not params or len(params) % arity)):
            raise VectorRejected("svg_path_arity")
        if command.upper() == "A":
            for i in range(0, len(params), 7):
                if params[i+3] not in ("0", "1") or params[i+4] not in ("0", "1"):
                    raise VectorRejected("svg_arc_flag")

    for token in tokens:
        if token.upper() in commands and len(token) == 1:
            validate()
            command, params = token, []
        else:
            scalar(token)
            params.append(token)
    validate()


def scalar(value):
    if not re.fullmatch(NUMBER, value):
        raise VectorRejected("svg_numeric")
    return numbers(value)[0]


def svg(raw, *, generated=False):
    root = parse(raw, SVG, "svg")
    view = root.get("viewBox")
    if view is None or not NUMBERS.fullmatch(view):
        raise VectorRejected("svg_viewbox")
    box = numeric_list(view)
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        raise VectorRejected("svg_viewbox")
    width, height = box[2:]
    if generated:
        width, height = width * 0.032, height * 0.032
    elif "width" in root.attrib or "height" in root.attrib:
        if "width" not in root.attrib or "height" not in root.attrib:
            raise VectorRejected("svg_viewport")
        width, height = (scalar(root.get(key).removesuffix("px")) for key in ("width", "height"))
        if width <= 0 or height <= 0:
            raise VectorRejected("svg_viewport")
    scale = min(1, 1024 / width, 600 / height)
    width, height = max(1, math.floor(width * scale)), max(1, math.floor(height * scale))
    shapes = 0
    for node in root.iter():
        tag = node.tag.removeprefix(SVG)
        if node is not root and tag not in SHAPES:
            raise VectorRejected("svg_element")
        if (node.text or "").strip() or (node.tail or "").strip():
            raise VectorRejected("svg_text")
        if node is not root and tag != "g":
            shapes += 1
            if len(node):
                raise VectorRejected("svg_shape_children")
        for key, val in list(node.attrib.items()):
            if node is root and key in ("viewBox", "width", "height"):
                del node.attrib[key]
            elif generated and key.startswith("data-"):
                if key == "data-mml-node" and val == "merror":
                    raise VectorRejected("mathml_error")
                if key in ("data-frame", "data-line", "data-background"):
                    raise VectorRejected("svg_styling_required")
                del node.attrib[key]
            elif generated and key in ("role", "focusable", "aria-hidden", "aria-label"):
                del node.attrib[key]
            elif generated and node is root and key == "style" and re.fullmatch(r"\s*vertical-align:\s*[-0-9.]+ex;?\s*", val):
                del node.attrib[key]
            elif key in GEOMETRY:
                scalar(val)
            elif key == "d" and tag == "path" and PATH.fullmatch(val):
                path_data(val)
            elif key == "points" and tag in ("polygon", "polyline") and NUMBERS.fullmatch(val):
                coordinates = numeric_list(val)
                if len(coordinates) < 4 or len(coordinates) % 2:
                    raise VectorRejected("svg_points")
            elif key == "transform" and TRANSFORM.fullmatch(val):
                arities = {"translate": (1, 2), "scale": (1, 2), "rotate": (1, 3),
                           "matrix": (6,), "skewX": (1,), "skewY": (1,)}
                for name, values in re.findall(r"(\w+)\(([^)]+)\)", val):
                    if len(numeric_list(values)) not in arities[name]:
                        raise VectorRejected("svg_transform")
            elif key in ("fill", "stroke") and (val in COLORS or COLOR.fullmatch(val)):
                if val == "currentColor":
                    if not generated:
                        raise VectorRejected("svg_inherited_color")
                    node.set(key, "black")
            elif key in ("stroke-linecap", "stroke-linejoin") and val in ("round", "butt", "square", "miter", "bevel"):
                pass
            elif key in ("fill-rule", "clip-rule") and val in ("nonzero", "evenodd"):
                pass
            else:
                raise VectorRejected("svg_attribute")
    if not shapes:
        raise VectorRejected("svg_empty")
    root.set("viewBox", " ".join(format(n, ".12g") for n in box))
    root.set("width", str(width))
    root.set("height", str(height))
    return serialize(root, SVG)


def run_worker(mode, payload):
    node = shutil.which("node")
    if not node:
        raise VectorUnavailable("Node.js 24 and delivery renderer dependencies are required")
    try:
        result = subprocess.run([node, "--max-old-space-size=384", str(RENDERER / "worker.mjs"), mode],
                                cwd=RENDERER, input=payload, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise VectorRejected("vector_timeout") from None
    if result.returncode == 2:
        raise VectorRejected("vector_render_failed")
    if result.returncode != 0:
        raise VectorUnavailable("Vector renderer failed; install the pinned delivery renderer dependencies")
    maximum = MAX_XML if mode == "mathml" else MAX_PNG
    if not 0 < len(result.stdout) <= maximum:
        raise VectorRejected("vector_output_size")
    return result.stdout


def render_vector(asset):
    if asset["media_type"] == "application/mathml+xml":
        source = mathml(asset["payload"])
        sanitized = svg(run_worker("mathml", source), generated=True)
    elif asset["media_type"] == "image/svg+xml":
        sanitized = svg(asset["payload"])
    else:
        raise VectorRejected("unsupported_vector")
    return run_worker("svg", sanitized)
