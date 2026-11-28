import argparse
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

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


def core():
    print("[Core] Pinned transcript contract", flush=True)
    prepare_contract()
    print("[Core] Python compilation", flush=True)
    run(sys.executable, "-m", "compileall", "-q", "app.py", "heavy.py", "stem", "tests", "ci.py")
    print("[Core] Corpus validation", flush=True)
    run(sys.executable, "-m", "stem.corpus_model")
    print("[Core] Unit tests", flush=True)
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")


def renderer():
    print("[Renderer] Node.js 22 and npm", flush=True)
    version = output("node", "--version")
    if not re.fullmatch(r"v22\.\d+\.\d+", version):
        raise ValueError(f"CI requires Node.js 22; found {version}")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise ValueError("npm must be installed and on PATH")
    print("[Renderer] Install dependencies", flush=True)
    run(npm, "install", "--ignore-scripts", "--no-audit", "--no-fund",
        cwd=ROOT / "stem" / "renderer")
    print("[Renderer] Policy tests", flush=True)
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests",
        "-p", "test_stem_qualify_render.py", "-v")
    print("[Renderer] Real SVG and PNG smoke", flush=True)
    run(sys.executable, "-m", "stem.renderer_smoke")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the same checks as GitHub Actions")
    parser.add_argument("suite", choices=("all", "core", "renderer"), nargs="?", default="all")
    args = parser.parse_args(argv)
    try:
        require_python()
        if args.suite in ("all", "core"):
            core()
        if args.suite in ("all", "renderer"):
            renderer()
    except subprocess.CalledProcessError as error:
        print(f"CI failed: {error}", file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except (OSError, ValueError) as error:
        print(f"CI failed: {error}", file=sys.stderr)
        return 1
    print(f"CI passed: {args.suite}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
