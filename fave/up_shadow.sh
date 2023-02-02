#!/usr/bin/env bash

RES=up_anomalies/shadow

mkdir -p $RES
rm -rf $RES/*

echo -n "Run FaVe..."
for i in {1..10}; do
    echo -n " $i"
    PYTHONPATH=. python3 bench/wl_shadow/benchmark.py -u -r bench/wl_shadow/rulesets/up.fw > $RES/$i.stdout.log 2>&1
    cp /dev/shm/np/aggregator.log $RES/$i"_fave.log"
    cp /dev/shm/np/rpc.log $RES/$i"_np.log"
done
echo ""
