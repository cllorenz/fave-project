#!/bin/bash
# From fave/: bash bench/campaigns/results_inc_dev_d16_fave_20261017/run.sh
# The converged D16 run (INCREMENTAL_PLAN.md D16, D17), its phases in order.
# Resumable: every queue skips the cells that have a result. Preparation
# (MACHINE.txt, ARTIFACTS.txt, the inputs) is done once, before declaration,
# by prepare.sh.
set -u
OUT=bench/campaigns/results_inc_dev_d16_fave_20261017
PY=../.venv/bin/python3
log() { echo "$(date -u +%FT%TZ) $*" >> $OUT/run.log; }
log "phase 1: the main queue (4 pinned jobs, V5's limit class, packing by reservation)"
$PY bench/incremental_queue.py --queue $OUT/queue.json --out-dir $OUT/cells \
    --jobs 4 --mem-budget 56000 --limit-rss 32768 --memory-floor 2000 --pin >> $OUT/run.log 2>&1
log "phase 1 exit rc=$?"
log "phase 2: the contention sample (serial, unpinned)"
$PY bench/incremental_queue.py --queue $OUT/contention_queue.json --out-dir $OUT/contention \
    --jobs 1 --mem-budget 64000 --limit-rss 32768 --memory-floor 2000 >> $OUT/run.log 2>&1
log "phase 2 exit rc=$?"
log "phase 3: the bridge (V5's live layout, serial)"
$PY bench/cell_queue.py --queue $OUT/bridge_queue.json --out-dir $OUT/bridge >> $OUT/run.log 2>&1
log "phase 3 exit rc=$?"
log "end: the artifacts and inputs against their records"
$PY bench/campaign_stamps.py check $OUT >> $OUT/run.log 2>&1; log "artifacts rc=$?"
$PY bench/campaign_inputs.py check $OUT >> $OUT/run.log 2>&1; log "inputs rc=$?"
log "runner exit"
