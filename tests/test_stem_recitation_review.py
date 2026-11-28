import json
from pathlib import Path
from types import MappingProxyType
import unittest

from stem.compiler import compile_corpus
from stem.corpus_model import load_corpus, mathematical_digest
from stem.dictionary import Dictionary, Entry, normalize_alias
from stem.matcher import recognize

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class RecitationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = [json.loads(path.read_text(encoding="utf-8"))
                        for path in sorted(FIXTURES.glob("stem_recitation_*.json"))]
        cls.rows = [row for fixture in cls.fixtures for row in fixture["rows"]]
        cls.representations = {}
        entries, aliases = [], {}
        for concept in load_corpus():
            for rep in concept["representations"]:
                key = concept["id"] + ":" + rep["id"]
                cls.representations[key] = (concept, rep)
                if rep["mathematical_review"]["status"] != "approved" or not rep["spoken_aliases"]:
                    continue
                entry = Entry(key, concept["name"], concept["subject"], rep["latex"],
                              tuple(normalize_alias(alias) for alias in rep["spoken_aliases"]), "review-fixture")
                entries.append(entry)
                for phrase in entry.aliases:
                    aliases[phrase] = entry
        cls.dictionary = Dictionary(tuple(entries), MappingProxyType(aliases), "test-only")

    def test_review_fixture_binds_exact_math_and_aliases(self):
        self.assertTrue(self.fixtures)
        self.assertTrue(self.rows)
        for fixture in self.fixtures:
            self.assertEqual(fixture["schema"], "fitbaus.stem.recitation-review-fixture/v1")
            self.assertEqual(fixture["qualification"], "scope_review_only")
            self.assertTrue(fixture["rows"])
        ids = set()
        for row in self.rows:
            with self.subTest(id=row["id"]):
                self.assertNotIn(row["id"], ids)
                ids.add(row["id"])
                concept, rep = self.representations[row["id"]]
                self.assertEqual(rep["latex"], row["latex"])
                self.assertEqual(mathematical_digest(concept, rep), row["mathematical_sha256"])
                self.assertEqual(sorted(rep["spoken_aliases"]), sorted(row["aliases"]))
                self.assertTrue(row["scope_review"].strip())

    def test_all_representations_have_scope_review_fixtures(self):
        self.assertEqual({row["id"] for row in self.rows}, set(self.representations))

    def test_positive_recitations_and_source_spans(self):
        for row in self.rows:
            for phrase in row["aliases"]:
                for text in (phrase, "The formula is " + phrase.upper() + "."):
                    with self.subTest(id=row["id"], text=text):
                        matches = recognize(text, self.dictionary)
                        self.assertEqual(len(matches), 1)
                        match = matches[0]
                        self.assertEqual(match.dictionary_id, row["id"])
                        self.assertEqual(match.latex, row["latex"])
                        self.assertEqual(text[match.start:match.end], match.source_text)
                        self.assertEqual(normalize_alias(match.source_text), normalize_alias(phrase))

    def test_ambiguous_and_changed_equations_do_not_match(self):
        for row in self.rows:
            for phrase in row["negative_phrases"]:
                for text in (phrase, "The formula is " + phrase + "."):
                    with self.subTest(id=row["id"], text=text):
                        self.assertEqual(recognize(text, self.dictionary), ())

    def test_pending_review_does_not_enter_compiled_candidates(self):
        artifact = compile_corpus()
        eligible = {row["id"] for row in artifact["entries"]}
        for row in self.rows:
            _, rep = self.representations[row["id"]]
            if rep["recognition_review"]["status"] != "approved":
                self.assertNotIn(row["id"], eligible)
        self.assertFalse(artifact["release_qualified"])


if __name__ == "__main__":
    unittest.main()
