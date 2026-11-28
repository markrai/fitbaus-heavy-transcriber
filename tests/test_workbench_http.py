import json
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import threading
import unittest
from urllib.request import urlopen

from app import Handler, load_static_assets


class WorkbenchHTTPTests(unittest.TestCase):
    def test_actual_companion_route_and_static_snapshot(self):
        book = "book-123"
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            server.host = "127.0.0.1:" + str(server.server_port)
            server.static_assets = load_static_assets()
            server.workbench = SimpleNamespace(companions=lambda item: {
                "item_id": item, "files": [{"file_id": "42", "format": "epub"}]})
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with urlopen("http://" + server.host + "/api/companions/" + book, timeout=5) as response:
                    self.assertEqual(json.load(response), {"item_id": book,
                                                           "files": [{"file_id": "42", "format": "epub"}]})
                with urlopen("http://" + server.host + "/app.js", timeout=5) as response:
                    self.assertEqual(response.read(), server.static_assets["/app.js"][1])
                self.assertNotIn(b"VEGA", server.static_assets["/"][1])
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
