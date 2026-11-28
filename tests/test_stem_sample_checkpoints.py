import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stem.sample_checkpoints import PROFILE_PREFIX, scan, save_sample, partition_for
from transcriber.contract import AudioIdentity, Cue, MAX_WINDOW_MS, TranscriptWindow


class CheckpointSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name) / "work"
        self.identity = AudioIdentity("home", "book", "a" * 64)
        self.key = self.identity.cache_key()
        self.profile = hashlib.sha256((PROFILE_PREFIX + "auto").encode("ascii")).hexdigest()[:16]
        self.directory = self.work / self.key / self.profile
        self.directory.mkdir(parents=True)
        self.files = {}
        for index in range(12):
            start = index * MAX_WINDOW_MS
            cues = (
                Cue(start, start + 1000, "Résumé. E = mc²."),
                Cue(start + 1000, start + 2000, "Ordinary narration."),
                Cue(start + 2000, start + 3000, "The formula is not known."),
            )
            value = TranscriptWindow(self.identity, start, start + MAX_WINDOW_MS, cues).to_json()
            path = self.directory / f"{start}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            self.files[path] = path.read_bytes()
        (self.directory / "published.json").write_text("not a window", encoding="utf-8")

    def test_inventory_and_sampling_are_read_only_and_deterministic(self):
        inventory = scan(self.work, inventory=True)
        self.assertEqual(inventory["counts"]["windows"], 12)
        self.assertEqual(inventory["counts"]["cues"], 36)
        self.assertEqual(inventory["cases"], [])
        self.assertFalse(inventory["sources"][0]["profile_verified"])
        self.assertNotIn("Ordinary narration", json.dumps(inventory))
        pack = scan(self.work, uniform_count=2, targeted_count=4)
        self.assertEqual(pack, scan(self.work, uniform_count=2, targeted_count=4))
        self.assertEqual(pack["counts"]["uniform_selected"], 2)
        self.assertEqual(pack["counts"]["formula_hint_selected"], 4)
        self.assertEqual(len({row["id"] for row in pack["cases"]}), 6)
        for row in pack["cases"]:
            path = self.directory / f'{row["window_start_ms"]}.json'
            value = json.loads(self.files[path])
            self.assertEqual(row["text"], value["cues"][row["cue_index"]]["text"])
            self.assertEqual(row["checkpoint_sha256"], hashlib.sha256(self.files[path]).hexdigest())
            self.assertIsNone(row["expected"])
            self.assertEqual(row["book_key"], self.key)
        self.assertFalse(pack["labels_complete"])
        self.assertFalse(pack["recognition_qualified"])
        for path, raw in self.files.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_partition_is_disjoint_and_not_profile_dependent(self):
        one = scan(self.work, partition="development", uniform_count=100, targeted_count=0)
        two = scan(self.work, partition="holdout", uniform_count=100, targeted_count=0)
        first = {row["window_start_ms"] for row in one["cases"]}
        second = {row["window_start_ms"] for row in two["cases"]}
        self.assertTrue(first and second)
        self.assertFalse(first & second)
        self.assertEqual(len(first | second), 12)
        for row in two["cases"]:
            self.assertEqual(partition_for(42, self.key, row["window_start_ms"]), "holdout")

    def test_exact_book_and_profile_selection(self):
        self.assertEqual(scan(self.work, books=[self.key], profile_key=self.profile, inventory=True)["counts"]["windows"], 12)
        with self.assertRaisesRegex(ValueError, "not found"):
            scan(self.work, books=["0" * 64], inventory=True)
        with self.assertRaisesRegex(ValueError, "Unknown heavy profile"):
            scan(self.work, profile_key="0" * 16, inventory=True)

    def test_reject_mismatched_identity_and_malformed_windows(self):
        path = self.directory / "0.json"
        original = json.loads(self.files[path])
        for change in ({"audio_revision": "b" * 64}, {"coverage": {"start_ms": 1, "end_ms": 300000}},
                       {"cues": [{"start_ms": 0, "end_ms": 300001, "text": "bad"}]}):
            value = {**original, **change}
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(change=change), self.assertRaises(ValueError):
                scan(self.work, inventory=True)
        path.write_text('{"schema":1,"schema":2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            scan(self.work, inventory=True)

    def test_partial_window_followed_by_later_window_rejected(self):
        path = self.directory / "0.json"
        value = json.loads(self.files[path])
        value["coverage"]["end_ms"] = 10000
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Partial checkpoint"):
            scan(self.work, inventory=True)

    def test_sample_save_is_exclusive_and_rejects_traversal(self):
        pack = scan(self.work, uniform_count=1, targeted_count=1)
        output = self.work / "stem-qualification"
        path = save_sample(pack, "sample.json", output)
        self.assertEqual(json.loads(path.read_bytes()), pack)
        with self.assertRaises(FileExistsError):
            save_sample(pack, "sample.json", output)
        with self.assertRaises(ValueError):
            save_sample(pack, "../sample.json", output)


if __name__ == "__main__":
    unittest.main()
