import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stem.acquire import AcquisitionError, store_snapshot
from stem.recover import recover, parse_response, fetch_batch


def claim(entity, suffix, formula, rank="normal"):
    return {"id": entity + "$" + suffix, "rank": rank,
            "mainsnak": {"property": "P2534", "datatype": "math", "snaktype": "value",
                         "datavalue": {"type": "string", "value": formula}}}


def response(ids):
    return json.dumps({"entities": {entity: {
        "id": entity, "lastrevid": 123,
        "claims": {"P2534": [
            claim(entity, "a", r"\boldsymbol{\alpha}"),
            claim(entity, "b", "x=1", "preferred"),
            claim(entity, "c", "x=2", "deprecated"),
        ]}
    } for entity in ids}}).encode()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        rows = []
        for entity, label in (("Q1", "Named one"), ("Q1", "Named alias"),
                              ("Q2", "Named two"), ("Q3", "123"), ("Q4", "Q4")):
            rows.append({"item": {"value": "http://www.wikidata.org/entity/" + entity},
                         "itemLabel": {"value": label}, "formula": {"value": "x=1"}})
        raw = json.dumps({"results": {"bindings": rows}}).encode()
        manifest = store_snapshot(self.root / "snapshots", raw, acquisition="local_export")
        self.source = self.root / "snapshots" / manifest["sha256"]
        self.output = self.root / "recovery"

    @patch("stem.recover.BATCH_SIZE", 1)
    def test_resume_and_provenance(self):
        calls = []
        def fetch(ids):
            calls.append(ids)
            return response(ids)
        report = recover(self.source, self.output, 1, fetch)
        self.assertFalse(report["complete"])
        self.assertEqual(report["entities_completed"], 1)
        self.assertEqual(report["candidate_statements"], 2)
        report = recover(self.source, self.output, fetch=fetch)
        self.assertTrue(report["complete"])
        self.assertEqual(calls, [["Q1"], ["Q2"]])
        self.assertEqual(report["candidate_statements"], 4)
        self.assertEqual(report["unique_exact_latex"], 2)
        records = [json.loads(line) for line in (self.output / "original-tex.jsonl").read_text().splitlines()]
        self.assertEqual(records[0]["latex"], r"\boldsymbol{\alpha}")
        self.assertEqual(records[0]["entity_revision"], 123)
        self.assertEqual(records[0]["labels"], ["Named alias", "Named one"])
        self.assertEqual(records[0]["statement_id"], "Q1$a")
        self.assertEqual(records[0]["lexical_screen"], "Unsupported LaTeX command")
        self.assertTrue(all(r["status"] == "candidate_only" for r in records))
        before = (self.output / "original-tex.jsonl").read_bytes()
        self.assertEqual(report, recover(self.source, self.output, fetch=fetch))
        self.assertEqual(calls, [["Q1"], ["Q2"]])
        self.assertEqual(before, (self.output / "original-tex.jsonl").read_bytes())

    @patch("stem.recover.BATCH_SIZE", 1)
    def test_corrupted_checkpoint_stops(self):
        recover(self.source, self.output, 1, response)
        path = self.output / "batches" / "00000.json"
        data = json.loads(path.read_text())
        data["response_utf8"] += " "
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(AcquisitionError, "SHA-256"):
            recover(self.source, self.output, fetch=response)

    def test_wrong_entity_or_revision_rejected(self):
        with self.assertRaises(AcquisitionError):
            parse_response(response(["Q2"]), ["Q1"])
        data = json.loads(response(["Q1"]))
        del data["entities"]["Q1"]["lastrevid"]
        with self.assertRaises(AcquisitionError):
            parse_response(json.dumps(data).encode(), ["Q1"])

    def test_missing_and_non_value_statements(self):
        def fetch(ids):
            data = json.loads(response(ids))
            data["entities"]["Q2"] = {"id": "Q2", "missing": ""}
            data["entities"]["Q1"]["claims"]["P2534"].append({
                "id": "Q1$d", "rank": "normal",
                "mainsnak": {"property": "P2534", "snaktype": "novalue"},
            })
            return json.dumps(data).encode()
        report = recover(self.source, self.output, fetch=fetch)
        self.assertEqual(report["outcomes"]["missing_entity"], 1)
        self.assertEqual(report["outcomes"]["non_value_statement"], 1)
        self.assertEqual(report["outcomes"]["deprecated_statement"], 1)

    @patch("stem.recover.time.sleep")
    @patch("stem.recover.urlopen")
    def test_api_maxlag_retry(self, urlopen, sleep):
        first, second = urlopen.return_value.__enter__.return_value, response(["Q1"])
        first.read.side_effect = [b'{"error":{"code":"maxlag"}}', second]
        first.headers.get.return_value = "2"
        self.assertEqual(fetch_batch(["Q1"]), second)
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn(2, [call.args[0] for call in sleep.call_args_list])


if __name__ == "__main__":
    unittest.main()
