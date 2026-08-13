#!/usr/bin/env bash

# Generate the wl_tum inputs that test_apkeep_tum consumes: the device model
# (topology.json / sources.json / routes.json / policies.json). These are
# gitignored generated artifacts (fave/.gitignore: bench/wl_tum/*.json).
#
# Regenerated from *tracked* sources with no live backend, mirroring the wl_tum
# benchmark's preparation (generic_benchmark._preparation + TUMBenchmark._post_
# preparation): routegen/policygen emit the (empty) routes and the universal
# probe; topogen emits the fw.tum packet_filter (pointed at the tracked
# tum-ruleset) + the source. IPv4, tum-ruleset -- matching bench/wl_tum/benchmark.py
# defaults (-4 / RULESET).

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

RULESET=bench/wl_tum/rulesets/tum-ruleset

"$PYTHON" bench/wl_tum/routegen.py
"$PYTHON" bench/wl_tum/policygen.py
"$PYTHON" bench/wl_tum/topogen.py ipv4 "$RULESET"

echo "wl_tum inputs generated under bench/wl_tum/ (topology/sources/routes/policies.json)"
