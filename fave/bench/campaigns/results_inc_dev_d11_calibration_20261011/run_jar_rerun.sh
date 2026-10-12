#!/bin/bash
# From fave/: the 12 BDD-/NDD-APKeep cells of run.sh that loaded a jar other than the declared code (run.log,
# DECLARED 2026-10-12T04:58Z), re-run on this tree's jar rebuilt from its own source. Same arguments as run.sh.
# Starts once run.sh has written DONE; sequential, nothing else of this session's alongside.
set -u
OUT=bench/campaigns/results_inc_dev_d11_calibration_20261011
PY=${PY:-../.venv/bin/python3}
until grep -q DONE $OUT/run.log; do sleep 60; done
echo "$(date -u +%FT%TZ) start; jar $(sha256sum ../apkeep/target/apkeep-1.0.0.jar | cut -c1-16) built from $(git rev-parse --short HEAD)" >> $OUT/run_jar_rerun.log
cell() { # workload-dir name engine stream [extra...]
  local w=$1 name=$2 e=$3 s=$4; shift 4
  local d=$OUT/cells_jar_rerun/${name}_${e}_${s}
  [ -e "$d" ] && return
  $PY bench/incremental_cell.py bench/$w --engine $e --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 50 --status-every 60 \
      --limit-wall 7200 "$@" --out "$d" >> $OUT/run_jar_rerun.log 2>&1
  echo "$(date -u +%FT%TZ) $name $e $s rc=$?" >> $OUT/run_jar_rerun.log
}
SJ="--checks ../checks.json --files topology=device_topology.json,policies=probes.json"
cell wl_airtel2 wl_airtel2 ndd-apkeep s1
cell wl_up wl_up ndd-apkeep s1
cell wl_stanford/stanford-json wl_stanford ndd-apkeep s1 $SJ
cell wl_i2/i2-json wl_i2 ndd-apkeep s1 $SJ
cell wl_airtel2 wl_airtel2 apkeep s2
cell wl_airtel2 wl_airtel2 ndd-apkeep s2
cell wl_up wl_up ndd-apkeep s2
cell wl_stanford/stanford-json wl_stanford ndd-apkeep s2 $SJ
cell wl_i2/i2-json wl_i2 ndd-apkeep s2 $SJ
cell wl_airtel2 wl_airtel2 apkeep s3
cell wl_airtel2 wl_airtel2 ndd-apkeep s3
cell wl_up wl_up ndd-apkeep s3
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run_jar_rerun.log
