import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stem.sample_checkpoints import PROFILE_PREFIX, partition_for, scan
from transcriber.contract import AudioIdentity, Cue, TranscriptWindow

from stem.context_observations import LABEL_SCHEMA, read_labels, recover_context, score
from stem.corpus_model import digest
from stem.hybrid import PYTHAGORAS, build_hybrid


class ContextObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, _, _ = build_hybrid()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        identity = AudioIdentity("home", "book", "a" * 64)
        key = identity.cache_key()
        profile = hashlib.sha256((PROFILE_PREFIX + "auto").encode("ascii")).hexdigest()[:16]
        directory = self.work / key / profile
        directory.mkdir(parents=True)
        self.originals = {}
        for i in range(12):
            start = i * 300000
            text = "a squared plus" if partition_for(42, key, start) == "development" else "SEALED HOLDOUT"
            cues = (Cue(start, start + 1000, text),
                    Cue(start + 1100, start + 2000, "b squared equals c squared."),
                    Cue(start + 2100, start + 3000, "Ordinary prose."))
            path = directory / f"{start}.json"
            path.write_text(json.dumps(TranscriptWindow(identity, start, start + 300000, cues).to_json()),
                            encoding="utf-8")
            self.originals[path] = path.read_bytes()
        self.sample = scan(self.work, uniform_count=100, targeted_count=0)
        self.pack, self.windows = recover_context(self.sample, self.work, self.hybrid)

    def labels(self):
        cases = []
        for window in self.pack["windows"]:
            for anchor in window["anchors"]:
                expected = []
                if anchor["cue_index"] == 0:
                    expected.append({"id": PYTHAGORAS, "latex": "a^2+b^2=c^2",
                                     "spans": [{"cue_index": 0, "start": 0, "end": len("a squared plus")},
                                               {"cue_index": 1, "start": 0, "end": len("b squared equals c squared")}]})
                cases.append({"id": anchor["id"], "expected": expected, "exclusion_reason": None})
        return {"schema": LABEL_SCHEMA, "context_sha256": self.pack["context_sha256"],
                "labeling_method": "authored test fixture", "cases": cases}

    def test_replay_read_only_and_partition_isolation(self):
        self.assertEqual(recover_context(self.sample, self.work, self.hybrid)[0], self.pack)
        self.assertEqual(sum(len(w["anchors"]) for w in self.pack["windows"]), len(self.sample["cases"]))
        self.assertNotIn("SEALED HOLDOUT", json.dumps(self.pack))
        self.assertTrue(all(len(w["cues"]) == 3 for w in self.pack["windows"]))
        for path, raw in self.originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_exact_cross_cue_scoring(self):
        report = score(self.pack, self.windows, self.labels(), self.hybrid)
        uniform = report["groups"]["uniform"]
        self.assertTrue(uniform["pass"])
        self.assertGreater(uniform["cross_cue_expected"], 0)
        self.assertEqual(uniform["cross_cue_true_positive"], uniform["cross_cue_expected"])
        self.assertEqual(uniform["invalid_evidence"], 0)
        self.assertIsNone(report["groups"]["formula_hint"]["recall"])
        self.assertFalse(report["recognition_qualified"])

    def test_wrong_span_counts_as_two_errors(self):
        labels = self.labels()
        row = next(row for row in labels["cases"] if row["expected"])
        row["expected"][0]["spans"][1]["end"] -= 1
        result = score(self.pack, self.windows, labels, self.hybrid)["groups"]["uniform"]
        self.assertEqual((result["false_positive"], result["false_negative"]), (1, 1))

    def test_explicit_exclusion_and_no_missing_labels(self):
        labels = self.labels()
        labels["cases"][0].update(expected=None, exclusion_reason="Ambiguous source")
        result = score(self.pack, self.windows, labels, self.hybrid)["groups"]["uniform"]
        self.assertEqual(result["excluded"], 1)
        labels["cases"].pop()
        with self.assertRaises(ValueError):
            read_labels(labels, self.pack, self.hybrid)

    def test_tampered_and_stale_samples_rejected(self):
        sample = copy.deepcopy(self.sample)
        sample["cases"][0]["text"] = "changed"
        with self.assertRaises(ValueError):
            recover_context(sample, self.work, self.hybrid)
        sample["sample_sha256"] = digest({k: v for k, v in sample.items() if k != "sample_sha256"})
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            recover_context(sample, self.work, self.hybrid)
        path = next(iter(self.originals))
        path.write_bytes(self.originals[path] + b"\n")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            recover_context(self.sample, self.work, self.hybrid)

    def test_holdout_sample_refused(self):
        holdout = scan(self.work, partition="holdout", uniform_count=100, targeted_count=0)
        with self.assertRaisesRegex(ValueError, "development"):
            recover_context(holdout, self.work, self.hybrid)

    def test_labels_reject_wrong_binding_and_anchor(self):
        labels = self.labels()
        labels["context_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            read_labels(labels, self.pack, self.hybrid)
        labels = self.labels()
        row = next(row for row in labels["cases"] if row["expected"])
        row["expected"][0]["spans"].pop(0)
        with self.assertRaises(ValueError):
            read_labels(labels, self.pack, self.hybrid)


if __name__ == "__main__":
    unittest.main()
