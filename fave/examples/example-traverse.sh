#!/usr/bin/env bash

TMPDIR=/tmp/np
mkdir -p $TMPDIR

echo -n "start netplumber... "
scripts/start_np.sh
echo "ok"
echo -n "PID: "
cat /tmp/np.pid

read -n 1 -s -r -p "press any key to continue..."
echo ""
PYTHONPATH=. python2 test/traverse.py

echo -n "stop netplumber... "
scripts/stop_np.sh
echo "ok"
