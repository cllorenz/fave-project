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

OKS=0
SKIPS=0
FAILS=0

PYFILES=`find . -name "*.py"`

for PYFILE in $PYFILES; do
    echo -n "lint $PYFILE: "

    if [[ $IGNORE =~ $(echo "$PYFILE" | cut -d/ -f2-) ]]; then
        echo "skip"
        SKIPS=$(( $SKIPS + 1 ))
        continue
    fi

    PYTHONPATH=. pylint2 $PYFILE > $TMP 2>&1
    if [ $? -eq 0 ]; then
        echo "ok"
        OKS=$(( $OKS + 1 ))
    else
        SPY=`echo $PYFILE | cut -d/ -f2- | tr '/' '_'`
        REPORT="/tmp/lint_$SPY.log"
        cp $TMP $REPORT
        echo "fail (report at $REPORT)"
        FAILS=$(( $FAILS + 1 ))
    fi
done

echo -e "\nLinting Summary: skipped $SKIPS, succeeded $OKS, and failed $FAILS\n"

[ -f $TMP ] && rm $TMP
