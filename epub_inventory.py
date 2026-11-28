from collections import Counter
import hashlib
import posixpath
import re
import stat
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile


MAX_EPUB_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 4096
CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"


class EpubError(ValueError):
    pass


def member_name(name):
    if (not name or len(name) > 1024 or "\\" in name or ":" in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise EpubError("Unsafe EPUB member path")
    return name


def resolve_href(package, href):
    if not href or re.search(r"%(?![0-9a-fA-F]{2})", href):
        raise EpubError("Invalid EPUB manifest reference")
    try:
        parsed = urlsplit(href)
        path = unquote(parsed.path, errors="strict")
    except (ValueError, UnicodeError):
        raise EpubError("Invalid EPUB manifest reference") from None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not path or path.startswith("/"):
        raise EpubError("External or unsupported EPUB manifest reference")
    if "\\" in path or ":" in path or any(ord(c) < 32 for c in path):
        raise EpubError("Unsafe EPUB manifest reference")
    return member_name(posixpath.normpath(posixpath.join(posixpath.dirname(package), path)))


def archive_members(archive):
    infos = archive.infolist()
    if not 1 <= len(infos) <= MAX_MEMBERS:
        raise EpubError("EPUB member count exceeds limit")
    members, seen = {}, set()
    expanded = 0
    for info in infos:
        if info.orig_filename != info.filename:
            raise EpubError("Invalid EPUB member name")
        name = member_name(info.filename.rstrip("/") if info.is_dir() else info.filename)
        if name in seen:
            raise EpubError("Duplicate EPUB member")
        seen.add(name)
        kind = stat.S_IFMT(info.external_attr >> 16)
        if (kind not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG)
                or info.flag_bits & 1
                or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise EpubError("Unsupported or encrypted EPUB member")
        expanded += info.file_size
        if info.file_size > MAX_MEMBER_BYTES or expanded > MAX_EXPANDED_BYTES:
            raise EpubError("EPUB expanded size exceeds limit")
        if not info.is_dir():
            members[name] = info
    if "META-INF/encryption.xml" in members:
        raise EpubError("Encrypted or obfuscated EPUB is unsupported")
    return members


def read_xml(archive, members, name):
    info = members.get(name)
    if info is None or info.file_size > MAX_XML_BYTES:
        raise EpubError("Missing or oversized EPUB metadata")
    raw = archive.read(info)
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
            raise EpubError("DTD and entities are unsupported")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError, LookupError):
        raise EpubError("Unsupported or invalid EPUB XML") from None
    if sum(1 for _ in root.iter()) > 50000:
        raise EpubError("EPUB metadata node count exceeds limit")
    return root


def metadata_text(metadata, tag):
    if metadata is None:
        return None
    node = metadata.find(DC + tag)
    if node is None:
        return None
    return " ".join("".join(node.itertext()).split())[:300] or None


def package_inventory(archive, members, *, include_resources=False):
    mime = members.get("mimetype")
    if (mime is None or mime.file_size != 20 or mime.compress_type != zipfile.ZIP_STORED
            or archive.read(mime) != b"application/epub+zip"):
        raise EpubError("Invalid EPUB mimetype")
    container = read_xml(archive, members, "META-INF/container.xml")
    roots = container.findall(CONTAINER + "rootfiles/" + CONTAINER + "rootfile")
    if container.tag != CONTAINER + "container" or len(roots) != 1:
        raise EpubError("Exactly one EPUB package is supported")
    if roots[0].get("media-type") != "application/oebps-package+xml":
        raise EpubError("Unsupported EPUB package type")
    package = member_name(roots[0].get("full-path", ""))
    opf = read_xml(archive, members, package)
    version = opf.get("version", "")
    if opf.tag != OPF + "package" or version not in ("2.0", "3.0", "3.1", "3.2", "3.3"):
        raise EpubError("Unsupported EPUB package version")
    manifest = opf.find(OPF + "manifest")
    spine = opf.find(OPF + "spine")
    if manifest is None or spine is None:
        raise EpubError("Missing EPUB manifest or spine")
    resources, paths = {}, set()
    for row in manifest.findall(OPF + "item"):
        ident = row.get("id")
        kind = row.get("media-type")
        path = resolve_href(package, row.get("href"))
        if (not ident or ident in resources or not kind or len(kind) > 128
                or path not in members or path in paths):
            raise EpubError("Invalid or duplicate EPUB manifest item")
        resources[ident] = (path, kind)
        paths.add(path)
    ordered = []
    for row in spine.findall(OPF + "itemref"):
        ident = row.get("idref")
        if ident not in resources:
            raise EpubError("Unresolved EPUB spine entry")
        if row.get("linear", "yes") not in ("yes", "no"):
            raise EpubError("Invalid EPUB spine linearity")
        if resources[ident][1] not in ("application/xhtml+xml", "image/svg+xml"):
            raise EpubError("Unsupported EPUB spine resource")
        ordered.append({"path": resources[ident][0], "media_type": resources[ident][1],
                        "linear": row.get("linear", "yes") == "yes"})
    if not ordered or len(ordered) > MAX_MEMBERS:
        raise EpubError("Missing or oversized EPUB spine")
    counts = Counter(kind for _, kind in resources.values())
    metadata = opf.find(OPF + "metadata")
    result = {"version": version, "title": metadata_text(metadata, "title"),
            "creator": metadata_text(metadata, "creator"),
            "manifest_count": len(resources), "spine_count": len(ordered),
            "xhtml_count": counts["application/xhtml+xml"],
            "image_count": sum(count for kind, count in counts.items() if kind.startswith("image/")),
            "spine": ordered}
    if include_resources:
        result["resources"] = {path: kind for path, kind in resources.values()}
    return result


def inspect_epub(stream, *, include_resources=False):
    stream.seek(0, 2)
    size = stream.tell()
    if not 0 < size <= MAX_EPUB_BYTES:
        raise EpubError("EPUB download size exceeds limit")
    stream.seek(0)
    digest = hashlib.sha256()
    while chunk := stream.read(65536):
        digest.update(chunk)
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as archive:
            inventory = package_inventory(archive, archive_members(archive), include_resources=include_resources)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, OSError) as error:
        raise EpubError("Invalid or unsupported EPUB archive") from None
    return {"schema": "fitbaus.epub-inventory/v1", "sha256": digest.hexdigest(),
            "size": size, "edition_verified": False, **inventory}
