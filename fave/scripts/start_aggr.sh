#!/usr/bin/env sh

mkdir -p /tmp/np

PYTHONPATH=. python2 aggregator/aggregator.py &

PID=$!
echo $PID > /tmp/aggr.pid
sleep 0.5s
