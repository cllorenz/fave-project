#!/usr/bin/env bash

TMP=/tmp/pylint.log

#PYFILES=`find . -name "*.py"`
PYFILES="test/test_rpc.py netplumber/jsonrpc.py __init__.py test/test_netplumber.py netplumber/mapping.py netplumber/vector.py netplumber/model.py test/test_tree.py ip6np/tree.py test/test_topology.py topology/topology.py test/unit_tests.py test/test_utils.py util/print_util.py util/path_util.py util/packet_util.py util/match_util.py"

for PYFILE in $PYFILES; do
    echo -n "lint $PYFILE: "

    PYTHONPATH=. pylint $PYFILE > $TMP 2>&1
    [ $? -eq 0 ] && echo "ok" || ( echo "fail" && cat $TMP )

done

[ -f $TMP ] && rm $TMP
