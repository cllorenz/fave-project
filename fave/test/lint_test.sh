
#!/usr/bin/env bash

export TMP=$(mktemp -d -p /tmp pylint.XXXXXX)

# to be ignored (generated code):
export IGNORE="\
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

    PYTHONPATH=. pylint2 $PYFILE > $LOG 2>&1
    if [ $? -eq 0 ]; then
        echo "$PRE ok"
        echo $PYFILE >> $OKS
    else
        REPORT=/tmp/lint_$SPY.log
        cp $LOG $REPORT
        echo "$PRE fail (report at $REPORT)"
        echo $PYFILE >> $FAILS
    fi
}
export -f lint_file


PYFILES=`find . -name "*.py"`

MAX_PROCS=$(nproc)
echo $PYFILES | xargs --max-procs $MAX_PROCS -n 1 bash -c 'lint_file "$@"' _

echo -e "\n\
Linting Summary: \
skipped $(wc -l < $SKIPS), \
succeeded $(wc -l < $OKS), \
and failed $(wc -l < $FAILS)\
\n"

rm -rf $TMP
