import json
from pathlib import Path
import tempfile
import unittest

from stem.acquire import store_snapshot
from stem.diagnose import diagnose


class DiagnosticsTests(unittest.TestCase):
    def test_rejected_named_values_only(self):
        def binding(index, label, body):
            return {
                "item": {"value": f"http://www.wikidata.org/entity/Q{index}"},
                "itemLabel": {"value": label},
                "formula": {"value": '<math xmlns="http://www.w3.org/1998/Math/MathML">' + body + '</math>'},
            }
        rows = [
            binding(1, "Rejected formula", '<mi mathvariant="bold-italic">x</mi><mo>∴</mo>'),
            binding(2, "Accepted formula", '<mi mathvariant="bold">y</mi>'),
            binding(3, "123", '<mi mathvariant="bold-italic">z</mi>'),
        ]
        raw = json.dumps({"results": {"bindings": rows}}).encode()
        with tempfile.TemporaryDirectory() as root:
            manifest = store_snapshot(root, raw, acquisition="local_export")
            path = Path(root) / manifest["sha256"]
            report = diagnose(path)
            self.assertEqual(report["rejected_named_mathml_rows"], 1)
            self.assertEqual(report["attribute_values"]["mi:mathvariant"], {"bold-italic": 1})
            self.assertEqual(report["token_values"]["mo"], {"∴": 1})
            self.assertEqual(report["token_values"]["mi"], {"x": 1})
            self.assertEqual(report, diagnose(path))
            self.assertEqual((path / "snapshot.json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
