import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent


def test_paths(suite, root=ROOT):
    if suite not in ("core", "stem"):
        raise ValueError("Unknown test suite")
    paths = sorted((root / "tests").glob("test_*.py"))
    selected = [path for path in paths if path.name.startswith("test_stem") == (suite == "stem")]
    if not selected:
        raise ValueError("No tests found for " + suite)
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("core", "stem"))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / ".upstream"))
    loader = unittest.TestLoader()
    tests = unittest.TestSuite()
    for path in test_paths(args.suite):
        tests.addTests(loader.discover(str(ROOT / "tests"), pattern=path.name))
    if not tests.countTestCases():
        raise ValueError("Empty test suite")
    return 0 if unittest.TextTestRunner(verbosity=2).run(tests).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
