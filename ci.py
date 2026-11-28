import argparse
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
UPSTREAM_URL = "https://github.com/markrai/fitbaus-transcriber.git"
UPSTREAM_SHA = "adb1e9530ef8f03758138703ebd737ff8e2bfe24"


def run(*args, cwd=ROOT):
    print("+ " + shlex.join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def output(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def require_python():
    if sys.version_info[:2] != (3, 12):
        raise ValueError(f"CI requires Python 3.12; found {sys.version.split()[0]}")
    print(f"Python {sys.version.split()[0]}", flush=True)


def prepare_contract(root=ROOT):
    upstream = root / ".upstream"
    if upstream.is_symlink():
        raise ValueError(".upstream must not be a symlink")
    if not upstream.exists():
        run("git", "clone", UPSTREAM_URL, ".upstream", cwd=root)
    if not upstream.is_dir():
        raise ValueError(".upstream is not a directory")
    actual_root = Path(output("git", "rev-parse", "--show-toplevel", cwd=upstream)).resolve()
    if actual_root != upstream.resolve():
        raise ValueError(".upstream is not a standalone Git checkout")
    if output("git", "status", "--porcelain", "--untracked-files=normal", cwd=upstream):
        raise ValueError(".upstream contains local changes; preserve or remove them before running CI")
    available = subprocess.run(
        ["git", "cat-file", "-e", UPSTREAM_SHA + "^{commit}"],
        cwd=upstream, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if available.returncode:
        run("git", "fetch", "--no-tags", UPSTREAM_URL, UPSTREAM_SHA, cwd=upstream)
    run("git", "checkout", "--detach", UPSTREAM_SHA, cwd=upstream)
    if output("git", "rev-parse", "HEAD", cwd=upstream) != UPSTREAM_SHA:
        raise ValueError("Pinned upstream contract checkout mismatch")


def core_steps():
    return [
        ("[Core] Pinned transcript contract", prepare_contract),
        ("[Core] Python compilation", lambda: run(
            sys.executable, "-m", "compileall", "-q", "app.py", "heavy.py", "stem", "tests", "ci.py")),
        ("[Core] Corpus validation", lambda: run(sys.executable, "-m", "stem.corpus_model")),
        ("[Core] Unit tests", lambda: run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")),
    ]


def npm_command():
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise ValueError("npm must be installed and on PATH")
    return npm


def require_node():
    version = output("node", "--version")
    if not re.fullmatch(r"v24\.\d+\.\d+", version):
        raise ValueError(f"CI requires Node.js 24; found {version}")
    print(f"Node.js {version}", flush=True)
    npm_command()


def renderer_steps():
    return [
        ("[Renderer] Node.js 24 and npm", require_node),
        ("[Renderer] Install dependencies", lambda: run(
            npm_command(), "install", "--ignore-scripts", "--no-audit", "--no-fund",
            cwd=ROOT / "stem" / "renderer")),
        ("[Renderer] Policy tests", lambda: run(
            sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-p", "test_stem_qualify_render.py", "-v")),
        ("[Renderer] Real SVG and PNG smoke", lambda: run(sys.executable, "-m", "stem.renderer_smoke")),
    ]


def print_summary(suite, results, elapsed, code, reason):
    width = max(len(label) for label, _, _ in results)
    counts = {status: sum(row[1] == status for row in results) for status in ("PASS", "FAIL", "SKIP")}
    print("\n" + "=" * 72)
    print(f"CI SUMMARY ({suite})")
    print("-" * 72)
    for label, status, duration in results:
        timing = f"{duration:.2f}s" if duration is not None else "-"
        print(f"{label:<{width}}  {status:>4}  {timing:>9}")
    print("-" * 72)
    print(f"Checks: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped")
    print(f"Elapsed: {elapsed:.2f}s")
    if reason:
        print(f"Failure: {reason}")
    print(f"RESULT: {'PASS' if code == 0 else 'FAIL'} (exit code {code})")
    print("=" * 72, flush=True)


def execute(suite, steps):
    started = time.monotonic()
    results = [(label, "SKIP", None) for label, _ in steps]
    code, reason = 0, None
    for index, (label, action) in enumerate(steps):
        print(label, flush=True)
        step_start = time.monotonic()
        try:
            action()
        except subprocess.CalledProcessError as error:
            code = error.returncode if error.returncode > 0 else 1
            reason = str(error)
        except (OSError, ValueError) as error:
            code, reason = 1, str(error)
        except KeyboardInterrupt:
            code, reason = 130, "Interrupted by user"
        results[index] = (label, "FAIL" if code else "PASS", time.monotonic() - step_start)
        if code:
            break
    print_summary(suite, results, time.monotonic() - started, code, reason)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the same checks as GitHub Actions")
    parser.add_argument("suite", choices=("all", "core", "renderer"), nargs="?", default="all")
    args = parser.parse_args(argv)
    steps = [("[Setup] Python 3.12", require_python)]
    if args.suite in ("all", "core"):
        steps.extend(core_steps())
    if args.suite in ("all", "renderer"):
        steps.extend(renderer_steps())
    return execute(args.suite, steps)


if __name__ == "__main__":
    raise SystemExit(main())
