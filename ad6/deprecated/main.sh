#!/usr/bin/env bash

check() {
	RUNS=`ps -e | grep $PID`
	echo "ps -e | grep $PID: $RUNS"
}

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
time PYTHONPATH=. python3 main.py | tee $TTY > ./main.log
