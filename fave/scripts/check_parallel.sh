#!/usr/bin/env bash

CHECKS=$1
THREADS=$2


for i in $(seq 0 $((THREADS-1))); do
     python2 test/check_flows.py -b -r -t "$i:$THREADS" -f "$CHECKS" &
     pids[${i}]=$!
done

for pid in ${pids[*]}; do
     wait $pid
done
