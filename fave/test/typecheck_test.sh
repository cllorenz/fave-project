#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

# GATING POLICY: run mypy over the typed "core slice" and fail (non-zero) on any
# error. mypy is binary -- it passes or it does not; there is no style/error
# split as in lint_test.sh. The catch-all `[mypy-*] ignore_errors = True` in
# mypy.ini scopes reporting to the core modules, so not-yet-typed siblings that
# the core imports do not produce noise.
#
# SINGLE SOURCE OF TRUTH: the set of checked files is DERIVED from the strict
# per-module sections in mypy.ini (`[mypy-<pkg>.<mod>]` / `[mypy-<pkg>.*]`).
# Adding a module to the migration is therefore one edit (its mypy.ini section)
# and it is automatically covered here -- no second list to keep in sync.
#
# mypy runs ONCE over the whole set (not per-file) so cross-module inference
# works. It analyses statically, so this needs no native stack (pybison etc. are
# handled by ignore_missing_imports in mypy.ini) and runs in the pure-Python
# environment, like the `fast` tier.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
CONFIG="$ROOT/mypy.ini"

cd "$ROOT"

if ! "$PYTHON" -m mypy --version >/dev/null 2>&1; then
    echo "typecheck: mypy is not installed (pip install -r requirements.txt)" >&2
    exit 2
fi

# Collect the strict per-module sections from mypy.ini, excluding the global
# [mypy] section and the [mypy-*] catch-all, then map module specs to files:
#   pkg.mod  -> fave/pkg/mod.py
#   pkg.*    -> every fave/pkg/*.py (minus __init__.py)
FILES=()
while read -r spec; do
    [ -z "$spec" ] && continue
    [ "$spec" = "*" ] && continue
    if [[ "$spec" == *.\* ]]; then
        dir="fave/${spec%.\*}"
        dir="${dir//.//}"
        for f in "$dir"/*.py; do
            [ -e "$f" ] || continue
            [ "$(basename "$f")" = "__init__.py" ] && continue
            FILES+=("$f")
        done
    else
        FILES+=("fave/${spec//.//}.py")
    fi
done < <(grep -oE '^\[mypy-[^]]+\]' "$CONFIG" | sed -E 's/^\[mypy-//; s/\]$//')

if [ "${#FILES[@]}" -eq 0 ]; then
    echo "typecheck: no strict [mypy-<module>] sections found in $CONFIG" >&2
    exit 2
fi

# Verify every derived path exists (catches a renamed module whose section was
# not updated) before handing the list to mypy.
missing=0
for f in "${FILES[@]}"; do
    if [ ! -e "$f" ]; then
        echo "typecheck: derived file does not exist: $f (stale mypy.ini section?)" >&2
        missing=1
    fi
done
[ "$missing" -eq 0 ] || exit 2

echo "typecheck: mypy over ${#FILES[@]} core modules"
# Note: mypy may print a benign 'unused section(s): [mypy-*]' note (the catch-all
# is not matched by any explicitly-checked file); it does not affect the result.
PYTHONPATH=fave "$PYTHON" -m mypy --config-file "$CONFIG" "${FILES[@]}"
