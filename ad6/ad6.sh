#!/usr/bin/env bash

RES=results/ad6

mkdir -p $RES
rm -rf $RES/*

export PYTHONPATH=.

echo -n "run benchmarks:"
for i in {1..10}; do
    echo -n " $i"
    python3 main.py --ruleset bench/tum/tum-ruleset > $RES/$i.stdout.log 2> $RES/$i.stderr.log
done
echo ""
