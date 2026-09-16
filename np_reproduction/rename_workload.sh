#!/usr/bin/bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

DIR=$1

for f in `ls $DIR/*.rules.json`; do
  ID=`cat $f | "$PYTHON" -c "import sys, json; print(json.load(sys.stdin)['id'])"`
  mv $f $DIR/$ID.tf.json
done
