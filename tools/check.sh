#!/usr/bin/env bash
# Compile every module and run the suite. The short form of the verification procedure;
# see CLAUDE.md for why running the CLI on both machines is the other half.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== compile =="
# Named directories only, never `compileall .` - that would walk anything a user has
# dropped in the tree.
python3 -m compileall -q src tests tools rdtroubleshoot

echo "== suite =="
python3 -m unittest discover -s tests -b

echo "== cli smoke =="
./rdtroubleshoot --help >/dev/null
./rdtroubleshoot --guid 0003 054c 05c4 8111 | grep -qx '0-00000003-054c-0000-c405-000011810000' \
  || { echo "the pinned DualShock 4 id no longer derives correctly" >&2; exit 1; }
# Exit code must be 0/1/2 and nothing else, even where every check degrades to INFO.
set +e
./rdtroubleshoot --no-color >/dev/null 2>&1
code=$?
set -e
case "$code" in
  0|1|2) echo "exit contract OK (exited $code)" ;;
  *) echo "unexpected exit code $code" >&2; exit 1 ;;
esac

echo "all checks passed"
