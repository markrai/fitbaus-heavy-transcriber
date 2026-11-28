import argparse
import getpass
import warnings
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser

from heavy import Library, Vega, GpuEngine, process_book, ROOT, atomic_json, SourceError, WorkbenchError, require_ffmpeg


class Workbench:
    def __init__(self, library, vega, profile, root):
        self.library = library
        self.vega = vega
        self.profile = profile
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.engine = GpuEngine(profile.rsplit(":", 1)[1])
        self.lock = threading.Lock()
        self.catalog = {}
        self.jobs = {}
        self.running = False
        self.inspecting_epub = False
        self.history_path = root / "history.json"
        self.history = json.loads(self.history_path.read_text("ascii")) if self.history_path.exists() else {}

    def books(self):
        books = self.library.books()
        with self.lock:
            self.catalog = {book["id"]: book for book in books}
            return [{**book, "previously_imported": book["id"] in self.history} for book in books]

    def companions(self, item):
        with self.lock:
            if item not in self.catalog:
                raise ValueError("Unknown book")
        return {"item_id": item, "files": [row.public() for row in self.library.companions(item)]}

    def epub_inventory(self, item, file_id):
        with self.lock:
            if not isinstance(item, str) or item not in self.catalog:
                raise ValueError("Unknown book")
            if self.running or self.inspecting_epub:
                raise ValueError("Workbench is busy")
            self.inspecting_epub = True
        try:
            result = self.library.epub_inventory(item, file_id)
            return {key: value for key, value in result.items() if key != "spine"}
        finally:
            with self.lock:
                self.inspecting_epub = False

    def cover(self, item):
        with self.lock:
            if item not in self.catalog:
                raise ValueError("Unknown book")
        return self.library.cover(item)

    def start(self, ids):
        with self.lock:
            if self.running or self.inspecting_epub:
                raise ValueError("Workbench is busy")
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 32 or
                    any(not isinstance(item, str) or item not in self.catalog for item in ids) or
                    len(set(ids)) != len(ids)):
                raise ValueError("Select between 1 and 32 known books")
            self.jobs = {item: {"title": self.catalog[item]["title"], "state": "Queued", "done": 0, "total": 0}
                         for item in ids}
            self.running = True
        threading.Thread(target=self.run, args=(ids,), daemon=False).start()

    def run(self, ids):
        try:
            for item in ids:
                def report(state, done, total):
                    with self.lock:
                        self.jobs[item].update(state=state, done=done, total=total)
                try:
                    process_book(self.library, self.vega, self.engine, self.profile, item, self.root, report)
                    with self.lock:
                        self.history[item] = True
                        atomic_json(self.history_path, self.history)
                except Exception as error:
                    with self.lock:
                        stage = self.jobs[item]["state"]
                        if isinstance(error, WorkbenchError):
                            detail = str(error)
                        elif isinstance(error, SourceError):
                            detail = "Audiobookshelf: " + error.code
                        elif isinstance(error, FileNotFoundError):
                            detail = "Required file or executable not found"
                        else:
                            detail = type(error).__name__
                        message = stage + ": " + detail
                        self.jobs[item].update(state="Failed", error=message)
                    print("Transcription failed: " + message, flush=True)
        finally:
            with self.lock:
                self.running = False

    def status(self):
        with self.lock:
            return {"running": self.running, "jobs": {k: dict(v) for k, v in self.jobs.items()}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def send(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200):
        self.send(status, "application/json", json.dumps(value, ensure_ascii=True).encode("ascii"))

    def valid_host(self):
        return self.headers.get_all("Host") == [self.server.host]

    def do_GET(self):
        if not self.valid_host():
            return self.json({"error": "Invalid host"}, 403)
        try:
            if self.path in ("/", "/app.js", "/style.css"):
                path, kind = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                              "/style.css": ("style.css", "text/css")}[self.path]
                self.send(200, kind + "; charset=utf-8", (ROOT / "web" / path).read_bytes())
            elif self.path == "/api/books":
                self.json(self.server.workbench.books())
            elif self.path == "/api/status":
                self.json(self.server.workbench.status())
            elif self.path.startswith("/api/companions/"):
                self.json(self.server.workbench.companions(self.path.removeprefix("/api/companions/")))
            elif self.path.startswith("/api/cover/"):
                kind, cover = self.server.workbench.cover(self.path.removeprefix("/api/cover/"))
                self.send(200, kind, cover)
            else:
                self.json({"error": "Not found"}, 404)
        except Exception:
            self.json({"error": "Request failed; check Audiobookshelf access"}, 502)

    def do_POST(self):
        if (not self.valid_host() or self.headers.get_all("Origin") != ["http://" + self.server.host]
                or self.headers.get_content_type() != "application/json"):
            return self.json({"error": "Request rejected"}, 403)
        if self.path not in ("/api/start", "/api/epub-inventory"):
            return self.json({"error": "Not found"}, 404)
        try:
            size = int(self.headers["Content-Length"])
            if not 0 < size <= 16384 or self.headers.get("Transfer-Encoding"):
                raise ValueError()
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError()
            if self.path == "/api/epub-inventory":
                if set(value) != {"item_id", "file_id"}:
                    raise ValueError()
                self.json(self.server.workbench.epub_inventory(value["item_id"], value["file_id"]))
            else:
                if set(value) != {"ids"}:
                    raise ValueError()
                self.server.workbench.start(value["ids"])
                self.json({"accepted": True}, 202)
        except SourceError as error:
            self.json({"error": "Audiobookshelf: " + error.code}, 502)
        except (ValueError, TypeError, KeyError, OSError):
            self.json({"error": "Cannot inspect EPUB: unsupported file, invalid selection or busy workbench"
                       if self.path == "/api/epub-inventory" else
                       "Cannot start: select known books and wait for the current batch"}, 400)


def authenticate(address, source_id):
    print("Audiobookshelf authentication")
    print("  1) Username and password (default)")
    print("  2) API key or access token")
    choice = input("Choose [1/2]: ").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        if choice in ("", "1"):
            username = input("Audiobookshelf username: ").strip()
            password = getpass.getpass("Audiobookshelf password: ")
            try:
                return Library.login(address, source_id, username, password)
            finally:
                del password
        if choice == "2":
            return Library(address, source_id, getpass.getpass("Audiobookshelf API key or access token: "))
    raise ValueError("Invalid authentication choice")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abs-url", required=True)
    parser.add_argument("--ssh-host", default="vega")
    parser.add_argument("--remote-dir", default="/home/vega/dev/project/fitbaus-transcriber")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "work")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    if args.abs_url.startswith("http://"):
        print("Audiobookshelf credentials travel over unencrypted HTTP; use only a trusted LAN.")
        if input("Continue? [y/N]: ").strip().lower() != "y":
            return
    try:
        require_ffmpeg()
    except WorkbenchError as error:
        print(str(error))
        return 1
    vega = Vega(args.ssh_host, args.remote_dir)
    config = vega.configuration()
    try:
        library = authenticate(args.abs_url, config["source_id"])
        library.authorized(library.source.check_access)
    except (ValueError, SourceError, getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print("Audiobookshelf authentication failed or cancelled. Check your credentials and server access.")
        return 1
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.host = f"127.0.0.1:{args.port}"
        server.workbench = Workbench(library, vega, config["profile"], args.work_dir.resolve())
        address = "http://" + server.host
        print("Workbench: " + address)
        webbrowser.open(address)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Closing UI; any running batch finishes before Python exits.")


if __name__ == "__main__":
    raise SystemExit(main())
