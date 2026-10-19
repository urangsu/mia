#!/usr/bin/env bash
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' 'Run bash scripts/codex_setup.sh first.' >&2
  exit 1
fi
.venv/bin/python -m unittest discover -s . -p 'test*.py' -v
.venv/bin/python -W error::ResourceWarning -m unittest discover -s . -p 'test_v37*.py' -q
.venv/bin/python -c 'import pathlib,py_compile; files=list(pathlib.Path(".").glob("*.py")); [py_compile.compile(str(p),doraise=True) for p in files]; print("Compile OK:",len(files))'
.venv/bin/python benchmark_v37.py --runs 10
printf '%s\n' 'Offline checks passed. Live browser, Windows COM, scheduler and ECM server remain separate acceptance gates.'
