#!/usr/bin/env bash

# Generate the wl_deltanet benchmark input JSON that the backend differential
# consumes: topology.json / routes.json / sources.json / policies.json (the
# device model) and reachable.json (the policy's expected reachability), plus
# the FPL inventory and policy the translator turns into reachability.csv.
#
# Everything here is DERIVED from the two vendored traces under
# deltanet-traces/ (CLOUD_BENCH_PLAN.md §2) -- there is no hand-written half to
# preserve, which is why the whole directory is gitignored. A clean checkout has
# none of it, and the deterministic integration tier needs it without starting a
# backend, so this runs the benchmark's _pre_preparation and policy steps and
# stops before anything that needs a live engine.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

"$PYTHON" - <<'PY'
import logging

from bench.wl_deltanet.benchmark import DeltanetBenchmark, _PREFIX

logging.basicConfig(level=logging.INFO)

run = DeltanetBenchmark(_PREFIX, logger=logging.getLogger('gen_wl_deltanet'),
                        use_internet=False, strict=True)
# The model, the FPL inventory and the FPL policy, all from the vendored traces.
run._pre_preparation()
# reachability.csv (PolicyTranslator) -> checks/cchecks/reachable.json. Neither
# step needs an engine; `_preparation` itself would also delete /dev/shm state a
# concurrent run may own, so the two steps are called directly.
run._generate_policy_matrix()
run._convert_policy_to_checks()
PY

echo "wl_deltanet inputs generated under bench/wl_deltanet/"
