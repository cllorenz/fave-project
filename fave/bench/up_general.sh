#!/usr/bin/env bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

RES=up_anomalies/general

mkdir -p $RES
rm -rf $RES/*

echo -n "Run FaVe..."
for i in {1..10}; do
    echo -n " $i"
    PYTHONPATH=. "$PYTHON" bench/wl_shadow/benchmark.py -u -r bench/wl_shadow/rulesets/up.fw --disable-shadow --general > $RES/$i.stdout.log 2>&1
    cp /dev/shm/np/aggregator.log $RES/$i"_fave.log"
    cp /dev/shm/np/rpc.log $RES/$i"_np.log"
done
echo ""
