#!/usr/bin/env bash

RUNS=10
RESULTS=results/mb_expand
mkdir -p $RESULTS
rm -rf $RESULTS/*

export PYTHONPATH=.

for count in 10 100 1000 10000 20000 30000 40000 50000 60000; do
	for i in $(seq 1 $RUNS); do
		python2 bench/wl_expand/benchmark.py -v -c $count
		cp /dev/shm/np/rpc.log $RESULTS/$count.$i.rpc.log
	done
done
