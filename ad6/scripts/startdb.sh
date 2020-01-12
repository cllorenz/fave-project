#!/usr/bin/env sh

RUNNING=`ps -e | grep redis`
if [ "$RUNNING" == "" ]; then
	redis-server > redis.log &
	sleep 0.5
fi

exit 0
