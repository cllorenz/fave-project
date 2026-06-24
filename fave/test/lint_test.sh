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

# GATING POLICY: fail (exit 1) only on pylint ERROR (E) / FATAL (F) messages --
# genuine bugs (undefined names, bad calls, syntax). Style (warning/convention/
# refactor) is reported but does NOT gate. Import/name-resolution checks
# (import-error E0401, no-name-in-module E0611) are NOT gated: pylint resolves
# imports differently from the runtime PYTHONPATH, so they are env-fragile and
# noisy here; genuinely broken imports are caught by the fast/integration tiers.
# pylint exit bitmask: 1=fatal 2=error 4=warning 8=refactor 16=convention 32=usage.

export TMP=$(mktemp -d -p /tmp pylint.XXXXXX)
export RCFILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.pylintrc"

# Specific files to skip, by exact path relative to the fave/ directory.
# (Vendored Hassel trees and deprecated/ are pruned at the find stage below.)
export IGNORE_FILES="\
./examples/demo_slicing.py \
./util/dynamic_distribution.py \
"

# pylint checks that must not gate (env-fragile import/name resolution).
export NONGATING="import-error,no-name-in-module"

export OKS="$TMP/ok_files";     touch $OKS
export SKIPS="$TMP/skipped";    touch $SKIPS
export STYLE="$TMP/style";      touch $STYLE
export FAILS="$TMP/failed";     touch $FAILS

lint_file() {
    PYFILE=$1
    SPY=`echo $PYFILE | cut -d/ -f2- | tr '/' '_'`
    LOG=$TMP/lint_$SPY.log
    PRE="lint $PYFILE:"

    for ig in $IGNORE_FILES; do
        if [ "$PYFILE" = "$ig" ]; then
            echo "$PRE skip"
            echo "$PYFILE" >> $SKIPS
            return 0
        fi
    done

    PYTHONPATH=. pylint --rcfile="$RCFILE" --disable="$NONGATING" "$PYFILE" > $LOG 2>&1
    RC=$?

    if [ $((RC & 32)) -ne 0 ] || [ $((RC & 3)) -ne 0 ]; then
        # pylint usage error, fatal, or error -> gate failure
        echo "$PRE FAIL (error/fatal)"
        echo "$PYFILE" >> $FAILS
    elif [ $RC -ne 0 ]; then
        # warning/convention/refactor only -> reported, does not gate
        SCORE=`grep "Your code has been rated at" $LOG | cut -d' ' -f7-`
        echo "$PRE style ($SCORE)"
        echo "$PYFILE" >> $STYLE
    else
        echo "$PRE ok"
        echo "$PYFILE" >> $OKS
    fi
}
export -f lint_file


# Lint everything except __init__.py, deprecated/, in-repo virtualenvs /
# site-packages (a local .venv must not be linted), and the vendored Hassel trees.
PYFILES=$(find . -name '*.py' -not -name '__init__.py' \
    -not -path './deprecated/*' \
    -not -path '*/.venv/*' \
    -not -path '*/venv/*' \
    -not -path '*/site-packages/*' \
    -not -path '*/stanford-hassel/*' \
    -not -path '*/i2-hassel/*')

MAX_PROCS=$(nproc)
echo $PYFILES | xargs --max-procs $MAX_PROCS -n 1 bash -c 'lint_file "$@"' _

echo -e "\n\
Linting Summary: \
skipped $(wc -l < $SKIPS), \
ok $(wc -l < $OKS), \
style-only $(wc -l < $STYLE), \
and failed $(wc -l < $FAILS) (errors/fatals)\
\n"

NFAILS=$(wc -l < $FAILS)
if [ "$NFAILS" -gt 0 ]; then
    # Print the actual error/fatal messages so CI logs are debuggable
    # (done once, single-threaded, after the parallel run to avoid interleaving).
    echo "===== error/fatal findings (these gate the build) ====="
    while read -r f; do
        SPY=`echo "$f" | cut -d/ -f2- | tr '/' '_'`
        echo "--- $f ---"
        grep -E ":[0-9]+:[0-9]+: [EF][0-9]+" "$TMP/lint_$SPY.log" | sed 's/^/  /'
    done < $FAILS
    echo "======================================================="
fi

rm -rf $TMP

# Gate: non-zero exit if any file had error/fatal findings.
[ "$NFAILS" -eq 0 ]
