#!/usr/bin/env sh

PID=`cat /tmp/aggr.pid`
kill -15 $PID
rm /tmp/aggr.pid

[ -S /tmp/np_aggregator.socket ] && rm /tmp/np_aggregator.socket

sleep 0.5s
