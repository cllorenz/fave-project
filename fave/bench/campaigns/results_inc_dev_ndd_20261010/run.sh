#!/bin/bash
# The indicative calibration of PROTOCOL.txt. From fave/: bash bench/campaigns/results_inc_dev_ndd_20261010/run.sh
set -u
OUT=bench/campaigns/results_inc_dev_ndd_20261010
PY=${PY:-../.venv/bin/python3}
cell() { # workload engine stream [extra args...]
  local w=$1 e=$2 s=$3; shift 3
  local d=$OUT/$CELLDIR/${w}_${e}_${s}
  [ -e "$d" ] && return
  $PY bench/incremental_cell.py bench/$w --engine $e --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 \
      "$@" --out "$d" >> $OUT/run.log 2>&1
  echo "$(date -u +%FT%TZ) $CELLDIR $w $e $s rc=$?" >> $OUT/run.log
}
CELLDIR=cells
for w in wl_example wl_ifi wl_airtel1; do
  for e in netplumber apkeep ndd-apkeep; do
    for s in s1 s2 s3; do cell $w $e $s; done
  done
done
for e in netplumber ndd-apkeep; do
  for s in s1 s2 s3; do cell wl_cloud $e $s; done
done
CELLDIR=oracle
for w in wl_ifi wl_airtel1 wl_cloud; do
  cell $w ndd-apkeep s2 --oracle-sample 50 --oracle-every 50
done
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run.log
