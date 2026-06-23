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

# GATING POLICY: this script fails (exit 1) only on pylint ERROR (E) and FATAL
# (F) messages -- i.e. genuine bugs (undefined names, bad calls, broken imports).
# Warnings / conventions / refactors (style) are reported but do NOT gate, so the
# build is not held hostage to style on a research codebase. pylint's exit code
# is a bitmask: 1=fatal, 2=error, 4=warning, 8=refactor, 16=convention, 32=usage.

export TMP=$(mktemp -d -p /tmp pylint.XXXXXX)
export RCFILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.pylintrc"

# to be ignored (generated / vendored / stale demo code):
export IGNORE="\
examples/example-traverse.py \
examples/demo_slicing.py \
util/dynamic_distribution.py \
deprecated/* \
bench/wl_stanford/stanford-hassel/utils/*.py \
bench/wl_stanford/stanford-hassel/utils//test/*.py \
bench/wl_stanford/stanford-hassel/headerspace/*.py \
bench/wl_stanford/stanford-hassel/headerspace/test/*.py \
bench/wl_stanford/stanford-hassel/c-bytearray/*.py
bench/wl_stanford/stanford-hassel/cisco_router_parser.py \
bench/wl_i2/i2-hassel/utils/*.py \
bench/wl_i2/i2-hassel/utils/test/*.py \
bench/wl_i2/i2-hassel/headerspace/*.py \
bench/wl_i2/i2-hassel/headerspace/test/*.py \
bench/wl_i2/i2-hassel/c-bytearray/*.py \
bench/wl_i2/i2-hassel/juniper_parser.py
"
export OKS="$TMP/ok_files"
touch $OKS
export SKIPS="$TMP/skipped_files"
touch $SKIPS
export STYLE="$TMP/style_files"
touch $STYLE
export FAILS="$TMP/failed_files"
touch $FAILS

lint_file() {
    PYFILE=$1
    SPY=`echo $PYFILE | cut -d/ -f2- | tr '/' '_'`
    LOG=$TMP/lint_$SPY.log

    PRE="lint $PYFILE:"

    if [[ $IGNORE =~ $(echo "$PYFILE" | cut -d/ -f2-) ]]; then
        echo "$PRE skip"
        echo $PYFILE >> $SKIPS
        return 0
    fi

    PYTHONPATH=. pylint --rcfile="$RCFILE" $PYFILE > $LOG 2>&1
    RC=$?
    REPORT=/tmp/lint_$SPY.log

    if [ $((RC & 32)) -ne 0 ]; then
        # pylint usage error (e.g. could not run) -> treat as a gate failure
        cp $LOG $REPORT
        echo "$PRE FAIL (pylint usage error; report at $REPORT)"
        echo $PYFILE >> $FAILS
    elif [ $((RC & 3)) -ne 0 ]; then
        # fatal (1) and/or error (2) -> genuine bug -> gate failure
        cp $LOG $REPORT
        echo "$PRE FAIL (error/fatal; report at $REPORT)"
        echo $PYFILE >> $FAILS
    elif [ $RC -ne 0 ]; then
        # warning/convention/refactor only -> reported, does not gate
        SCORE=`grep "Your code has been rated at" $LOG | cut -d' ' -f7-`
        echo "$PRE style ($SCORE)"
        echo $PYFILE >> $STYLE
    else
        echo "$PRE ok"
        echo $PYFILE >> $OKS
    fi
}
export -f lint_file


PYFILES=`find . -not -path "deprecated" -not -name "__init__.py" -name "*.py"`

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
    echo "Files with error/fatal findings (gating):"
    sed 's/^/  /' $FAILS
fi

rm -rf $TMP

# Gate: non-zero exit if any file had error/fatal findings.
[ "$NFAILS" -eq 0 ]
