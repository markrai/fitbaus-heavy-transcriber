import contextlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from stem import acquire


RAW = json.dumps({"results": {"bindings": [{"item": {"value": "http://www.wikidata.org/entity/Q1"},
    "itemLabel": {"value": "Example"}, "formula": {"value": "x=1"}}]}}).encode()


def http_error(status, retry=None):
    headers = {} if retry is None else {"Retry-After": retry}
    return HTTPError(acquire.ENDPOINT, status, "error", headers, BytesIO())


class StemAcquisitionTests(unittest.TestCase):
    @patch("stem.acquire.time.sleep")
    @patch("stem.acquire.urlopen")
    def test_rate_limit_then_success(self, opener, sleep):
        opener.side_effect = [http_error(429, "17"), BytesIO(RAW)]
        with contextlib.redirect_stderr(StringIO()):
            self.assertEqual(acquire.fetch_snapshot(), RAW)
        sleep.assert_called_once_with(17)
        self.assertEqual(opener.call_count, 2)

    @patch("stem.acquire.time.sleep")
    @patch("stem.acquire.urlopen")
    def test_long_retry_after_stops_without_retry(self, opener, sleep):
        opener.side_effect = http_error(429, "600")
        with self.assertRaisesRegex(acquire.AcquisitionError, "600 seconds"):
            acquire.fetch_snapshot()
        sleep.assert_not_called()
        opener.assert_called_once()

    @patch("stem.acquire.time.sleep")
    @patch("stem.acquire.urlopen")
    def test_missing_retry_after_uses_bounded_backoff(self, opener, sleep):
        opener.side_effect = [http_error(429), http_error(429)]
        with contextlib.redirect_stderr(StringIO()):
            with self.assertRaisesRegex(acquire.AcquisitionError, "120 seconds"):
                acquire.fetch_snapshot()
        sleep.assert_called_once_with(60)
        self.assertEqual(opener.call_count, 2)

    @patch("stem.acquire.time.sleep")
    @patch("stem.acquire.urlopen")
    def test_permanent_error_is_not_retried(self, opener, sleep):
        opener.side_effect = http_error(403)
        with self.assertRaisesRegex(acquire.AcquisitionError, "403"):
            acquire.fetch_snapshot()
        sleep.assert_not_called()

    def test_http_date_retry_after(self):
        header = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=300), usegmt=True)
        self.assertGreaterEqual(acquire.retry_delay(header, 1), 298)

    @patch("stem.acquire.urlopen")
    def test_offline_snapshot_is_idempotent_and_has_honest_provenance(self, opener):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "export.json"
            path.write_bytes(RAW)
            output = Path(root) / "candidates"
            first = acquire.snapshot(output, path)
            self.assertEqual(first, acquire.snapshot(output, path))
            self.assertEqual(first["acquisition"], "local_export")
            self.assertIsNone(first["query"])
            self.assertEqual((output / first["sha256"] / "snapshot.json").read_bytes(), RAW)
        opener.assert_not_called()

    def test_invalid_snapshot_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "candidates"
            for raw in (b"not json", b'{"results":{"bindings":[]}}', b'{"results":{"bindings":[null]}}'):
                with self.assertRaises(acquire.AcquisitionError):
                    acquire.store_snapshot(output, raw, acquisition="local_export")
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
