#!/usr/bin/env bash

NPADDR=127.0.0.1
NPPORT=1234

TMPDIR=/tmp/np
mkdir -p $TMPDIR

echo "start unit tests..."
PYTHONPATH=. python2 test/unit_tests.py

echo -n "start netplumber tests..."
net_plumber --test
echo "ok"

echo -n "regressions... "
PYTHONPATH=. test/test_rpc.py
echo "ok"

echo "example network..."
bash examples/example.sh
