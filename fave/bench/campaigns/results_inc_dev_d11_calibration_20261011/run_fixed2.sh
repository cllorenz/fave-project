#!/bin/bash
# The calibration's wl_up apkeep cells on m2 at a850ad11 (unionOf reference fix), from the worktree.
# cells_fixed/ (d8318633) ended in errors from that defect and stays as recorded.
# The three cells run in parallel, alongside the sequential calibration (declared in run.log).
W=/tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/fave-m2/fave
R=/home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_d11_calibration_20261011
cd $W
for s in s1 s2 s3; do
  ( d=$R/cells_fixed2/wl_up_apkeep_$s
    [ -e "$d" ] && exit 0
    FAVE_REQUIRE_BACKENDS=1 /home/ubuntu/fave-project/.venv/bin/python3 bench/incremental_cell.py bench/wl_up --engine apkeep --stream $s \
        --fraction 0.2 --seed 1 --limit-updates 50 --status-every 60 --limit-wall 7200 --out "$d" >> $R/run_fixed2.$s.log 2>&1
    echo "$(date -u +%FT%TZ) wl_up apkeep $s rc=$? (m2 a850ad11, worktree)" >> $R/run_fixed2.log ) &
done
wait
echo "$(date -u +%FT%TZ) DONE" >> $R/run_fixed2.log
