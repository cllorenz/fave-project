#!/bin/bash
# The indicative calibration of PROTOCOL.txt. From fave/: bash bench/campaigns/results_inc_dev_20261010/run.sh
set -u
OUT=bench/campaigns/results_inc_dev_20261010
PY=${PY:-../.venv/bin/python3}
for w in wl_example wl_ifi wl_airtel1; do
  for e in netplumber veriflow apkeep; do
    for s in s1 s2 s3; do
      d=$OUT/cells/${w}_${e}_${s}
      [ -e "$d" ] && continue
      $PY bench/incremental_cell.py bench/$w --engine $e --stream $s \
          --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 \
          --out "$d" >> $OUT/run.log 2>&1
      echo "$(date -u +%FT%TZ) $w $e $s rc=$?" >> $OUT/run.log
    done
  done
done
for w in wl_ifi wl_airtel1; do
  for e in netplumber veriflow apkeep; do
    d=$OUT/oracle/${w}_${e}_s2
    [ -e "$d" ] && continue
    $PY bench/incremental_cell.py bench/$w --engine $e --stream s2 \
        --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 \
        --oracle-sample 50 --oracle-every 50 --out "$d" >> $OUT/run.log 2>&1
    echo "$(date -u +%FT%TZ) oracle $w $e rc=$?" >> $OUT/run.log
  done
done
echo "$(date -u +%FT%TZ) DONE" >> $OUT/run.log
