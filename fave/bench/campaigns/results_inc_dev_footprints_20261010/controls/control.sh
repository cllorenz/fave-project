# As run, 2026-10-10; B was the session scratchpad holding the two variant jars (apkeep/ at 3209124f with NW.diff / ND.diff applied).
# Negative controls for the selectable footprints: the NDD-APKeep oracle tests with the
# mode on, against a variant jar carrying one plausible bug (NW.diff, ND.diff).
v=$1; cls=$2
cd /home/ubuntu/fave-project/fave
FAVE_EXP_APKEEP_JAR=$B/$v/apkeep/target/apkeep-1.0.0.jar FAVE_EXP_LOG=$B/hook_$v.log PYTHONPATH=$B/hook:.   /home/ubuntu/fave-project/.venv/bin/python3 -m pytest -q -p no:cacheprovider "test/test_incremental_apkeep.py::$cls"   > $B/control_$v.log 2>&1
echo "rc=$?" >> $B/control_$v.log
