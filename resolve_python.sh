#!/usr/bin/env bash

# Find an interpreter that actually has this project's dependencies.
#
# SOURCE this, do not execute it: it defines resolve_python() and initialises
# $PYTHON / $PYTHON_FROM_ENV / $PYTHON_RESOLVED in the caller's shell.
#
#     FAVE_PYTHON_ROOT=<repo root>     # optional; defaults to this file's dir
#     . "<repo root>/resolve_python.sh"
#     resolve_python [module ...]      # probe modules, default: pytest
#
# WHY THIS EXISTS. Every tier, and the doctor especially, used to run whatever
# `python3` was first on PATH. In a container where the venv lives outside the
# checkout that is the SYSTEM interpreter, which has none of the deps -- so
# `./test.sh fast` died with "No module named pytest" and, far worse, the DOCTOR
# reported pytest/mypy/pycosat/python-sat/pybison/JPype1 as [MISSING] and exited
# FAILED while all six were installed and working. A doctor whose verdict
# depends on whether the caller remembered to activate a venv is worse than no
# doctor: its repair advice (`pip install ...`) would install into the wrong
# interpreter, and the tier it names as blocked is not blocked.
#
# WHY IT IS ITS OWN FILE. It used to live inside test.sh, so `bash
# fave/test/typecheck_test.sh` -- the invocation the README documents, and the
# one CI's typecheck job uses -- got none of it and died with "mypy is not
# installed" while mypy was installed and working in ~/.venv. One resolver, one
# set of candidate locations, every entry point.
#
# An explicit $PYTHON or an active $VIRTUAL_ENV always wins -- this only fills
# in when the caller said nothing. The candidates are exactly the two locations
# this project's own docs create: the README's in-checkout `.venv` and
# `fave/setup.sh`'s `~/.venv`. The probe modules are the caller's liveness test:
# test.sh probes `pytest` (every tier needs it), typecheck_test.sh probes `mypy`.

FAVE_PYTHON_ROOT="${FAVE_PYTHON_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHON_FROM_ENV="${PYTHON:-}"
PYTHON="${PYTHON:-python3}"
PYTHON_RESOLVED=""

resolve_python() {
    local modules=("$@")
    [ "${#modules[@]}" -eq 0 ] && modules=(pytest)
    [ -n "$PYTHON_FROM_ENV" ] && return 0
    [ -n "${VIRTUAL_ENV:-}" ] && return 0
    local candidate module ok
    for candidate in "$FAVE_PYTHON_ROOT/.venv/bin/python3" "$HOME/.venv/bin/python3"; do
        [ -x "$candidate" ] || continue
        ok=1
        for module in "${modules[@]}"; do
            "$candidate" -c "import $module" >/dev/null 2>&1 || { ok=0; break; }
        done
        if [ "$ok" -eq 1 ]; then
            PYTHON="$candidate"
            PYTHON_RESOLVED="$candidate"
            return 0
        fi
    done
    return 0
}
