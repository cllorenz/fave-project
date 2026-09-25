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
from bench.deltanet.workload import generate_inputs

logging.basicConfig(level=logging.INFO)

names = sys.argv[1:] or sorted(WORKLOADS)
for name in names:
    if name not in WORKLOADS:
        raise SystemExit(
            "%s is not a registered Delta-net workload -- have: %s"
            % (name, ', '.join(sorted(WORKLOADS))))

    # What "generate the inputs" MEANS is defined once, in
    # `bench.deltanet.workload`, because `run()` reaches the same steps by a
    # different route -- and two spellings of it are how a benchmark and its
    # generator come to produce almost the same directory.
    run = generate_inputs(name, logger=logging.getLogger('gen_%s' % name))
    print("generated bench/%s/ from %s" % (name, run.trace))
PY
