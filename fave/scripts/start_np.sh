#!/usr/bin/env sh

mkdir -p /tmp/np

net_plumber --hdr-len 1 --server 127.0.0.1 1234 > /tmp/np/stdout.log &
PID=$!
echo $PID > /tmp/np.pid
sleep 0.5s
