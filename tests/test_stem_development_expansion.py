import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from transcriber.contract import AudioIdentity, Cue, TranscriptWindow

from stem.context_observations import LABEL_SCHEMA
from stem.corpus_model import digest
from stem.development_expansion import STRATA, compare, expansion
from stem.hybrid import MASS_ENERGY, PYTHAGORAS, build_hybrid
from stem.sample_checkpoints import PROFILE_PREFIX, partition_for, scan


class DevelopmentExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, _, _ = build_hybrid()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.profile = hashlib.sha256((PROFILE_PREFIX + "auto").encode("ascii")).hexdigest()[:16]
        self.books = []
        self.holdout = []
        for book in ("math", "physics"):
            identity = AudioIdentity("home", book, "a" * 64)
            key = identity.cache_key()
            self.books.append(key)
            directory = self.work / key / self.profile
            directory.mkdir(parents=True)
            for n in range(12):
                start = n * 300000
                texts = ("a squared plus", "b squared equals c squared.",
                         "Ordinary words.", "E=m*c².", "Is the formula incorrect?",
                         "Another sentence.")
                cues = tuple(Cue(start + i * 1100, start + i * 1100 + 1000, text)
                             for i, text in enumerate(texts))
                path = directory / f"{start}.json"
                path.write_text(json.dumps(TranscriptWindow(identity, start, start + 300000, cues).to_json()),
                                encoding="utf-8")
                if partition_for(42, key, start) == "holdout":
                    self.holdout.append(path)
        self.prior = scan(self.work, books=[self.books[0]], uniform_count=1, targeted_count=0)
        for path in self.holdout:
            path.write_bytes(b"unreadable holdout content")
        self.quotas = dict(zip(STRATA, (3, 3, 3)))

    def export(self, **kwargs):
        return expansion(self.work, self.prior, self.hybrid, quotas=self.quotas, **kwargs)

    def test_replay_balanced_strata_and_no_holdout_reads(self):
        pack, originals = self.export()
        self.assertEqual(pack, self.export()[0])
        self.assertEqual(len(pack["sources"]), 2)
        self.assertTrue(self.holdout)
        prior_ids = {row["id"] for row in self.prior["cases"]}
        ids = []
        for window in pack["windows"]:
            self.assertEqual(partition_for(42, window["book_key"], window["start_ms"]), "development")
            self.assertEqual(len(window["cues"]), 6)
            ids.extend(anchor["id"] for anchor in window["anchors"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(prior_ids & set(ids))
        self.assertEqual(set(originals), {row["id"] for row in pack["windows"]})
        for source in pack["sources"]:
            self.assertEqual(source["selected"], self.quotas)

    def test_inventory_has_no_text_and_no_predictions(self):
        pack, originals = self.export(inventory=True)
        self.assertEqual((pack["windows"], originals), ([], {}))
        self.assertNotIn("a squared plus", json.dumps(pack))
        self.assertTrue(all(source["available"]["boundary_hint"] for source in pack["sources"]))

    def test_exact_cross_cue_and_single_cue_comparison(self):
        pack, originals = self.export()
        cases = []
        for window in pack["windows"]:
            for anchor in window["anchors"]:
                index = anchor["cue_index"]
                expected = []
                if index == 0:
                    expected = [{"id": PYTHAGORAS, "latex": "a^2+b^2=c^2",
                                 "spans": [{"cue_index": 0, "start": 0, "end": len("a squared plus")},
                                           {"cue_index": 1, "start": 0, "end": len("b squared equals c squared")}]}]
                elif index == 3:
                    expected = [{"id": MASS_ENERGY, "latex": "E=mc^2",
                                 "spans": [{"cue_index": 3, "start": 0, "end": len("E=m*c²")}]}]
                cases.append({"id": anchor["id"], "expected": expected, "exclusion_reason": None})
        labels = {"schema": LABEL_SCHEMA, "context_sha256": pack["context_sha256"],
                  "labeling_method": "authored test fixture", "cases": cases}
        report = compare(pack, originals, pack, labels, self.hybrid)
        group = report["contextual"]["groups"]["boundary_hint"]
        self.assertGreater(group["cross_cue_expected"], 0)
        self.assertEqual(group["cross_cue_expected"], group["cross_cue_true_positive"])
        self.assertEqual(group["true_positive"], group["identity_true_positive"])
        self.assertEqual(group["true_positive"], group["notation_true_positive"])
        self.assertEqual(report["single_cue"]["groups"]["boundary_hint"]["cross_cue_true_positive"], 0)
        self.assertFalse(report["recognition_qualified"])

    def test_prior_digest_and_selection_fail_closed(self):
        prior = copy.deepcopy(self.prior)
        prior["seed"] = 7
        with self.assertRaises(ValueError):
            expansion(self.work, prior, self.hybrid, quotas=self.quotas)
        prior["sample_sha256"] = digest({k: v for k, v in prior.items() if k != "sample_sha256"})
        with self.assertRaises(ValueError):
            expansion(self.work, prior, self.hybrid, quotas=self.quotas)
        with self.assertRaises(ValueError):
            self.export(books=["0" * 64])

    def test_source_drift_detected(self):
        pack, _ = self.export()
        row = pack["windows"][0]
        path = self.work / row["book_key"] / row["profile_key"] / f'{row["start_ms"]}.json'
        path.write_bytes(path.read_bytes() + b"\n")
        changed, originals = self.export()
        with self.assertRaises(ValueError):
            compare(changed, originals, pack, {}, self.hybrid, requalify=True)


if __name__ == "__main__":
    unittest.main()
