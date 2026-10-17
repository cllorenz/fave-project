#!/bin/bash
# From fave/: bash bench/campaigns/results_inc_dev_bdd_cloud_trial_20261017/run.sh
# Resumable: a restart skips finished cells (bench/incremental_queue.py).
set -u
OUT=bench/campaigns/results_inc_dev_bdd_cloud_trial_20261017
../.venv/bin/python3 bench/incremental_queue.py --queue $OUT/queue.json --out-dir $OUT/cells \
    --jobs 4 --mem-budget 56000 >> $OUT/run.log 2>&1
echo "$(date -u +%FT%TZ) runner exit rc=$?" >> $OUT/run.log
