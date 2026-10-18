#!/bin/bash
# From fave/: bash bench/campaigns/results_apkeep_structure_cost_20261018/run.sh
# Serial, one process per (workload, engine, variant); variants rotate per pair.
set -u
OUT=bench/campaigns/results_apkeep_structure_cost_20261018
PAIRS="wl_airtel1:bdd wl_airtel2:bdd wl_cloud:bdd wl_up:bdd wl_tum:bdd
wl_airtel1:ndd-apkeep wl_airtel2:ndd-apkeep wl_cloud:ndd-apkeep wl_up:ndd-apkeep
wl_stanford:ndd-apkeep wl_i2:ndd-apkeep wl_tum:ndd-apkeep"
i=0
for pair in $PAIRS; do
    w=${pair%%:*}; e=${pair##*:}
    case $w in
        wl_stanford|wl_i2) prefix=bench/$w/${w#wl_}-json ;;
        *) prefix=bench/$w ;;
    esac
    set -- plain updatable tracked
    for k in $(seq 0 $((i % 3))); do set -- "$2" "$3" "$1"; done   # rotate the order
    i=$((i + 1))
    for v in "$@"; do
        echo "$(date -u +%FT%TZ) start $w $e $v" >> $OUT/run.log
        PYTHONPATH=. timeout 21600 ../.venv/bin/python3 $OUT/probe.py $prefix bench/$w/checks.json $e $v \
            2>> $OUT/stderr.log | grep '^{' >> $OUT/results.jsonl
        echo "$(date -u +%FT%TZ) end   $w $e $v rc=${PIPESTATUS[0]}" >> $OUT/run.log
    done
done
echo "$(date -u +%FT%TZ) runner exit" >> $OUT/run.log
