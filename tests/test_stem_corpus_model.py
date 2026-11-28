import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from stem.corpus_model import ROOT, load_corpus, mathematical_digest, recognition_digest, report
from stem.dictionary import CURATED


class CorpusModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "corpus"
        shutil.copytree(ROOT, self.root)

    def change(self, edit):
        path = self.root / "physics" / "relativity" / "mass_energy.json"
        concept = json.loads(path.read_text(encoding="utf-8"))
        edit(concept)
        path.write_text(json.dumps(concept), encoding="utf-8")

    def test_seed_mathematical_identity_parity(self):
        concepts = load_corpus(self.root)
        seed = json.loads(CURATED.read_text(encoding="utf-8"))["entries"]
        by_id = {c["id"]: c for c in concepts}
        for entry in seed:
            concept = by_id[entry["id"]]
            rep = next(r for r in concept["representations"] if r["id"] == "standard")
            self.assertEqual(concept["name"], entry["name"])
            self.assertEqual(rep["latex"], entry["latex"])
        summary = report(concepts)
        self.assertGreaterEqual(summary["concepts"], 20)
        self.assertFalse(summary["release_qualified"])
        self.assertEqual(summary["corpus_sha256"], report(load_corpus(self.root))["corpus_sha256"])

    def test_bad_path_duplicate_key_and_unknown_source(self):
        path = self.root / "physics" / "relativity" / "mass_energy.json"
        wrong = path.with_name("wrong.json")
        path.rename(wrong)
        with self.assertRaisesRegex(ValueError, "path does not match"):
            load_corpus(self.root)
        wrong.rename(path)
        self.change(lambda c: c["representations"][0]["references"][0].update(source_id="unknown"))
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate reference"):
            load_corpus(self.root)
        path.write_text('{"id":"a","id":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            load_corpus(self.root)

    def test_alias_collision(self):
        self.change(lambda c: c["representations"][0]["spoken_aliases"].append("F equals M A"))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            load_corpus(self.root)

    def test_review_digests_and_invalidation(self):
        def approve(c):
            r = c["representations"][0]
            r["mathematical_review"] = {"status": "approved", "digest": mathematical_digest(c, r),
                                        "method": ["reference"], "evidence": ["test fixture only"]}
            r["recognition_review"] = {"status": "approved", "digest": recognition_digest(c, r),
                                       "method": ["test"], "evidence": ["test fixture only"]}
        self.change(approve)
        load_corpus(self.root)
        self.change(lambda c: c["representations"][0]["spoken_aliases"].append("rest energy equals mass times c squared"))
        with self.assertRaisesRegex(ValueError, "Stale or incomplete review.*recognition_review"):
            load_corpus(self.root)
        self.change(approve)
        self.change(lambda c: c["representations"][0]["conditions"].append("Changed condition"))
        with self.assertRaisesRegex(ValueError, "Stale or incomplete review.*mathematical_review"):
            load_corpus(self.root)

    def test_candidate_source_cannot_be_approved(self):
        def edit(c):
            r = c["representations"][0]
            r["references"] = [{"source_id": "wikidata", "locator": "Q35875"}]
            r["mathematical_review"] = {"status": "approved", "digest": mathematical_digest(c, r),
                                        "method": ["reference"], "evidence": ["test fixture only"]}
        self.change(edit)
        with self.assertRaisesRegex(ValueError, "requires admitted references"):
            load_corpus(self.root)

    def test_multiple_representations_pending_without_aliases(self):
        before = report(load_corpus(self.root))["representations"]

        def edit(c):
            r = copy.deepcopy(c["representations"][0])
            r["id"] = "alternate"
            r["latex"] = "m=E/c^2"
            r["spoken_aliases"] = []
            for field in ("mathematical_review", "recognition_review"):
                r[field] = {"status": "pending", "digest": None, "method": [], "evidence": []}
            c["representations"].append(r)
        self.change(edit)
        concepts = load_corpus(self.root)
        self.assertEqual(report(concepts)["representations"], before + 1)
        mass_energy = next(c for c in concepts if c["id"] == "physics.mass_energy")
        alternate = next(r for r in mass_energy["representations"] if r["id"] == "alternate")
        self.assertEqual(alternate["mathematical_review"]["status"], "pending")
        self.assertEqual(alternate["recognition_review"]["status"], "pending")

    def test_copied_approval_cannot_authorize_new_representation(self):
        def edit(c):
            original = c["representations"][0]
            original["mathematical_review"] = {
                "status": "approved", "digest": mathematical_digest(c, original),
                "method": ["reference"], "evidence": ["test fixture only"],
            }
            original["recognition_review"] = {
                "status": "pending", "digest": None, "method": [], "evidence": [],
            }
            alternate = copy.deepcopy(original)
            alternate["id"] = "alternate"
            alternate["latex"] = "m=E/c^2"
            alternate["spoken_aliases"] = []
            c["representations"].append(alternate)
        self.change(edit)
        with self.assertRaisesRegex(ValueError, "Stale or incomplete review.*alternate.mathematical_review"):
            load_corpus(self.root)


if __name__ == "__main__":
    unittest.main()
