#!/usr/bin/env sh

PID=`cat /tmp/np.pid`
kill -9 $PID
rm /tmp/np.pid
