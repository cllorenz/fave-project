# As run, 2026-10-10: the calibration's NDD-APKeep cells and oracle cells, on variant F
# (F.diff: NDD-APKeep's takeAffected tests the forwarded side only). B is the
# session scratchpad holding the variant jar; rebuild it from apkeep/ with F.diff applied.
set -u
B=/tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/recheck
cd /home/ubuntu/fave-project/fave
export FAVE_EXP_APKEEP_JAR=$B/F/apkeep/target/apkeep-1.0.0.jar FAVE_EXP_LOG=$B/hook_run.log PYTHONPATH=$B/hook:.
PY=/home/ubuntu/fave-project/.venv/bin/python3
cell() { local w=$1 s=$2 d=$3; shift 3
  $PY bench/incremental_cell.py bench/$w --engine ndd-apkeep --stream $s     --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 "$@" --out $B/$d/${w}_ndd-apkeep_$s >> $B/run.log 2>&1
  echo "$(date -u +%FT%TZ) $d $w $s rc=$?" >> $B/run.log
}
for w in wl_example wl_ifi wl_airtel1 wl_cloud; do for s in s1 s2 s3; do cell $w $s cells; done; done
for w in wl_ifi wl_airtel1 wl_cloud; do cell $w s2 oracle --oracle-sample 50 --oracle-every 50; done
echo DONE >> $B/run.log
