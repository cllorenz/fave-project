#!/usr/bin/env bash

NPADDR=127.0.0.1
NPPORT=1234

TMPDIR=/tmp/np
mkdir -p $TMPDIR

echo -n "start netplumber... "
TMPFILE=$TMPDIR/np.log
net_plumber --hdr-len 1 --server $NPADDR $NPPORT > $TMPFILE &
NP=$!
sleep 1
echo "ok"

echo -n "regressions... "
PYTHONPATH=. test/np_tests.py
echo "ok"
kill -s KILL $NP

echo "example network..."
bash example.sh
