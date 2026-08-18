#!/usr/bin/env bash

# Generate the wl_up benchmark device-model JSON that test_apkeep_ndd_wlup
# consumes: topology.json / sources.json / routes.json / policies.json. These
# are gitignored generated artifacts (fave/.gitignore: bench/wl_up/*.json), so a
# clean integration checkout lacks them; this regenerates them from the tracked
# generators (topogen/routegen/policygen), which depend only on the tracked
# bench.wl_up.inventory module -- no live backend and no reachability.csv needed.
#
# The reachability ORACLE for the NDD test is the tracked frozen BDD baseline
# matrix bench/wl_up/eval/mat_apk.json, NOT reachable.json, so the ground-truth
# generation steps (reachability.csv -> reachable.json) are intentionally absent.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

W=bench/wl_up

# device model: topology + sources, routes, probes/policies
"$PYTHON" "$W/topogen.py"
"$PYTHON" "$W/routegen.py"
"$PYTHON" "$W/policygen.py"

echo "wl_up inputs generated under $W/"
