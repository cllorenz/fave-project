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

# Run mypy over the typed modules and fail (non-zero) on any error. The set of
# checked files is derived from the strict per-module sections in mypy.ini, so
# adding a module to a section is all that is needed to cover it here. mypy runs
# once over the whole set (for cross-module inference) and statically, so no
# native stack is required.

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
