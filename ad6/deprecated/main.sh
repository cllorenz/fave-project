#!/usr/bin/env bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

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
time PYTHONPATH=. "$PYTHON" main.py | tee $TTY > ./main.log
