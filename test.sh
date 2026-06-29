#!/usr/bin/env bash

# FaVe test runner -- ONE suite, ONE entry point, several tiers.
#
# The same command is used by developers locally and by CI; CI must never
# redefine tests, it only selects a tier. "Local" means a tier is runnable
# without CI infrastructure -- not that it is a different set of tests.
#
# Usage:
#   ./test.sh fast          Pure-Python unit tests, no native deps. Runs
#                           natively in <1s. The inner-loop gate (run on save).
#   ./test.sh integration   NetPlumber C++ tests + bison-dependent FaVe tests.
#                           Needs build + pybison, but NO running backend, so it
#                           is deterministic -- suitable to gate merges.
#   ./test.sh e2e           Tests needing a live net_plumber backend: test_rpc
#                           + smoke (example.sh + wl_example + wl_ifi). Process
#                           orchestration / /dev/shm state -> non-gating first.
#   ./test.sh smoke         Just the smoke subset of e2e (example.sh + benches).
#   ./test.sh bench         Large benchmarks (wl_up/wl_tum/wl_stanford/wl_i2).
#                           CI / nightly only.
#   ./test.sh all           fast + integration + e2e (excludes bench).
#
# Tier membership is decided by DEPENDENCY FOOTPRINT, not runtime:
#   fast        = pure Python
#   integration = needs build + pybison, but NOT a live backend (deterministic)
#   e2e         = needs a running net_plumber process + /dev/shm state
#
# Environment:
#   PYTHON     Python interpreter to use (default: python3). For the fast tier,
#              point this at a venv that has `pip install -r requirements.txt`.
#   COVERAGE   If set to 1, Python tests run under coverage and a report is
#              printed at the end (used by CI; off by default to keep it fast).
#   COVERAGE_MIN  If set (with COVERAGE=1), gate on total coverage via
#              `coverage report --fail-under=$COVERAGE_MIN`; the tier FAILS if
#              coverage drops below it. The ratchet floor -- bump it up as
#              coverage rises, never down. Opt-in: CI sets it for the fast tier;
#              a bare COVERAGE=1 run just prints the report.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
COVERAGE="${COVERAGE:-0}"

# FaVe test modules that are NOT pure-Python and so are excluded from `fast`.
# Listing the *exceptions* (rather than an allow-list of fast tests) means new
# pure-Python tests are auto-discovered into the fast tier -- no registry to
# forget to update. They are split by what they need so the deterministic
# `integration` tier and the backend-dependent `e2e` tier run independently.
FAVE_INTEGRATION_TESTS=(   # need pybison/JVM build, but NOT a running backend (deterministic)
    test/test_topology.py
    test/test_packet_filter.py
    test/test_iptables_parser.py
    test/test_apkeep_lib.py   # libapkeep + reachability (JPype + apkeep jar); skips if unavailable
    test/test_apkeep_adapter.py  # APKeepAdapter: FaVe model -> APKeep (P4); skips if unavailable
    test/test_apkeep_wl_ifi.py   # APKeepAdapter driven by the real wl_ifi models (P4); skips if unavailable
)
FAVE_E2E_TESTS=(           # need a live net_plumber backend + /dev/shm state
    test/test_rpc.py
    test/test_lib_equivalence.py  # libnetplumber vs net_plumber-RPC (skips if .so unbuilt)
)
# Everything excluded from the fast tier (pure-Python discovery ignores these).
FAVE_NATIVE_TESTS=( "${FAVE_INTEGRATION_TESTS[@]}" "${FAVE_E2E_TESTS[@]}" )

# When measuring coverage, pin the data file to an absolute path. `coverage run
# -p` runs from different CWDs (repo root for the fast tier, fave/ for the
# integration tier); without this the parallel data files land in different
# directories and `coverage combine` (run from $ROOT) finds nothing.
if [ "$COVERAGE" = "1" ]; then
    export COVERAGE_FILE="$ROOT/.coverage"
fi

# ---- pytest plumbing --------------------------------------------------------

# Echo a pytest invocation, optionally wrapped in coverage (parallel mode so
# the two invocations -- policy_translator and fave -- can be combined).
pytest_cmd() {
    if [ "$COVERAGE" = "1" ]; then
        echo "$PYTHON -m coverage run -p -m pytest"
    else
        echo "$PYTHON -m pytest"
    fi
}

# Print the combined coverage report. If COVERAGE_MIN is set, gate on it
# (`coverage report --fail-under`) and return non-zero when total coverage drops
# below the floor -- the ratchet. COVERAGE_MIN is opt-in (CI sets it for the
# fast tier); a bare `COVERAGE=1` local run just prints the report, no gate.
coverage_report() {
    [ "$COVERAGE" = "1" ] || return 0
    echo "== coverage report =="
    local fail_under=()
    [ -n "${COVERAGE_MIN:-}" ] && fail_under=(--fail-under "$COVERAGE_MIN")
    ( cd "$ROOT" && "$PYTHON" -m coverage combine && \
        "$PYTHON" -m coverage report "${fail_under[@]}" )
}

# ---- tiers ------------------------------------------------------------------

run_fast() {
    local rc=0 pt
    pt="$(pytest_cmd)"

    echo "== fast: policy_translator =="
    ( cd "$ROOT" && PYTHONPATH=policy_translator $pt policy_translator/test ) || rc=1

    echo "== fast: fave (pure-Python units) =="
    local ignores=()
    local t
    for t in "${FAVE_NATIVE_TESTS[@]}"; do ignores+=("--ignore=fave/$t"); done
    ( cd "$ROOT" && PYTHONPATH=fave $pt fave/test "${ignores[@]}" ) || rc=1

    return $rc
}

run_smoke() {
    local rc=0
    echo "== smoke: example.sh =="
    ( cd "$ROOT/fave" && PYTHONPATH=. bash examples/example.sh ) || rc=1
    echo "== smoke: wl_example =="
    ( cd "$ROOT/fave" && PYTHONPATH=. "$PYTHON" bench/wl_example/benchmark.py ) || rc=1
    echo "== smoke: wl_ifi =="
    ( cd "$ROOT/fave" && PYTHONPATH=. "$PYTHON" bench/wl_ifi/benchmark.py ) || rc=1
    return $rc
}

run_integration() {
    local rc=0 pt
    pt="$(pytest_cmd)"

    echo "== integration: NetPlumber C++ unit tests =="
    make -j -C "$ROOT/net_plumber/build" test || rc=1

    # Build APKeep (+ CLI golden pin) BEFORE the fave pytest step, so the
    # libapkeep test (test_apkeep_lib) finds the jar; it skips otherwise.
    echo "== integration: APKeep build + bundled-Stanford golden pin =="
    bash "$ROOT/fave/test/apkeep_smoke.sh" || rc=1

    echo "== integration: fave bison-dependent tests (no backend) =="
    ( cd "$ROOT/fave" && PYTHONPATH=. $pt "${FAVE_INTEGRATION_TESTS[@]}" ) || rc=1

    return $rc
}

run_e2e() {
    local rc=0 pt
    pt="$(pytest_cmd)"

    echo "== e2e: fave tests needing a live net_plumber backend =="
    ( cd "$ROOT/fave" && PYTHONPATH=. $pt "${FAVE_E2E_TESTS[@]}" ) || rc=1

    run_smoke || rc=1
    return $rc
}

run_bench() {
    local rc=0 wl
    for wl in wl_up wl_tum wl_stanford wl_i2; do
        echo "== bench: $wl =="
        ( cd "$ROOT/fave" && PYTHONPATH=. "$PYTHON" "bench/$wl/benchmark.py" ) || rc=1
    done
    return $rc
}

# ---- dispatch ---------------------------------------------------------------

tier="${1:-}"
rc=0
case "$tier" in
    fast)        run_fast || rc=1 ;;
    smoke)       run_smoke || rc=1 ;;
    integration) run_integration || rc=1 ;;
    e2e)         run_e2e || rc=1 ;;
    bench)       run_bench || rc=1 ;;
    all)         run_fast || rc=1; run_integration || rc=1; run_e2e || rc=1 ;;
    *)
        echo "usage: $0 {fast|smoke|integration|e2e|bench|all}" >&2
        exit 2
        ;;
esac

coverage_report || rc=1

if [ "$rc" -eq 0 ]; then
    echo "RESULT: $tier PASSED"
else
    echo "RESULT: $tier FAILED"
fi
exit "$rc"
