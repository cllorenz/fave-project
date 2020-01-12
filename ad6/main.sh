#!/usr/bin/env bash

check() {
	RUNS=`ps -e | grep $PID`
	echo "ps -e | grep $PID: $RUNS"
}

bash scripts/startdb.sh

#python3 src/generator/generator.py
if [ -f time.log ]; then
	rm time.log
fi

if [ -f memory.log ]; then
	rm memory.log
fi

if [ -f pre.mem.log ]; then
	echo "" > pre.mem.log
fi

if [ -f pre.mem.log ]; then
	echo "" > in.mem.log
fi
 
if [ -f post.mem.log ]; then
	echo "" > post.mem.log
fi

TTY=$(tty)
time PYTHONPATH=. python3 main.py | tee $TTY > /tmp/main.log
PID=$!

killall redis-server

exit 0

echo "python PID: $PID"
ps -o size,rssize,vsize -p $PID > memory.log

#paste pre.mem.log in.mem.log post.mem.log | sed 1d > memory.log

#exit 0

check
#RUNS=""
while [ "$RUNS" != "" ]; do
	ps -o size,rssize,vsize -p $PID | sed 1d >> memory.log
	sleep 0.2
	check
done

echo "break"


#python3 testall.py

#python3 service.py
