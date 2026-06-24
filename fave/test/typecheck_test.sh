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

# Type-check the typed modules and fail (non-zero) on any error. fave and
# PolicyTranslator are independent tools, so each is checked independently with
# its own config and source root; CI runs both and fails if either fails. The
# set of checked files is derived from the strict per-module sections in each
# config, so adding a module to a section is all that is needed to cover it.
# mypy runs once per tool (for cross-module inference) and statically, so no
# native stack is required.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"

cd "$ROOT"

if ! "$PYTHON" -m mypy --version >/dev/null 2>&1; then
    echo "typecheck: mypy is not installed (pip install -r requirements.txt)" >&2
    exit 2
fi

# Run mypy for one tool: $1 = source root, $2 = its mypy config. Files are
# derived from the config's per-module sections (excluding the [mypy-*]
# catch-all), mapping pkg.mod -> <root>/pkg/mod.py and pkg.* -> <root>/pkg/*.py.
run_tool() {
    local src="$1" config="$2"
    local files=() spec rel f

    while read -r spec; do
        [ -z "$spec" ] && continue
        [ "$spec" = "*" ] && continue
        if [[ "$spec" == *.\* ]]; then
            rel="${spec%.\*}"; rel="${rel//.//}"
            for f in "$src/$rel"/*.py; do
                [ -e "$f" ] || continue
                [ "$(basename "$f")" = "__init__.py" ] && continue
                files+=("$f")
            done
        else
            files+=("$src/${spec//.//}.py")
        fi
    done < <(grep -oE '^\[mypy-[^]]+\]' "$config" | sed -E 's/^\[mypy-//; s/\]$//')

    if [ "${#files[@]}" -eq 0 ]; then
        echo "typecheck: no strict [mypy-<module>] sections in $config" >&2
        return 2
    fi

    # Verify every derived path exists (catches a renamed module whose section
    # was not updated) before handing the list to mypy.
    local f2 missing=0
    for f2 in "${files[@]}"; do
        if [ ! -e "$f2" ]; then
            echo "typecheck: derived file does not exist: $f2 (stale section in $config?)" >&2
            missing=1
        fi
    done
    [ "$missing" -eq 0 ] || return 2

    echo "== typecheck: $src/ (${#files[@]} modules) =="
    # mypy may print a benign 'unused section(s): [mypy-*]' note; it does not
    # affect the result.
    PYTHONPATH="$src" "$PYTHON" -m mypy --config-file "$config" "${files[@]}"
}

rc=0
run_tool fave "$ROOT/mypy.ini" || rc=1
run_tool policy_translator "$ROOT/policy_translator/mypy.ini" || rc=1
exit "$rc"
