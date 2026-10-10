#!/bin/bash
# The indicative measurement of PROTOCOL.txt. From fave/: bash bench/campaigns/results_inc_dev_footprints_20261010/run.sh
set -u
OUT=bench/campaigns/results_inc_dev_footprints_20261010
PY=${PY:-../.venv/bin/python3}
cell() { # dir workload engine stream footprint [extra args...]
  local dir=$1 w=$2 e=$3 s=$4 fp=$5; shift 5
  local d=$OUT/$dir/${w}_${e}_${s}
  [ -e "$d" ] && return
  local fparg=(); [ -n "$fp" ] && fparg=(--footprint "$fp")
  $PY bench/incremental_cell.py bench/$w --engine $e --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 \
      "${fparg[@]}" "$@" --out "$d" >> $OUT/run.log 2>&1
  echo "$(date -u +%FT%TZ) $dir $w $e $s rc=$?" >> $OUT/run.log
}
for mode in default witness dead-ends witness,dead-ends; do
  fp=$mode; [ "$mode" = default ] && fp=
  dir=cells_${mode/,/+}
  for w in wl_example wl_ifi wl_airtel1; do
    for e in apkeep ndd-apkeep; do
      for s in s1 s2 s3; do cell $dir $w $e $s "$fp"; done
    done
  done
  for s in s1 s2 s3; do cell $dir wl_cloud ndd-apkeep $s "$fp"; done
done
for w in wl_ifi wl_airtel1 wl_cloud; do
  cell oracle $w ndd-apkeep s2 witness,dead-ends --oracle-sample 50 --oracle-every 50
done
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run.log
