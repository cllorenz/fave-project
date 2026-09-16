#!/usr/bin/env bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

RES=results_tum/stl

mkdir -p $RES
rm -rf $RES/*

echo -n "run benchmarks:"
for i in {1..10}; do
    echo -n " $i"
    "$PYTHON" main.py -m -r rulesets/tum-ruleset > $RES/$i.stdout.log
done
echo ""
