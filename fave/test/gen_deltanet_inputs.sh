#!/usr/bin/env bash

# Generate the benchmark input JSON that the backend differential consumes, for
# every registered Delta-net workload: topology.json / routes.json /
# sources.json / policies.json (the device model) and reachable.json (the
# policy's expected reachability), plus the FPL inventory and policy the
# translator turns into reachability.csv.
#
# Everything here is DERIVED from the vendored traces under
# bench/deltanet/traces/ (CLOUD_BENCH_PLAN.md §2) -- there is no hand-written
# half to preserve, which is why the workload directories are gitignored. A
# clean checkout has none of it, and the deterministic integration tier needs it
# without starting a backend, so this runs each benchmark's _pre_preparation and
# policy steps and stops before anything that needs a live engine.
#
# WHICH workloads: `bench/deltanet/registry.py`, not a list here (D6). Naming
# them in both places is how the two come to disagree, and a workload missing
# from the tier's generation step does not fail -- it SKIPS, which reads as
# green. Pass names to restrict it; pass none and it does the registry.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

"$PYTHON" - "$@" <<'PY'
import logging
import sys

from bench.deltanet.registry import WORKLOADS
from bench.deltanet.workload import build

logging.basicConfig(level=logging.INFO)

names = sys.argv[1:] or sorted(WORKLOADS)
for name in names:
    if name not in WORKLOADS:
        raise SystemExit(
            "%s is not a registered Delta-net workload -- have: %s"
            % (name, ', '.join(sorted(WORKLOADS))))

    run = build(name, logger=logging.getLogger('gen_%s' % name))
    # The model, the FPL inventory and the FPL policy, all from the vendored
    # traces.
    run._pre_preparation()
    # reachability.csv (PolicyTranslator) -> checks/cchecks/reachable.json.
    # Neither step needs an engine; `_preparation` itself would also delete
    # /dev/shm state a concurrent run may own, so the two steps are called
    # directly.
    run._generate_policy_matrix()
    run._convert_policy_to_checks()
    print("generated bench/%s/" % name)
PY
