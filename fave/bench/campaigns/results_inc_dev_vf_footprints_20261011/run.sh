#!/bin/bash
# The indicative measurement of PROTOCOL.txt. From fave/: bash bench/campaigns/results_inc_dev_vf_footprints_20261011/run.sh
set -u
OUT=bench/campaigns/results_inc_dev_vf_footprints_20261011
PY=${PY:-../.venv/bin/python3}
cell() { # dir workload stream footprint [extra args...]
  local dir=$1 w=$2 s=$3 fp=$4; shift 4
  local d=$OUT/$dir/${w}_veriflow_${s}
  [ -e "$d" ] && return
  $PY bench/incremental_cell.py bench/$w --engine veriflow --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 \
      --footprint "$fp" "$@" --out "$d" >> $OUT/run.log 2>&1
  echo "$(date -u +%FT%TZ) $dir $w $s rc=$?" >> $OUT/run.log
}
for mode in coarse witness dead-ends witness,dead-ends; do
  dir=cells_${mode/,/+}
  for w in wl_example wl_ifi wl_airtel1 wl_cloud; do
    for s in s1 s2 s3; do cell $dir $w $s "$mode"; done
  done
done
for w in wl_ifi wl_airtel1 wl_cloud; do
  cell oracle $w s2 witness,dead-ends --oracle-sample 50 --oracle-every 50
done
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run.log
