# As run, 2026-10-10. The variant jar lived in the session scratchpad ($S below); rebuild it from
# apkeep/ with variant.diff applied (JAVA_HOME=java-11, ndd built first) and set S to reproduce.
set -u
cd /home/ubuntu/fave-project/fave
export FAVE_EXP_APKEEP_JAR=/tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/apkeep/target/apkeep-1.0.0.jar FAVE_EXP_LOG=/tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/hook.log PYTHONPATH=/tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/hook:.
for w in wl_example wl_airtel1 wl_ifi; do for s in s1 s2 s3; do
  /home/ubuntu/fave-project/.venv/bin/python3 bench/incremental_cell.py bench/$w --engine ndd-apkeep --stream $s     --fraction 0.2 --seed 1 --limit-updates 200 --status-every 60 --out /tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/cells/${w}_$s >> /tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/run.log 2>&1
  echo "$w $s rc=$?" >> /tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/run.log
done; done
echo DONE >> /tmp/claude-1000/-home-ubuntu-fave-project/02e0768e-d2d5-45e4-aa50-34e1db067075/scratchpad/portorder/run.log
