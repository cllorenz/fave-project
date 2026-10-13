#!/usr/bin/env bash

# Generate the wl_example inputs (gitignored) that the integration tier's
# incremental, NDD and packet-filter tests read -- without running the
# benchmark (TODO item 49). The steps are the benchmark's own:
# bench/wl_example/benchmark.py's `workload().generate_inputs()`, the input
# half of GenericBenchmark._preparation, so benchmark.py stays their only
# definition. No backend starts, and nothing under /dev/shm/np is deleted. The
# logging is configured first so that the constructor's own basicConfig is a
# no-op: it would truncate /dev/shm/np/fave.log, which may be a live run's.
#
# The steps discard their exit status (os.system), so the outputs are removed
# first and checked last: a missing file fails this script rather than a test
# an hour later.

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"
W=bench/wl_example
OUTPUTS=("$W"/{topology,routes,sources,policies,checks,cchecks,inventory,reachable,roles}.json
         "$W/reachability.csv")
# Removed first, so a step that fails cannot leave a stale file to pass for it.
rm -f "${OUTPUTS[@]}"
"$PYTHON" -c '
import logging
logging.basicConfig(handlers=[logging.NullHandler()])
from bench.wl_example.benchmark import workload
workload().generate_inputs()'
for f in "${OUTPUTS[@]}"; do
    [ -s "$f" ] || { echo "gen_wl_example_inputs: $f not produced" >&2; exit 1; }
done
echo "wl_example inputs generated under $W/"
