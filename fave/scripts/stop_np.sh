#!/usr/bin/env sh

#PERF=`cat /tmp/perf.pid`
#sudo kill -9 $PERF
#rm /tmp/perf.pid

#PID=`cat /tmp/np.pid`
#kill -9 $PID
#rm /tmp/np.pid

PYTHONPATH=. python2 scripts/stop_np.py

[ -S /tmp/net_plumber.socket ] && rm /tmp/net_plumber.socket
