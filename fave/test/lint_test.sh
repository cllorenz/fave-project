#!/usr/bin/env bash

TMP=/tmp/pylint.log

#PYFILES=`find . -name "*.py"`
PYFILES="test/test_rpc.py netplumber/jsonrpc.py"

for PYFILE in $PYFILES; do
    echo -n "lint $PYFILE: "

    PYTHONPATH=. pylint $PYFILE > $TMP 2>&1
    [ $? -eq 0 ] && echo "ok" || ( echo "fail" && cat $TMP )

done

[ -f $TMP ] && rm $TMP
