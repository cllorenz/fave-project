cd /home/ubuntu/fave-project/fave
export PYTHONPATH=.:/tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/plug FAVE_JVM_XMX=8g
for m in test/test_ndd_apkeep.py test/test_apkeep_ndd_fwd.py test/test_apkeep_ndd_wlup.py test/test_ndd_apkeep_reference.py test/test_incremental_m2_apkeep.py test/test_incremental_device_removal.py test/test_incremental_apkeep.py; do
  echo "== $m" >> /tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/tumcells/variant_tests.log
  timeout 3600 ../.venv/bin/python3 -m pytest -q -p no:warnings -p variantjars -s $m 2>&1 | grep -E "passed|failed|NddPorts from|^FAILED|^ERROR" >> /tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/tumcells/variant_tests.log
done
echo DONE >> /tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/tumcells/variant_tests.log
