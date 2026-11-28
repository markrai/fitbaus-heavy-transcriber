import subprocess
import sys
import unittest
from unittest.mock import call, patch

import ci


class CIDriverTests(unittest.TestCase):
    def test_core_uses_pinned_contract_and_expected_checks(self):
        with patch.object(ci, "prepare_contract") as prepare, patch.object(ci, "run") as run:
            ci.core()
        prepare.assert_called_once_with()
        self.assertEqual(run.call_args_list, [
            call(sys.executable, "-m", "compileall", "-q", "app.py", "heavy.py", "stem", "tests", "ci.py"),
            call(sys.executable, "-m", "stem.corpus_model"),
            call(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
        ])

    def test_renderer_uses_install_policy_and_real_smoke(self):
        with patch.object(ci, "output", return_value="v22.15.0"), \
                patch.object(ci.shutil, "which", return_value="npm-test"), \
                patch.object(ci, "run") as run:
            ci.renderer()
        self.assertEqual(run.call_args_list, [
            call("npm-test", "install", "--ignore-scripts", "--no-audit", "--no-fund",
                 cwd=ci.ROOT / "stem" / "renderer"),
            call(sys.executable, "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_stem_qualify_render.py", "-v"),
            call(sys.executable, "-m", "stem.renderer_smoke"),
        ])

    def test_default_runs_both_suites_in_order(self):
        order = []
        with patch.object(ci, "require_python"), \
                patch.object(ci, "core", side_effect=lambda: order.append("core")), \
                patch.object(ci, "renderer", side_effect=lambda: order.append("renderer")):
            self.assertEqual(ci.main([]), 0)
        self.assertEqual(order, ["core", "renderer"])

    def test_core_failure_is_propagated_and_stops_all(self):
        with patch.object(ci, "require_python"), \
                patch.object(ci, "core", side_effect=subprocess.CalledProcessError(7, ["test"])), \
                patch.object(ci, "renderer") as renderer:
            self.assertEqual(ci.main([]), 7)
        renderer.assert_not_called()

    def test_wrong_node_version_rejected_before_install(self):
        with patch.object(ci, "output", return_value="v24.1.0"), patch.object(ci, "run") as run:
            with self.assertRaisesRegex(ValueError, "requires Node.js 22"):
                ci.renderer()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
