import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

from .dictionary import COMMANDS

RENDERER = Path(__file__).resolve().parent / "renderer"
SVG_NS = "http://www.w3.org/2000/svg"
SCHEMA = "fitbaus.stem.renderer-qualification/v1"
MAX_INPUT = 16 * 1024 * 1024
MAX_TEX = 1024
MAX_SVG = 256 * 1024
MAX_PNG = 1024 * 1024
BATCH = 16
TIMEOUT = 60
MAX_WIDTH = 1600
MAX_HEIGHT = 800
TEX_COMMANDS = COMMANDS | frozenset("""
boldsymbol begin end choose bigl bigr Bigl Bigr big Big bigg Bigg
colon dots dotsc dotsb dotsm dotsi dotso tfrac dfrac le ge ne over
implies iff rightarrow longrightarrow longleftarrow leftrightarrow
mbox vert lvert rvert lVert rVert langle rangle not smallsetminus
underbrace overbrace overset underset binom dbinom tbinom
displaystyle textstyle scriptstyle scriptscriptstyle
mathstrut phantom hphantom vphantom notag nonumber
""".split()) | frozenset({",", ";", "!", " ", "{", "}", "\\", "|", ":"})
ENVIRONMENTS = frozenset({"aligned", "cases", "pmatrix", "bmatrix", "matrix",
                          "smallmatrix", "vmatrix", "Vmatrix", "array", "align", "align*"})
SHAPES = frozenset({"svg", "g", "path", "rect", "line", "polygon", "polyline", "circle", "ellipse"})
NUMERIC = frozenset({"x", "y", "x1", "y1", "x2", "y2", "width", "height", "rx", "ry",
                     "cx", "cy", "r", "stroke-width", "stroke-dashoffset"})
NUMBERS = re.compile(r"[-+0-9.eE, ]+")
TRANSFORM = re.compile(r"(?:\s*(?:translate|scale|rotate|matrix|skewX|skewY)\([-+0-9.eE, ]+\)\s*)+")
PATH_DATA = re.compile(r"[MmZzLlHhVvCcSsQqTtAa0-9.,+\-eE \t\n]+")
SHA = re.compile(r"[a-f0-9]{64}")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def preflight(tex):
    if not isinstance(tex, str) or not 1 <= len(tex) <= MAX_TEX:
        raise ValueError("tex_size")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in tex) or "\ufffd" in tex:
        raise ValueError("tex_control_character")
    if any(c in tex for c in ("%", "$", "#", "\x7f")):
        raise ValueError("tex_disallowed_character")
    for match in re.finditer(r"\\([A-Za-z]+|[\s\S])?", tex):
        if match.group(1) not in TEX_COMMANDS:
            raise ValueError("tex_command:" + str(match.group(1)))
        if match.group(1) in {"begin", "end"}:
            env = re.match(r"\s*\{([^{}]+)\}", tex[match.end():])
            if not env or env.group(1) not in ENVIRONMENTS:
                raise ValueError("tex_environment")
    return tex


def load_corpus(directory):
    directory = Path(directory)
    with (directory / "recovery.json").open("rb") as stream:
        report = json.loads(stream.read(MAX_INPUT + 1))
    if report.get("schema") != "fitbaus.stem.original-tex/v1" or report.get("complete") is not True:
        raise ValueError("Complete original TeX recovery required")
    path = directory / "original-tex.jsonl"
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("Corpus size limit")
    source = report["source_sha256"]
    if not SHA.fullmatch(source):
        raise ValueError("Invalid source digest")
    unique = defaultdict(list)
    statements = set()
    count = 0
    for line in raw.splitlines():
        row = json.loads(line)
        tex = row["latex"]
        statement = row["statement_id"]
        if (row.get("status") != "candidate_only" or row.get("source") != "wikidata"
                or row.get("license") != "CC0-1.0" or row.get("source_sha256") != source
                or row.get("formula_sha256") != sha(tex.encode("utf-8"))
                or statement in statements or not isinstance(row["labels"], list)
                or not all(isinstance(label, str) for label in row["labels"])):
            raise ValueError("Invalid source row or duplicate statement")
        statements.add(statement)
        unique[tex].append(row)
        count += 1
    if count != report["candidate_statements"] or len(unique) != report["unique_exact_latex"]:
        raise ValueError("Corpus counts differ from recovery report")
    return source, sha(raw), unique


def safe_svg(value):
    raw = value.encode("utf-8")
    if len(raw) > MAX_SVG or b"<!" in raw or b"<?" in raw:
        raise ValueError("svg_size_or_markup")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("svg_xml") from error
    if root.tag != "{" + SVG_NS + "}svg":
        raise ValueError("svg_root")
    try:
        view = [float(n) for n in root.attrib["viewBox"].split()]
        if len(view) != 4 or not all(math.isfinite(n) and abs(n) <= 100000 for n in view):
            raise ValueError
        if view[2] <= 0 or view[3] <= 0:
            raise ValueError
        width, height = math.ceil(view[2] * 0.032), math.ceil(view[3] * 0.032)
    except (KeyError, ValueError, OverflowError):
        raise ValueError("svg_viewbox") from None
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise ValueError("svg_dimensions")
    paths = 0
    for count, node in enumerate(root.iter(), 1):
        if count > 8192:
            raise ValueError("svg_node_limit")
        tag = node.tag.removeprefix("{" + SVG_NS + "}")
        if node.tag != "{" + SVG_NS + "}" + tag or tag not in SHAPES:
            raise ValueError("svg_element:" + tag)
        if (node.text or "").strip() or (node.tail or "").strip():
            raise ValueError("svg_text")
        if tag == "path":
            paths += 1
        for key, val in list(node.attrib.items()):
            if key in {"data-frame", "data-line", "data-background", "class"}:
                raise ValueError("svg_styling_required")
            if key == "data-mml-node" and val == "merror":
                raise ValueError("svg_error_node")
            if key.startswith("data-") or key in {"role", "focusable", "aria-hidden", "aria-label"}:
                del node.attrib[key]
            elif node is root and key in {"width", "height", "viewBox", "style"}:
                if key == "style" and not re.fullmatch(r"\s*vertical-align:\s*[-0-9.]+ex;?\s*", val):
                    raise ValueError("svg_root_style")
                del node.attrib[key]
            elif key in NUMERIC and NUMBERS.fullmatch(val):
                if not all(math.isfinite(float(n)) and abs(float(n)) <= 100000
                           for n in re.split(r"[, ]+", val.strip()) if n):
                    raise ValueError("svg_numeric_range")
            elif key == "d" and PATH_DATA.fullmatch(val):
                pass
            elif key == "points" and NUMBERS.fullmatch(val):
                pass
            elif key == "transform" and TRANSFORM.fullmatch(val):
                pass
            elif key in {"fill", "stroke"} and val in {"currentColor", "none", "black", "white", "#000", "#fff"}:
                if val != "none":
                    node.set(key, "#ffffff")
            elif key in {"stroke-linecap", "stroke-linejoin"} and val in {"round", "butt", "square", "miter", "bevel"}:
                pass
            else:
                raise ValueError("svg_attribute:" + key)
    if not paths:
        raise ValueError("svg_no_paths")
    root.set("viewBox", " ".join(format(n, ".12g") for n in view))
    root.set("width", str(width))
    root.set("height", str(height))
    root.set("fill", "#ffffff")
    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="unicode"), width, height


def run_batch(mode, items):
    if not items:
        return {}
    try:
        result = subprocess.run(
            ["node", "--max-old-space-size=384", str(RENDERER / "worker.mjs"), mode],
            input=json.dumps(items, ensure_ascii=True).encode("utf-8"),
            capture_output=True, timeout=TIMEOUT, cwd=RENDERER, check=True,
        )
    except subprocess.TimeoutExpired:
        if len(items) == 1:
            return {items[0]["id"]: {"error": "worker_timeout"}}
        half = len(items) // 2
        return run_batch(mode, items[:half]) | run_batch(mode, items[half:])
    except subprocess.CalledProcessError as error:
        raise RuntimeError("Renderer worker failed: " + error.stderr.decode("utf-8", "replace")[-2000:]) from error
    if len(result.stdout) > BATCH * 2 * MAX_PNG:
        raise RuntimeError("Renderer output limit")
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    expected = {item["id"] for item in items}
    if len(rows) != len(expected) or {row["id"] for row in rows} != expected:
        raise RuntimeError("Renderer response identity mismatch")
    return {row["id"]: row for row in rows}


def png_bytes(value, width, height):
    data = base64.b64decode(value, validate=True)
    if (len(data) > MAX_PNG or len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n"
            or data[12:16] != b"IHDR" or struct.unpack(">II", data[16:24]) != (width, height)):
        raise ValueError("png_invalid")
    return data


def qualify(directory, output, limit=None):
    source, corpus_hash, formulas = load_corpus(directory)
    output = Path(output).resolve()
    source_dir = Path(directory).resolve()
    if output == source_dir or source_dir in output.parents:
        raise ValueError("Output must be separate from source corpus")
    if not shutil.which("node"):
        raise RuntimeError("Node.js 22 or newer is required for maintainer qualification")
    lock = RENDERER / "package-lock.json"
    if not lock.is_file():
        raise RuntimeError("Run npm install --ignore-scripts in stem/renderer first")
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be positive")
    selected = sorted(formulas, key=lambda tex: sha(tex.encode("utf-8")))[:limit]
    probe = run_batch("svg", [{"id": "probe", "value": "E=mc^2"}])["probe"]
    if "error" in probe:
        raise RuntimeError("Renderer smoke test failed: " + probe["error"])
    svg, width, height = safe_svg(probe["value"])
    probe_png = run_batch("png", [{"id": "probe", "value": svg}])["probe"]
    if "error" in probe_png:
        raise RuntimeError("PNG smoke test failed: " + probe_png["error"])
    png_bytes(probe_png["value"], width, height)
    output.mkdir(parents=True, exist_ok=False)
    assets = output / "assets"
    assets.mkdir()
    outcomes = Counter()
    records = []
    for offset in range(0, len(selected), BATCH):
        batch = selected[offset:offset+BATCH]
        requests, by_id, safe = [], {}, {}
        for tex in batch:
            key = sha(tex.encode("utf-8"))
            row = {"formula_sha256": key, "statements": [r["statement_id"] for r in formulas[tex]],
                   "labels": sorted({label for r in formulas[tex] for label in r["labels"]}),
                   "status": "candidate_only"}
            by_id[key] = row
            try:
                requests.append({"id": key, "value": preflight(tex)})
            except ValueError as error:
                row.update(outcome="input_rejected", reason=str(error))
        for key, result in run_batch("svg", requests).items():
            row = by_id[key]
            if "error" in result:
                row.update(outcome="svg_failed", reason=result["error"])
                continue
            try:
                safe[key] = safe_svg(result["value"])
            except ValueError as error:
                row.update(outcome="svg_rejected", reason=str(error))
        for key, result in run_batch("png", [{"id": k, "value": v[0]} for k, v in safe.items()]).items():
            row = by_id[key]
            if "error" in result:
                row.update(outcome="png_failed", reason=result["error"])
                continue
            svg, width, height = safe[key]
            try:
                png = png_bytes(result["value"], width, height)
            except (ValueError, TypeError) as error:
                row.update(outcome="png_rejected", reason=str(error))
                continue
            svg_raw = svg.encode("utf-8")
            svg_hash, png_hash = sha(svg_raw), sha(png)
            (assets / (svg_hash + ".svg")).write_bytes(svg_raw)
            (assets / (png_hash + ".png")).write_bytes(png)
            row.update(outcome="rendered_candidate", svg_sha256=svg_hash, png_sha256=png_hash,
                       width=width, height=height)
        for row in by_id.values():
            outcomes[row["outcome"]] += 1
            records.append(row)
        if offset % (BATCH * 10) == 0:
            print(f"Qualified {min(offset + BATCH, len(selected))}/{len(selected)}", file=sys.stderr)
    with (output / "results.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    gallery = ['<!doctype html><meta charset="utf-8"><title>STEM render samples</title>',
               '<style>body{background:#151515;color:#eee;font:16px system-ui;padding:24px}article{border-bottom:1px solid #444;padding:16px}img{max-width:100%;height:auto}</style>',
               '<h1>STEM rendering samples (not approved)</h1>']
    for row in [r for r in records if r["outcome"] == "rendered_candidate"][:100]:
        gallery.append('<article><p>' + html.escape(", ".join(row["labels"])) +
                       '</p><img src="assets/' + row["png_sha256"] + '.png" alt="Formula candidate"></article>')
    (output / "gallery.html").write_text("\n".join(gallery), encoding="utf-8")
    report = {"schema": SCHEMA, "source_sha256": source, "corpus_sha256": corpus_hash,
              "renderer_lock_sha256": sha(lock.read_bytes()), "unique_formulas": len(formulas),
              "examined": len(selected), "complete": len(selected) == len(formulas),
              "outcomes": dict(sorted(outcomes.items())), "status": "candidate_only"}
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Maintainer-only offline STEM renderer qualification")
    parser.add_argument("recovery", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(qualify(args.recovery, args.output, args.limit), indent=2))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        parser.exit(1, f"Qualification failed: {error}\n")


if __name__ == "__main__":
    main()
