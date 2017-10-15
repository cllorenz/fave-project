#!/usr/bin/env sh

mkdir -p /tmp/np

if [ "$#" -eq "1" ]; then
    net_plumber --log4j-config $1 --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    PID=$!
else
    rm -f /tmp/np/stdout.log
    touch /tmp/np/stdout.log
    net_plumber --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    PID=$!
fi

echo $PID > /tmp/np.pid
sleep 0.5s
