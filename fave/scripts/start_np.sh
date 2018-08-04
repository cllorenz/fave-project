#!/usr/bin/env sh

mkdir -p /tmp/np

if [ "$#" -eq "1" ]; then
#    net_plumber --log4j-config $1 --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    [ -f /tmp/net_plumber.socket ] && rm /tmp/net_plumber.socket
    #valgrind --tool=memcheck --leak-check=full --track-origins=yes net_plumber --log4j-config $1 --hdr-len 1 --unix /tmp/net_plumber.socket >> /tmp/np/stdout.log &
    net_plumber --log4j-config $1 --hdr-len 1 --unix /tmp/net_plumber.socket >> /tmp/np/stdout.log &
    PID=$!
else
    [ -f /tmp/np/stdout.log ] && rm /tmp/np/stdout.log
    touch /tmp/np/stdout.log
    net_plumber --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    PID=$!
fi

#taskset -p 0x00000001 $PID > /dev/null

#sudo perf record -a -F 783 --call-graph dwarf -p $PID &
#PERF=$!
#echo $PERF > /tmp/perf.pid
#sleep 0.5s
