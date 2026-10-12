#!/bin/bash
# The calibration's wl_up apkeep cells on the fixed code (m2 at d8318633), from the worktree.
cd /tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/fave-m2/fave
for s in s1 s2 s3; do
  d=/home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_d11_calibration_20261011/cells_fixed/wl_up_apkeep_$s
  [ -e "$d" ] && continue
  FAVE_REQUIRE_BACKENDS=1 /home/ubuntu/fave-project/.venv/bin/python3 bench/incremental_cell.py bench/wl_up --engine apkeep --stream $s \
      --fraction 0.2 --seed 1 --limit-updates 50 --status-every 60 --limit-wall 7200 --out "$d" >> /home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_d11_calibration_20261011/run_fixed.log 2>&1
  echo "$(date -u +%FT%TZ) wl_up apkeep $s rc=$? (m2 d8318633, worktree)" >> /home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_d11_calibration_20261011/run_fixed.log
done
echo "$(date -u +%FT%TZ) DONE" >> /home/ubuntu/fave-project/fave/bench/campaigns/results_inc_dev_d11_calibration_20261011/run_fixed.log
