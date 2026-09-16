#!/usr/bin/env bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

RUNS=10
BENCH=$1
RESULTS=$2

BDIR=$BENCH"_json_vanilla"
export PYTHONIOENCODING=utf8
HDR_LEN=$(cat $BDIR/config.json | "$PYTHON" -c "import sys, json; print(json.load(sys.stdin)['length'])")

mkdir -p $RESULTS/$BENCH

echo -n "run $BENCH:"
for i in $(seq 1 $RUNS); do
    echo -n " $i"
    RDIR=$RESULTS/$BENCH/$i.vnp
    mkdir -p $RDIR
    ~/hassel-public/net_plumber/Ubuntu-NetPlumber-Release/net_plumber --hdr-len $HDR_LEN --load $BDIR --policy $BDIR/policy.json > $RDIR/stdout.log 2> $RDIR/stderr.log
done
echo ""
