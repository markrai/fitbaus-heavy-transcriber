import copy
import json
from pathlib import Path
import tempfile
import unittest

from stem.compiler import SCHEMA, canonical_bytes, compile_corpus
from stem.corpus_model import ROOT, digest, mathematical_digest, recognition_digest
from stem.dictionary import load_dictionary

PENDING = {"status": "pending", "digest": None, "method": [], "evidence": []}


class CompilerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "physics" / "relativity" / "mass_energy.json"
        self.path.parent.mkdir(parents=True)
        source = ROOT / "physics" / "relativity" / "mass_energy.json"
        self.concept = json.loads(source.read_text(encoding="utf-8"))
        registry = {"schema": "fitbaus.stem.sources/v1", "sources": [
            {"id": "curated", "status": "admitted", "provenance": "Test fixture only"},
            {"id": "candidate", "status": "candidate_only"},
        ]}
        self.registry = self.root / "sources.json"
        self.registry.write_text(json.dumps(registry), encoding="utf-8")
        rep = self.concept["representations"][0]
        rep["references"] = [{"source_id": "curated", "locator": "Test fixture only"}]
        rep["mathematical_review"] = copy.deepcopy(PENDING)
        rep["recognition_review"] = copy.deepcopy(PENDING)

    def write(self):
        self.path.write_text(json.dumps(self.concept), encoding="utf-8")

    def approve(self, rep, recognition=True):
        rep["mathematical_review"] = {
            "status": "approved", "digest": mathematical_digest(self.concept, rep),
            "method": ["test"], "evidence": ["Test fixture only"],
        }
        if recognition:
            rep["recognition_review"] = {
                "status": "approved", "digest": recognition_digest(self.concept, rep),
                "method": ["test"], "evidence": ["Test fixture only"],
            }

    def test_pending_recognition_excluded_even_with_aliases_and_math_approval(self):
        self.approve(self.concept["representations"][0], recognition=False)
        self.write()
        result = compile_corpus(self.root)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["excluded"], [{
            "id": "physics.mass_energy:standard", "reasons": ["recognition_review:pending"],
        }])
        self.assertFalse(result["release_qualified"])

    def test_pending_math_and_empty_aliases_report_separate_reasons(self):
        self.concept["representations"][0]["spoken_aliases"] = []
        self.write()
        result = compile_corpus(self.root)
        self.assertEqual(result["counts"]["exclusion_reasons"], {
            "mathematical_review:pending": 1,
            "recognition_review:pending": 1,
            "no_spoken_aliases": 1,
        })
        self.assertEqual(result["counts"]["eligible"], 0)

    def test_approved_forms_preserve_exact_identity_and_aliases(self):
        original = self.concept["representations"][0]
        original["spoken_aliases"] = ["E equals M C squared"]
        self.concept["alternate_names"] = ["Famous equation"]
        alternate = copy.deepcopy(original)
        alternate.update(id="alternate", latex="m=E/c^2", spoken_aliases=["m equals e divided by c squared"])
        self.concept["representations"].append(alternate)
        for rep in self.concept["representations"]:
            self.approve(rep)
        self.write()
        result = compile_corpus(self.root)
        self.assertEqual([row["id"] for row in result["entries"]], [
            "physics.mass_energy:alternate", "physics.mass_energy:standard",
        ])
        self.assertEqual(result["entries"][0]["latex"], "m=E/c^2")
        self.assertEqual(result["entries"][1]["aliases"], ["e equals m c squared"])
        self.assertEqual(result["counts"]["aliases"], 2)
        self.assertFalse(result["release_qualified"])
        payload = {key: value for key, value in result.items() if key != "artifact_sha256"}
        self.assertEqual(result["artifact_sha256"], digest(payload))

    def test_rejected_recognition_is_excluded(self):
        rep = self.concept["representations"][0]
        self.approve(rep)
        rep["recognition_review"]["status"] = "rejected"
        self.write()
        result = compile_corpus(self.root)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["excluded"][0]["reasons"], ["recognition_review:rejected"])

    def test_stale_review_fails_entire_compile(self):
        rep = self.concept["representations"][0]
        self.approve(rep)
        rep["spoken_aliases"].append("another test equation alias")
        self.write()
        with self.assertRaisesRegex(ValueError, "Stale or incomplete review.*recognition_review"):
            compile_corpus(self.root)

    def test_candidate_source_cannot_be_admitted(self):
        rep = self.concept["representations"][0]
        rep["references"][0]["source_id"] = "candidate"
        self.approve(rep)
        self.write()
        with self.assertRaisesRegex(ValueError, "requires admitted references"):
            compile_corpus(self.root)

    def test_global_alias_collision_fails_even_for_pending(self):
        rep = copy.deepcopy(self.concept["representations"][0])
        rep["id"] = "alternate"
        self.concept["representations"].append(rep)
        self.write()
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            compile_corpus(self.root)

    def test_approved_tex_must_pass_preflight(self):
        rep = self.concept["representations"][0]
        rep["latex"] = r"\require{evil}"
        self.approve(rep)
        self.write()
        with self.assertRaisesRegex(ValueError, "fails TeX preflight"):
            compile_corpus(self.root)

    def test_matrix_preflight_not_legacy_lexical_screen(self):
        rep = self.concept["representations"][0]
        rep["latex"] = r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"
        self.approve(rep)
        self.write()
        self.assertEqual(compile_corpus(self.root)["entries"][0]["latex"], rep["latex"])

    def test_determinism_and_source_registry_binding(self):
        self.write()
        first = compile_corpus(self.root)
        self.path.write_text(json.dumps(self.concept, sort_keys=True, indent=4), encoding="utf-8")
        registry = json.loads(self.registry.read_text(encoding="utf-8"))
        registry["sources"].reverse()
        self.registry.write_text(json.dumps(registry), encoding="utf-8")
        self.assertEqual(canonical_bytes(first), canonical_bytes(compile_corpus(self.root)))
        registry["sources"][0]["notes"] = "Changed provenance"
        self.registry.write_text(json.dumps(registry), encoding="utf-8")
        changed = compile_corpus(self.root)
        self.assertNotEqual(first["source_registry_sha256"], changed["source_registry_sha256"])
        self.assertNotEqual(first["artifact_sha256"], changed["artifact_sha256"])

    def test_repository_corpus_partition_and_legacy_isolation(self):
        first = compile_corpus()
        second = compile_corpus()
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        counts = first["counts"]
        self.assertEqual(counts["representations"], counts["eligible"] + counts["excluded"])
        self.assertEqual(len({row["id"] for row in first["entries"] + first["excluded"]}), counts["representations"])
        self.assertFalse(first["release_qualified"])
        self.assertEqual(len(load_dictionary().entries), 20)


if __name__ == "__main__":
    unittest.main()
