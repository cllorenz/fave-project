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

export TMP=$(mktemp -d -p /tmp pylint.XXXXXX)

# to be ignored (generated code):
export IGNORE="\
examples/example-traverse.py
"
export OKS="$TMP/ok_files"
touch $OKS
export SKIPS="$TMP/skipped_files"
touch $SKIPS
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

    PYTHONPATH=. pylint $PYFILE > $LOG 2>&1
    if [ $? -eq 0 ]; then
        echo "$PRE ok"
        echo $PYFILE >> $OKS
    else
        REPORT=/tmp/lint_$SPY.log
        cp $LOG $REPORT
        SCORE=$`grep "Your code has been rated at" $LOG | cut -d' ' -f7-`
        echo "$PRE fail with $SCORE (report at $REPORT)"
        echo $PYFILE >> $FAILS
    fi
}
export -f lint_file


PYFILES=`find . -not -path "deprecated" -not -name "__init__.py" -name "*.py"`

MAX_PROCS=$(nproc)
echo $PYFILES | xargs --max-procs $MAX_PROCS -n 1 bash -c 'lint_file "$@"' _

echo -e "\n\
Linting Summary: \
skipped $(wc -l < $SKIPS), \
succeeded $(wc -l < $OKS), \
and failed $(wc -l < $FAILS)\
\n"

rm -rf $TMP
