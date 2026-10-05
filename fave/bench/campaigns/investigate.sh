#!/usr/bin/env bash
# Verification for the F1 fix: re-run the APKeep cells on the three workloads
# that carry `-o` (wl_example, wl_up, wl_tum -- the generator's own list), with
# the SAME cell definitions and limits as phase A. Only apkeep/adapter.py moved.
#
# Results go to a SEPARATE directory so phase A's pre-fix cells survive intact
# as the "before" side of the comparison.
set -u
ROOT=/home/ubuntu/fave-project
FAVE=$ROOT/fave
PY=$ROOT/.venv/bin/python3
export PATH="$ROOT/net_plumber/build:$PATH"
cd "$FAVE" || exit 1
[ -L /dev/shm/np ] || { mkdir -p /var/tmp/np-logs; rm -rf /dev/shm/np; ln -s /var/tmp/np-logs /dev/shm/np; }
exec $PY bench/cell_queue.py --queue bench/campaigns/v5_f1fix_recheck.json \
     --out-dir bench/campaigns/results_v5_f1fix
