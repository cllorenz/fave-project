#!/usr/bin/env sh

PID=`cat /tmp/aggr.pid`
kill -9 $PID
rm /tmp/aggr.pid
