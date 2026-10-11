#!/bin/bash
# From fave/: bash bench/campaigns/results_inc_dev_d11_calibration_20261011/run.sh
set -u
OUT=bench/campaigns/results_inc_dev_d11_calibration_20261011
PY=${PY:-../.venv/bin/python3}
cell() { # workload-dir name engine stream [extra...]
  local w=$1 name=$2 e=$3 s=$4; shift 4
  local d=$OUT/cells/${name}_${e}_${s}
  [ -e "$d" ] && return
  $PY bench/incremental_cell.py bench/$w --engine $e --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 50 --status-every 60 \
      --limit-wall 7200 "$@" --out "$d" >> $OUT/run.log 2>&1
  echo "$(date -u +%FT%TZ) $name $e $s rc=$?" >> $OUT/run.log
}
for s in s1 s2 s3; do
  for e in netplumber veriflow apkeep ndd-apkeep; do
    cell wl_airtel2 wl_airtel2 $e $s
    cell wl_up wl_up $e $s
  done
  for e in netplumber veriflow ndd-apkeep; do
    cell wl_stanford/stanford-json wl_stanford $e $s \
      --checks ../checks.json --files topology=device_topology.json,policies=probes.json
    cell wl_i2/i2-json wl_i2 $e $s \
      --checks ../checks.json --files topology=device_topology.json,policies=probes.json
  done
done
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run.log
