#!/usr/bin/env sh

mkdir -p /tmp/np

PYTHONPATH=. python2 aggregator/aggregator.py -s /tmp/net_plumber.socket &

PID=$!
echo $PID > /tmp/aggr.pid
#taskset -p 0x00000004 $PID > /dev/null
sleep 0.5s
