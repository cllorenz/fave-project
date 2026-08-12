#!/usr/bin/env bash
#
# APKeep exactness gate -- the Phase 0a regression tripwire (APKEEP_FAITHFUL_PLAN.md).
#
# This is the non-negotiable pre-commit check for the faithful-Stanford effort.
# It pins the behaviour APKeep already gets PROVABLY EXACT so that no core change
# (the planned faithful out-stage forwarding) can silently regress it. It does
# NOT define new assertions -- it SELECTS the exactness-critical subset of the
# existing suite and runs it as one green/red command:
#
#   1. APKeep Java core unit tests (mvn test)          -- the vendored-core contract
#   2. bundled-Stanford loop golden pin (apkeep_smoke) -- APKeep build unchanged
#   3. wl_ifi   FaVe+APKeep == oracle (missing=0/extra=0)
#   4. wl_i2    FaVe+APKeep == oracle (77k routes, exact)
#   5. wl_stanford P7a forwarding completeness == reachable.json
#   6. backend-differential  APKeep-lib == NetPlumber-lib
#
# Inputs for 3-5 are gitignored generated artifacts; this regenerates them from
# tracked sources (no live backend) exactly as the integration tier does.
#
# Usage:   PYTHON=/path/to/venv/python bash fave/test/exactness_gate.sh
#
# Exits 0 only if every step is green; prints one EXACTNESS GATE: PASS/FAIL line.
# Requires JDK + Maven + pybison (integration-tier toolchain); the pytest steps
# skip themselves if the backends are unavailable, so a skip is NOT a pass here
# -- run this in the full integration environment.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
export PYTHON

# The exactness-critical pytest files (a subset of FAVE_INTEGRATION_TESTS).
EXACT_TESTS=(
    test/test_apkeep_wl_ifi.py
    test/test_apkeep_i2.py
    test/test_apkeep_stanford.py
    test/test_backend_differential.py
)

rc=0
step() { echo; echo "== exactness[$1] =="; }

step "1/6 APKeep Java core unit tests"
( cd "$ROOT/apkeep" && mvn -q -B test ) || { echo "Java unit tests FAILED"; rc=1; }

step "2/6 bundled-Stanford loop golden pin"
bash "$ROOT/fave/test/apkeep_smoke.sh" || rc=1

step "3/6 regenerate exactness inputs (wl_ifi, wl_i2, wl_stanford)"
bash "$ROOT/fave/test/gen_wl_ifi_inputs.sh"      || rc=1
bash "$ROOT/fave/test/gen_wl_i2_inputs.sh"       || rc=1
bash "$ROOT/fave/test/gen_wl_stanford_inputs.sh" || rc=1

step "4/6 exactness pytest subset"
( cd "$ROOT/fave" && PYTHONPATH=. "$PYTHON" -m pytest -q "${EXACT_TESTS[@]}" ) || rc=1

echo
if [ "$rc" -eq 0 ]; then
    echo "EXACTNESS GATE: PASS"
else
    echo "EXACTNESS GATE: FAIL"
fi
exit "$rc"
