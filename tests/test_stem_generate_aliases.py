import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stem.corpus_model import ROOT, mathematical_digest
from stem.generate_aliases import Ollama, build_plan, classify, generate, make_record, validate_response

IDENTITY = {"provider": "ollama-loopback", "model": "test:local", "digest": "a" * 64, "version": "test"}
PENDING = {"status": "pending", "digest": None, "method": [], "evidence": []}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fingerprint = dict(IDENTITY)
        self.fail = None

    def identity(self):
        return dict(self.fingerprint)

    def generate(self, item, count):
        self.calls.append(item["id"])
        if self.fail == item["id"]:
            raise ValueError("test interruption")
        return json.dumps({"aliases": ["energy equals mass times c squared"]})


class AliasGenerationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "corpus"
        self.output = Path(temp.name) / "work"
        path = self.root / "physics" / "relativity" / "mass_energy.json"
        path.parent.mkdir(parents=True)
        self.concept = json.loads((ROOT / "physics" / "relativity" / "mass_energy.json").read_text(encoding="utf-8"))
        self.path = path
        rep = self.concept["representations"][0]
        rep["references"] = [{"source_id": "curated", "locator": "test fixture"}]
        rep["recognition_review"] = copy.deepcopy(PENDING)
        self.approve(rep)
        alternate = copy.deepcopy(rep)
        alternate.update(id="alternate", latex="m=E/c^2", spoken_aliases=[])
        self.approve(alternate)
        self.concept["representations"].append(alternate)
        self.write()
        (self.root / "sources.json").write_text(json.dumps({
            "schema": "fitbaus.stem.sources/v1",
            "sources": [{"id": "curated", "status": "admitted"}],
        }), encoding="utf-8")

    def approve(self, rep):
        rep["mathematical_review"] = {"status": "approved", "digest": mathematical_digest(self.concept, rep),
                                      "method": ["test"], "evidence": ["test fixture"]}

    def write(self):
        self.path.write_text(json.dumps(self.concept), encoding="utf-8")

    def test_plan_only_pending_recognition_with_approved_math(self):
        self.concept["representations"][1]["mathematical_review"] = copy.deepcopy(PENDING)
        self.write()
        plan = build_plan(self.root, IDENTITY, 8)
        self.assertEqual([row["id"] for row in plan["items"]], ["physics.mass_energy:standard"])
        self.assertIn("e equals mc squared", plan["reserved_aliases"])

    def test_resume_and_cross_representation_collision(self):
        client = FakeClient()
        before = self.path.read_bytes()
        first = generate(self.root, self.output, client, max_new=1)
        self.assertFalse(first["complete"])
        self.assertEqual(first["completed"], 1)
        self.assertEqual(first["counts"], {"candidate_only": 1})
        second = generate(self.root, self.output, client)
        self.assertTrue(second["complete"])
        self.assertEqual(second["counts"], {"collision": 2})
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(generate(self.root, self.output, client), second)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(second["release_qualified"])

    def test_stale_model_or_corpus_rejected(self):
        client = FakeClient()
        generate(self.root, self.output, client, max_new=1)
        client.fingerprint["digest"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "plan differs"):
            generate(self.root, self.output, client)
        client.fingerprint = dict(IDENTITY)
        self.concept["alternate_names"].append("new alternate name")
        self.write()
        with self.assertRaisesRegex(ValueError, "plan differs"):
            generate(self.root, self.output, client)

    def test_damaged_checkpoint_rejected(self):
        client = FakeClient()
        generate(self.root, self.output, client, max_new=1)
        path = next((self.output / "responses").iterdir())
        value = json.loads(path.read_text(encoding="utf-8"))
        value["content"] = '{"aliases":[]}'
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid or stale checkpoint"):
            generate(self.root, self.output, client)

    def test_invalid_response_no_checkpoint_and_resume(self):
        client = FakeClient()
        client.fail = "physics.mass_energy:standard"
        with self.assertRaisesRegex(ValueError, "Generation failed for"):
            generate(self.root, self.output, client)
        self.assertEqual(len(list((self.output / "responses").iterdir())), 1)
        client.fail = None
        self.assertTrue(generate(self.root, self.output, client)["complete"])
        self.assertEqual(len(client.calls), 3)

    def test_classification_and_reserved_alias_collision(self):
        plan = build_plan(self.root, IDENTITY, 8)
        a, b = plan["items"]
        records = {a["id"]: make_record(plan, a, json.dumps({"aliases": [
            "e equals mc squared", "mass energy equivalence", "ordinary unrelated words",
            "x = y", "m equals e over c squared", "M EQUALS E OVER C SQUARED",
        ]})), b["id"]: make_record(plan, b, json.dumps({"aliases": ["e equals mc squared"]}))}
        report = classify(plan, records)
        self.assertEqual(report["counts"], {
            "candidate_only": 1, "collision": 2, "duplicate": 1,
            "generic_name": 1, "invalid_alias": 1, "missing_relation": 1,
        })
        self.assertTrue(report["complete"])

    def test_strict_response_shape(self):
        for value in ('{"aliases":[],"extra":1}', '{"aliases":[1]}',
                      '{"aliases":[],"aliases":[]}', '{"aliases":["one","two"]}', 'not json'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_response(value, 1)
        self.assertEqual(validate_response('{"aliases":[]}', 1), [])

    def test_output_inside_corpus_rejected(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            generate(self.root, self.root / "work", FakeClient())

    def test_ollama_structured_request_and_completion(self):
        client = Ollama("test:local")
        item = build_plan(self.root, IDENTITY, 8)["items"][0]
        with patch.object(client, "request", return_value={
            "model": "test:local", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": '{"aliases":[]}'},
        }) as request:
            self.assertEqual(client.generate(item, 8), '{"aliases":[]}')
        path, payload = request.call_args.args
        self.assertEqual(path, "/api/chat")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"]["properties"]["aliases"]["maxItems"], 8)
        with patch.object(client, "request", return_value={"done": False}):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                client.generate(item, 8)

    def test_model_inventory_rejects_remote(self):
        client = Ollama("test:local")
        with patch.object(client, "request", return_value={"models": [{
            "name": "test:local", "digest": "a" * 64, "size": 100, "remote_host": "remote",
        }]}):
            with self.assertRaisesRegex(ValueError, "local size"):
                client.identity()


if __name__ == "__main__":
    unittest.main()
