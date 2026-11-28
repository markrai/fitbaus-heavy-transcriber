#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3.12 >/dev/null 2>&1; then
    exec python3.12 "$root/ci.py" "$@"
fi
exec python3 "$root/ci.py" "$@"
