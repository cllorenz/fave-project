#!/usr/bin/env bash

RES=results_tum/bv

mkdir -p $RES
rm -rf $RES/*

echo -n "run benchmarks:"
for i in {1..10}; do
    echo -n " $i"
    python3 main.py -m -r rulesets/tum-ruleset > $RES/$i.stdout.log
done
echo ""
