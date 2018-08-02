#!/usr/bin/env bash

TMP=/tmp/pylint.log

# to be ignored (generated code):
IGNORE="\
ip6np/ip6tables_lexer.py \
ip6np/ip6tables_listener.py \
ip6np/ip6tables_parser.py \
test/antlr/ip6tables_lexer.py \
test/antlr/ip6tables_listener.py \
test/antlr/ip6tables_parser.py \
test/antlr/parser.py \
test/antlr/test.py \
examples/example-traverse.py
"

PYFILES=`find . -name "*.py"`

for PYFILE in $PYFILES; do
    echo -n "lint $PYFILE: "

    if [[ $IGNORE =~ $(echo "$PYFILE" | cut -d/ -f2-) ]]; then
        echo "skip"
        continue
    fi

    PYTHONPATH=. pylint $PYFILE > $TMP 2>&1
    if [ $? -eq 0 ]; then
        echo "ok"
    else
        SPY=`echo $PYFILE | cut -d/ -f2- | tr '/' '_'`
        REPORT="/tmp/lint_$SPY.log"
        cp $TMP $REPORT
        echo "fail (report at $REPORT)"
    fi
done

[ -f $TMP ] && rm $TMP
