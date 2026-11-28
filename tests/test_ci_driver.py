import contextlib
import io
import subprocess
import sys
import unittest
from unittest.mock import call, patch

import ci


class CIDriverTests(unittest.TestCase):
    def setUp(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))

    def test_core_uses_pinned_contract_and_expected_checks(self):
        with patch.object(ci, "prepare_contract") as prepare, patch.object(ci, "run") as run:
            self.assertEqual(ci.execute("core", ci.core_steps()), 0)
        prepare.assert_called_once_with()
        self.assertEqual(run.call_args_list, [
            call(sys.executable, "-m", "compileall", "-q", "app.py", "heavy.py", "companions.py", "epub_inventory.py", "epub_alignment.py",
                 "ci.py", "test_suite.py", *(str(path.relative_to(ci.ROOT)) for path in ci.test_paths("core"))),
            call(sys.executable, "test_suite.py", "core"),
        ])

    def test_renderer_uses_install_policy_and_real_smoke(self):
        with patch.object(ci, "output", return_value="v24.11.0"), \
                patch.object(ci.shutil, "which", return_value="npm-test"), \
                patch.object(ci, "run") as run:
            self.assertEqual(ci.execute("renderer", ci.renderer_steps()), 0)
        self.assertEqual(run.call_args_list, [
            call("npm-test", "install", "--ignore-scripts", "--no-audit", "--no-fund",
                 cwd=ci.ROOT / "stem" / "renderer"),
            call(sys.executable, "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_stem_qualify_render.py", "-v"),
            call(sys.executable, "-m", "stem.renderer_smoke"),
        ])

    def test_default_runs_core_only(self):
        order = []
        with patch.object(ci, "require_python"), \
                patch.object(ci, "core_steps", return_value=[("core", lambda: order.append("core"))]), \
                patch.object(ci, "stem_steps") as stem, patch.object(ci, "renderer_steps") as renderer:
            self.assertEqual(ci.main([]), 0)
        self.assertEqual(order, ["core"])
        stem.assert_not_called()
        renderer.assert_not_called()
        self.assertIn("Checks: 2 passed, 0 failed, 0 skipped", self.stdout.getvalue())

    def test_all_runs_three_suites_in_order(self):
        order = []
        with patch.object(ci, "require_python"), \
                patch.object(ci, "core_steps", return_value=[("core", lambda: order.append("core"))]), \
                patch.object(ci, "stem_steps", return_value=[("stem", lambda: order.append("stem"))]), \
                patch.object(ci, "renderer_steps", return_value=[("renderer", lambda: order.append("renderer"))]):
            self.assertEqual(ci.main(["all"]), 0)
        self.assertEqual(order, ["core", "stem", "renderer"])

    def test_stem_only_prepares_contract_and_runs_dormant_tests(self):
        with patch.object(ci, "require_python"), patch.object(ci, "prepare_contract") as prepare, \
                patch.object(ci, "run") as run, patch.object(ci, "core_steps") as core:
            self.assertEqual(ci.main(["stem"]), 0)
        prepare.assert_called_once_with()
        core.assert_not_called()
        self.assertEqual(run.call_args_list, [
            call(sys.executable, "-m", "compileall", "-q", "stem",
                 *(str(path.relative_to(ci.ROOT)) for path in ci.test_paths("stem"))),
            call(sys.executable, "-m", "stem.corpus_model"),
            call(sys.executable, "test_suite.py", "stem"),
        ])

    def test_test_selection_is_exhaustive_and_disjoint(self):
        core = set(ci.test_paths("core"))
        stem = set(ci.test_paths("stem"))
        self.assertFalse(core & stem)
        self.assertEqual(core | stem, set((ci.ROOT / "tests").glob("test_*.py")))
        self.assertTrue(all(path.name.startswith("test_stem") for path in stem))
        self.assertTrue(all(not path.name.startswith("test_stem") for path in core))

    def test_core_failure_is_propagated_and_stops_all(self):
        with patch.object(ci, "require_python"), \
                patch.object(ci, "prepare_contract", side_effect=subprocess.CalledProcessError(7, ["test"])), \
                patch.object(ci, "run") as run:
            self.assertEqual(ci.main(["all"]), 7)
        run.assert_not_called()
        summary = self.stdout.getvalue().split("CI SUMMARY (all)", 1)[1]
        self.assertRegex(summary, r"Pinned transcript contract\s+FAIL")
        self.assertRegex(summary, r"Real SVG and PNG smoke\s+SKIP")
        self.assertIn("Checks: 1 passed, 1 failed, 9 skipped", summary)
        self.assertIn("RESULT: FAIL (exit code 7)", summary)

    def test_wrong_node_version_rejected_before_install(self):
        with patch.object(ci, "require_python"), \
                patch.object(ci, "output", return_value="v22.1.0"), patch.object(ci, "run") as run:
            self.assertEqual(ci.main(["renderer"]), 1)
        run.assert_not_called()
        summary = self.stdout.getvalue().split("CI SUMMARY (renderer)", 1)[1]
        self.assertIn("CI requires Node.js 24; found v22.1.0", summary)
        self.assertIn("Checks: 1 passed, 1 failed, 3 skipped", summary)
        self.assertNotIn("[Core]", summary)

    def test_python_failure_skips_all_selected_checks(self):
        with patch.object(ci, "require_python", side_effect=ValueError("Wrong Python")), \
                patch.object(ci, "prepare_contract") as prepare:
            self.assertEqual(ci.main(["core"]), 1)
        prepare.assert_not_called()
        self.assertIn("Checks: 0 passed, 1 failed, 3 skipped", self.stdout.getvalue())
        self.assertIn("Failure: Wrong Python", self.stdout.getvalue())

    def test_interrupt_reports_failed_and_skipped_checks(self):
        with patch.object(ci, "require_python"), \
                patch.object(ci, "prepare_contract", side_effect=KeyboardInterrupt), \
                patch.object(ci, "run") as run:
            self.assertEqual(ci.main(["core"]), 130)
        run.assert_not_called()
        self.assertIn("Checks: 1 passed, 1 failed, 2 skipped", self.stdout.getvalue())
        self.assertIn("Failure: Interrupted by user", self.stdout.getvalue())
        self.assertIn("RESULT: FAIL (exit code 130)", self.stdout.getvalue())

    def test_core_only_does_not_run_or_report_renderer(self):
        with patch.object(ci, "require_python"), patch.object(ci, "prepare_contract"), \
                patch.object(ci, "run") as run, patch.object(ci, "renderer_steps") as renderer:
            self.assertEqual(ci.main(["core"]), 0)
        renderer.assert_not_called()
        self.assertEqual(run.call_count, 2)
        self.assertIn("Checks: 4 passed, 0 failed, 0 skipped", self.stdout.getvalue())
        self.assertNotIn("[Renderer]", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
