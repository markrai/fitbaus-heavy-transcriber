from collections import Counter
import hashlib
import xml.etree.ElementTree as ET
import zipfile

from epub_alignment import XHTML
from epub_inventory import EpubError, archive_members, inspect_epub, read_xml, resolve_href


SCHEMA = "fitbaus.epub-assets-preview/v1"
MATH = "{http://www.w3.org/1998/Math/MathML}"
SVG = "{http://www.w3.org/2000/svg}"
MAX_ASSET_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_OCCURRENCES = 2048
MAX_DEPTH = 128
RASTER = frozenset(("image/png", "image/jpeg", "image/gif", "image/webp"))
SKIP = frozenset(("audio", "canvas", "iframe", "nav", "noscript", "script", "style", "video"))


class AssetError(EpubError):
    pass


def raster_signature(media_type, data):
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def subtree_bytes(node):
    stack = [(node, 0)]
    while stack:
        child, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise AssetError("Visual subtree exceeds nesting limit")
        stack.extend((item, depth + 1) for item in child)
    tail = node.tail
    try:
        node.tail = None
        return ET.tostring(node, encoding="utf-8")
    finally:
        node.tail = tail


class Catalogue:
    def __init__(self, archive, members, resources):
        self.archive = archive
        self.members = members
        self.resources = resources
        self.assets = {}
        self.occurrences = []
        self.cached = {}
        self.skipped = Counter()
        self.total_bytes = 0
        self.attempts = 0
        self.figures = 0

    def attempt(self):
        self.attempts += 1
        if self.attempts > MAX_OCCURRENCES:
            raise AssetError("Visual candidate count exceeds limit")

    def add(self, kind, media_type, payload, representation):
        if not 0 < len(payload) <= MAX_ASSET_BYTES:
            raise AssetError("Visual payload exceeds size limit")
        digest = hashlib.sha256(payload).hexdigest()
        asset_id = hashlib.sha256((media_type + ":" + digest).encode("ascii")).hexdigest()
        if asset_id not in self.assets:
            self.total_bytes += len(payload)
            if self.total_bytes > MAX_TOTAL_BYTES:
                raise AssetError("Total visual payload exceeds limit")
            self.assets[asset_id] = {"asset_id": asset_id, "sha256": digest, "kind": kind,
                                     "media_type": media_type, "size": len(payload),
                                     "representation": representation, "payload": payload}
        return asset_id

    def referenced(self, path):
        if path in self.cached:
            return self.cached[path]
        media_type = self.resources.get(path)
        if media_type not in RASTER and media_type != "image/svg+xml":
            self.skipped["unsupported_or_undeclared_resource"] += 1
            return None
        info = self.members[path]
        if not 0 < info.file_size <= MAX_ASSET_BYTES:
            raise AssetError("Visual resource exceeds size limit")
        if media_type == "image/svg+xml":
            root = read_xml(self.archive, self.members, path)
            if root.tag != SVG + "svg":
                raise AssetError("Invalid SVG resource")
            kind = "svg"
        else:
            kind = "raster"
        payload = self.archive.read(info)
        if kind == "raster" and not raster_signature(media_type, payload):
            raise AssetError("Image signature does not match declared media type")
        asset_id = self.add(kind, media_type, payload, "original_bytes")
        self.cached[path] = asset_id
        return asset_id

    def occurrence(self, asset_id, spine_index, document, node_path, figure_path, resource=None):
        self.occurrences.append({"asset_id": asset_id, "spine_index": spine_index,
                                 "document": document, "node_path": list(node_path),
                                 "figure_path": None if figure_path is None else list(figure_path),
                                 "resource": resource})

    def xhtml(self, root, spine_index, document):
        body = root.find(XHTML + "body")
        if root.tag != XHTML + "html" or body is None:
            raise AssetError("Unsupported XHTML reading-order document")
        stack = [(body, (), None)]
        while stack:
            node, path, figure = stack.pop()
            if len(path) > MAX_DEPTH:
                raise AssetError("XHTML exceeds visual nesting limit")
            if "hidden" in node.attrib or node.get("aria-hidden") == "true":
                continue
            tag = node.tag
            if tag == MATH + "math" or tag == SVG + "svg":
                self.attempt()
                kind, media_type = (("mathml", "application/mathml+xml") if tag == MATH + "math"
                                    else ("svg", "image/svg+xml"))
                asset_id = self.add(kind, media_type, subtree_bytes(node), "xml_subtree")
                self.occurrence(asset_id, spine_index, document, path, figure)
                continue
            if not tag.startswith(XHTML):
                continue
            local = tag.removeprefix(XHTML)
            if local in SKIP:
                continue
            if local == "figure":
                self.figures += 1
                figure = path
            if local == "img":
                self.attempt()
                if "srcset" in node.attrib:
                    self.skipped["responsive_image"] += 1
                    continue
                try:
                    resource = resolve_href(document, node.get("src"))
                except EpubError:
                    self.skipped["unsupported_reference"] += 1
                    continue
                asset_id = self.referenced(resource)
                if asset_id is not None:
                    self.occurrence(asset_id, spine_index, document, path, figure, resource)
                continue
            if local in ("object", "embed", "picture"):
                self.attempt()
                self.skipped["unsupported_container"] += 1
                continue
            stack.extend((child, path + (index,), figure)
                         for index, child in reversed(list(enumerate(node))))

    def result(self, inventory, section_count):
        counts = Counter(self.assets[row["asset_id"]]["kind"] for row in self.occurrences)
        return {"schema": SCHEMA, "epub_sha256": inventory["sha256"],
                "edition_verified": False, "render_qualified": False,
                "section_count": section_count, "figure_count": self.figures,
                "mathml_count": counts["mathml"], "svg_count": counts["svg"],
                "raster_count": counts["raster"], "occurrence_count": len(self.occurrences),
                "unique_asset_count": len(self.assets), "payload_bytes": self.total_bytes,
                "skipped_count": sum(self.skipped.values()), "skipped": dict(self.skipped),
                "assets": list(self.assets.values()), "occurrences": self.occurrences}


def extract_assets(stream):
    inventory = inspect_epub(stream, include_resources=True)
    document_bytes = section_count = 0
    try:
        with zipfile.ZipFile(stream) as archive:
            members = archive_members(archive)
            catalogue = Catalogue(archive, members, inventory["resources"])
            for index, row in enumerate(inventory["spine"]):
                if not row["linear"]:
                    continue
                path = row["path"]
                document_bytes += members[path].file_size
                if document_bytes > MAX_DOCUMENT_BYTES:
                    raise AssetError("Reading-order documents exceed visual preview limit")
                section_count += 1
                if row["media_type"] == "image/svg+xml":
                    catalogue.attempt()
                    asset_id = catalogue.referenced(path)
                    catalogue.occurrence(asset_id, index, path, (), None, path)
                else:
                    catalogue.xhtml(read_xml(archive, members, path), index, path)
            return catalogue.result(inventory, section_count)
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError):
        raise AssetError("Invalid or unsupported visual archive") from None
