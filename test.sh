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
#   ./test.sh doctor        Check the ENVIRONMENT, run no tests: which declared
#                           dependencies are missing, which tier each one
#                           blocks, and the exact command to repair it. Run
#                           this FIRST in a fresh container -- a missing system
#                           package usually surfaces as something that looks
#                           unrelated (see the notes in run_doctor).
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
# Interpreter resolution lives in resolve_python.sh so that the standalone gates
# (fave/test/typecheck_test.sh) get exactly the same answer as this runner --
# it used to be inline here, and they got none of it. See that file for why.
FAVE_PYTHON_ROOT="$ROOT"
. "$ROOT/resolve_python.sh"

# EXPORT it, do not merely set it. Every script this runner shells out to --
# examples/example.sh, scripts/start_aggr.sh, the gen_wl_*_inputs.sh generators,
# typecheck_test.sh, lint_test.sh -- already honours `PYTHON="${PYTHON:-python3}"`,
# but an unexported shell variable reaches none of them, so they all fell back to
# whatever `python3` PATH resolved: the SYSTEM interpreter, with none of FaVe's
# dependencies. resolve_python then "worked" for this file's own pytest calls while
# the smoke tier died on `No module named 'filelock'` in a backgrounded aggregator
# nobody reads, and all 13 example flow checks failed as though the MODEL were
# wrong. One `export` is the whole fix for every script that already asks.
export PYTHON

# scripts/start_np.sh invokes a BARE `net_plumber`, so the binary has to be on
# PATH -- `make -C net_plumber/build install` is what normally puts it there.
# A sandbox that resets system state keeps the build directory (it lives in the
# repo) but loses /usr/local/bin, so the binary is present and unreachable at
# the same time. The failure that produces is maximally misleading: start_np.sh
# backgrounds the process and reports "ok" regardless, the aggregator then
# cannot reach NetPlumber on 44001, and every flow check fails as though the
# MODEL were wrong. Falling back to the in-repo build costs nothing when the
# binary is properly installed (PATH wins) and needs no root when it is not.
resolve_net_plumber() {
    command -v net_plumber >/dev/null 2>&1 && return 0
    [ -x "$ROOT/net_plumber/build/net_plumber" ] || return 0
    PATH="$ROOT/net_plumber/build:$PATH"
    export PATH
    NET_PLUMBER_FROM_BUILD_DIR=1
    return 0
}
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
    test/test_iptables_out_iface.py  # `-o` in a filter chain is refused (item 13); needs pybison
    test/test_apkeep_lib.py   # libapkeep + reachability (JPype + apkeep jar); skips if unavailable
    test/test_apkeep_acl.py   # APKeep ACL mechanic: src-seeded reachability through an ACLElement; skips if unavailable
    test/test_apkeep_adapter.py  # APKeepAdapter: FaVe model -> APKeep (P4); skips if unavailable
    test/test_apkeep_wl_ifi.py   # APKeepAdapter driven by the real wl_ifi models (P4); skips if unavailable
    test/test_backend_differential.py  # APKeep-vs-NetPlumber reachability differential (P5); skips if either backend unavailable
    test/test_apkeep_i2.py       # APKeep scale validation on wl_i2 (77k dst-IP routes, P5); skips if unavailable
    test/test_apkeep_stanford.py # APKeep on wl_stanford (in/mid/out HSA, out-stage collapse, P7); skips if unavailable
    test/test_apkeep_tum.py      # APKeep vs NP on wl_tum stateful firewall (Phase 1 characterization); skips if unavailable
    test/test_wl_ifi_stateless_gate.py  # wl_ifi's <--> policy variant end to end: zero violations; needs the JVM + generated stateless inputs
    test/test_apkeep_i2_admission.py  # wl_i2 faithful VLAN admission is per (ingress port, VLAN) and applies to transit hops; skips if unavailable
    test/test_apkeep_stanford_admission.py  # wl_stanford faithful VLAN admission is per (ingress port, VLAN) and gates the arrival edge; skips if unavailable
    # ad6 tests with a NATIVE dependency -- the ad6 bridge itself is pure Python
    # (a sys.executable subprocess), but these three reach past it:
    test/test_ad6_wl_up.py       # wl_up rulesets -> iptables/parser.py -> pybison
    test/test_ad6_wl_stanford.py # full 256-query differential vs a libnetplumber worker; opt-in (AD6_STANFORD_FULL_DIFFERENTIAL), so normally skips here
    test/test_ad6_wl_stanford_plain.py # N=2 differential vs a libnetplumber worker (bench.apkeep_convergence._emit_worker)
)
# Also integration-tier, but these must run in their OWN pytest process. JPype
# allows exactly one JVM per process and APKeep holds its network in Java static
# fields, so an APKeep test earlier in the same process leaves the shared heap
# too full for the NDD engine to build its diagrams -- co-running them dies with
# `java.lang.OutOfMemoryError: Java heap space` (default JVM heap is ~1/4 of RAM;
# ~4 GB on a 16 GB CI runner). A fresh JVM per engine is the robust split; raising
# FAVE_JVM_XMX only moves the wall. Both are gated by FAVE_REQUIRE_BACKENDS.
FAVE_NDD_TESTS=(
    test/test_apkeep_ndd_fwd.py  # NDD engine: IPv4 forwarding benchmarks (needs the NDD jar)
    test/test_apkeep_ndd_wlup.py # NDD engine: wl_up parity vs the frozen BDD baseline (needs jar + wl_up inputs)
    test/test_apkeep_compliance_cond.py # a check's `related:N` CONDITION is honoured (or refused), never dropped; needs jar + wl_up inputs
)
FAVE_E2E_TESTS=(           # need a live net_plumber backend + /dev/shm state
    test/test_rpc.py
    test/test_lib_equivalence.py  # libnetplumber vs net_plumber-RPC (skips if .so unbuilt)
)
# Everything excluded from the fast tier (pure-Python discovery ignores these).
FAVE_NATIVE_TESTS=( "${FAVE_INTEGRATION_TESTS[@]}" "${FAVE_NDD_TESTS[@]}" "${FAVE_E2E_TESTS[@]}" )

# When measuring coverage, pin the data file to an absolute path. `coverage run
# -p` runs from different CWDs (repo root for the policy_translator step, fave/
# for every fave step); without this the parallel data files land in different
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
    local rc=0 pt label
    pt="$(pytest_cmd)"
    # `all` runs this tier twice and labels the second pass, so the two are
    # told apart in a log; every other caller gets the plain name.
    label="${1:-fast}"

    echo "== $label: policy_translator =="
    ( cd "$ROOT" && PYTHONPATH=policy_translator $pt policy_translator/test ) || rc=1

    # Run from fave/, like the integration and e2e tiers: the benchmark-driven
    # tests locate their (gitignored, generated) inputs through a CWD-relative
    # `_PREFIX = "bench/<wl>"`, the convention every fave test uses. Running
    # this tier from $ROOT instead made that prefix unresolvable, so those tests
    # skipped themselves as "inputs not generated" in every tier -- a silent,
    # permanent skip, exactly the "a skip is NOT a pass" hazard
    # test/backend_gate.py exists to prevent.
    echo "== $label: fave (pure-Python units) =="
    local ignores=()
    local t
    for t in "${FAVE_NATIVE_TESTS[@]}"; do ignores+=("--ignore=$t"); done
    ( cd "$ROOT/fave" && PYTHONPATH=. $pt test "${ignores[@]}" ) || rc=1

    return $rc
}

run_smoke() {
    local rc=0
    echo "== smoke: example.sh =="
    ( cd "$ROOT/fave" && PYTHONPATH=. bash examples/example.sh ) || rc=1
    # TODO.md item 13a: an `-o` match in a filter chain is REFUSED by default,
    # because FaVe runs its filter chains before routing and the match would
    # silently constrain nothing. wl_example's pgf-ruleset uses one, so this
    # tier opts in explicitly; the run then prints one line per affected device
    # saying what is not being modelled. Scoped to the command that needs it,
    # NOT exported -- `./test.sh all` runs the integration tier in the same
    # shell, and test_iptables_out_iface.py asserts the default is refusal.
    # DELETE once routing precedes the filter chains (item 13a): the refusal
    # and this override go together.
    echo "== smoke: wl_example =="
    ( cd "$ROOT/fave" && PYTHONPATH=. FAVE_ALLOW_OUT_IFACE=1 \
        "$PYTHON" bench/wl_example/benchmark.py ) || rc=1
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

    # The NDD engine is a SECOND backend jar, built from its own pom -- apkeep_smoke.sh
    # builds only the APKeep jar. Without it `apkeep.lib_ndd.available()` is false and
    # both NDD tests would skip (or, under FAVE_REQUIRE_BACKENDS=1, fail the gate).
    # Kept as a script rather than an inline `mvn`: fave/test/ndd_build.sh pins
    # JAVA_HOME to java-11 exactly as apkeep_smoke.sh does (so both jars come from one
    # toolchain), guards mvn/java/pom up front with a readable message instead of a raw
    # Maven error, and asserts the jar actually appeared -- `mvn -q` can exit 0 having
    # produced nothing usable. Being separately invocable also matters when rebuilding
    # just this jar.
    echo "== integration: NDD engine jar (for test_apkeep_ndd_*) =="
    bash "$ROOT/fave/test/ndd_build.sh" || rc=1

    # Generate the wl_ifi benchmark inputs (gitignored artifacts) the APKeep
    # wl_ifi test consumes -- a clean checkout has none, and the integration tier
    # runs no live benchmark. Regenerated from tracked inputs (no backend).
    echo "== integration: generate wl_ifi inputs (for test_apkeep_wl_ifi) =="
    bash "$ROOT/fave/test/gen_wl_ifi_inputs.sh" || rc=1

    # Generate the wl_i2 inputs (HSA transfer functions -> FaVe model + oracle)
    # for the APKeep scale test; from tracked inputs, no live backend.
    echo "== integration: generate wl_i2 inputs (for test_apkeep_i2) =="
    bash "$ROOT/fave/test/gen_wl_i2_inputs.sh" || rc=1

    # Generate the wl_stanford inputs (in/mid/out HSA model + oracle) for the
    # APKeep out-stage-collapse test; from tracked inputs, no live backend.
    echo "== integration: generate wl_stanford inputs (for test_apkeep_stanford) =="
    bash "$ROOT/fave/test/gen_wl_stanford_inputs.sh" || rc=1

    # Generate the wl_tum inputs (fw.tum stateful firewall model) for the APKeep
    # wl_tum differential; from tracked sources (the ruleset + generators), no
    # live backend.
    echo "== integration: generate wl_tum inputs (for test_apkeep_tum) =="
    bash "$ROOT/fave/test/gen_wl_tum_inputs.sh" || rc=1

    # Generate the wl_up inputs -- the device-model JSON (topology/sources/routes/
    # policies) AND the per-host ip6tables rulesets -- from the tracked generators, no
    # live backend. TWO consumers in this tier now: test_ad6_wl_up.py (rulesets ->
    # iptables/parser.py -> pybison) and test_apkeep_ndd_wlup.py (model JSON, checked
    # against the tracked frozen BDD matrix, not reachable.json). Required, not
    # optional: under FAVE_REQUIRE_BACKENDS=1 a missing generated input is a hard
    # failure (test/backend_gate.py), not a skip.
    echo "== integration: generate wl_up inputs (for test_ad6_wl_up, test_apkeep_ndd_wlup) =="
    bash "$ROOT/fave/test/gen_wl_up_inputs.sh" || rc=1

    echo "== integration: fave bison-dependent tests (no backend) =="
    ( cd "$ROOT/fave" && PYTHONPATH=. $pt "${FAVE_INTEGRATION_TESTS[@]}" ) || rc=1

    # Separate process => fresh JVM for the NDD engine (see FAVE_NDD_TESTS).
    echo "== integration: NDD engine tests (own JVM) =="
    ( cd "$ROOT/fave" && PYTHONPATH=. $pt "${FAVE_NDD_TESTS[@]}" ) || rc=1

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
    local envs
    for wl in wl_up wl_tum wl_stanford wl_i2; do
        echo "== bench: $wl =="
        # TODO.md item 13a, as in run_smoke. wl_up's gateway firewall carries
        # one `-o` rule and wl_tum's tum-ruleset carries 3,286; wl_stanford and
        # wl_i2 have no rulesets at all, so they are left strict rather than
        # opted in wholesale. Passed via `env` because an assignment that comes
        # from an expansion is NOT recognised as an assignment prefix.
        envs=()
        case "$wl" in
            wl_up|wl_tum) envs=(FAVE_ALLOW_OUT_IFACE=1) ;;
        esac
        ( cd "$ROOT/fave" && PYTHONPATH=. env "${envs[@]}" \
            "$PYTHON" "bench/$wl/benchmark.py" ) || rc=1
    done
    return $rc
}

# ---- doctor -----------------------------------------------------------------

# Which tier each apt package blocks. The Dockerfile is the single source of
# truth for WHAT is needed (this parses it, rather than duplicating the list
# and letting the two drift); this table only adds WHY. A Dockerfile package
# missing from every bucket below is reported as unclassified rather than
# silently ignored, so the table cannot quietly fall behind.
apt_purpose() {
    case "$1" in
        bison|flex|m4|python3-dev|build-essential)
            echo "integration (pybison native build + runtime parser compile)" ;;
        libcppunit-1.15-0|libcppunit-dev)
            echo "integration (NetPlumber C++ unit suites)" ;;
        liblog4cxx15|liblog4cxx-dev|pybind11-dev)
            echo "integration/e2e (libnetplumber pybind11 module)" ;;
        openjdk-11-jdk-headless|maven)
            echo "integration (APKeep backend: JVM + build)" ;;
        minisat|clasp)
            echo "ad6 (make test: solver adapters shell out to these binaries)" ;;
        cadical|cryptominisat)
            echo "ad6_encoding_bench Axis 0/1 (modern-CDCL comparison + Tseitin equisatisfiability self-check)" ;;
        pandoc|texlive-latex-base|texlive-latex-recommended|texlive-fonts-recommended|lmodern|inkscape)
            echo "bench (report.md -> report.pdf conversion)" ;;
        pylint)
            echo "lint gate (fave/test/lint_test.sh)" ;;
        python3-coverage)
            echo "COVERAGE=1 runs" ;;
        python3-daemon)
            echo "e2e (aggregator_service daemonisation)" ;;
        apt-utils|wget|git|python3|python3-pip|python3-venv)
            echo "base tooling" ;;
        *)  echo "UNCLASSIFIED -- declared in Dockerfile, purpose not recorded in apt_purpose()" ;;
    esac
}

# Declared in the Dockerfile, but blocking NO ./test.sh tier -- reported as [warn]
# and excluded from the verdict, so an absent one cannot fail a doctor run.
#
# The distinction is real and worth keeping: a doctor that fails on a dependency
# nothing in the suite needs trains people to ignore its verdict, which is exactly
# how a REAL missing dependency gets read as a code bug (the failure mode this whole
# tier exists to prevent -- see the notes below run_doctor). But leaving such a
# dependency UNDECLARED is how cadical/cryptominisat went missing after a container
# reset with the doctor having no opinion at all, and ad6_encoding_bench's Axis 0 was
# silently unrunnable (AD6_ENCODING_PLAN.md §3.1a). Declared-but-advisory is the
# position that catches it without crying wolf.
apt_advisory() {
    case "$1" in
        cadical|cryptominisat) return 0 ;;
        *) return 1 ;;
    esac
}

# A python import check that CANNOT take the doctor down with it: pybison in
# particular segfaults rather than raising (see run_doctor's notes), so every
# probe runs in its own subshell/interpreter and only its exit status is read.
check_import() {
    local label="$1" module="$2" pypath="${3:-}" note="${4:-}"
    if ( cd "$ROOT" && PYTHONPATH="$pypath" "$PYTHON" -c "import $module" ) >/dev/null 2>&1; then
        printf '  [ok]      %-22s\n' "$label"
    else
        printf '  [MISSING] %-22s %s\n' "$label" "$note"
        return 1
    fi
}

# The pip-side counterpart of apt_advisory(): declared in the Dockerfile, needed by
# no ./test.sh tier, so its absence is a [warn] and never the verdict. Same reasoning
# as apt_advisory() -- see the comment there. Appends the pip spec to $advisory_pip
# (caller's scope) so the verdict can print one repair line for all of them.
check_import_advisory() {
    local label="$1" module="$2" spec="$3" note="${4:-}"
    if ( cd "$ROOT" && "$PYTHON" -c "import $module" ) >/dev/null 2>&1; then
        printf '  [ok]      %-22s\n' "$label"
    else
        printf '  [warn]    %-22s %s\n' "$label" "$note"
        advisory_pip+=("$spec")
    fi
}

run_doctor() {
    local rc=0 missing_apt=() advisory_apt=() advisory_pip=() pkg status

    echo "== env doctor: interpreter =="
    printf '  %s\n' "$("$PYTHON" -c 'import sys; print(sys.executable)' 2>/dev/null || echo "$PYTHON NOT RUNNABLE")"
    printf '  %s\n' "$("$PYTHON" --version 2>&1)"
    # Say it explicitly: the packages probed below are probed against THIS
    # interpreter, and this is also the one every child script now gets. Before
    # the export those two were different things, and the doctor was reporting
    # on an interpreter the smoke tier never ran.
    echo "  [exported] child scripts (example.sh, start_aggr.sh, the gen_wl_*"
    echo "            generators, typecheck_test.sh) inherit PYTHON and use this"
    echo "            same interpreter; the package checks below probe it."
    if [ -n "$PYTHON_RESOLVED" ]; then
        echo "  [auto]    no VIRTUAL_ENV set; resolved this interpreter by probing for the"
        echo "            project's deps (resolve_python). Note the venv may live OUTSIDE"
        echo "            the checkout -- fave/setup.sh creates ~/.venv, which in a"
        echo "            container resolves via \$HOME and not under the project mount."
    elif [ -z "${VIRTUAL_ENV:-}" ] && [ -z "$PYTHON_FROM_ENV" ]; then
        echo "  [warn]    no VIRTUAL_ENV set and no venv found at ./.venv or ~/.venv --"
        echo "            missing imports below may just mean the deps live in an"
        echo "            interpreter this script could not find. Set \$PYTHON to it."
    fi

    echo "== env doctor: python packages =="
    check_import "pytest"      pytest                      "" "-> pip install -r requirements.txt   [every tier]" || rc=1
    check_import "coverage"    coverage                     "" "-> pip install -r requirements.txt   [COVERAGE=1]" || rc=1
    check_import "mypy"        mypy                         "" "-> pip install -r requirements.txt   [typecheck gate]" || rc=1
    check_import "lxml"        lxml.etree                   "" "-> pip install lxml                  [ad6]" || rc=1
    check_import "pycosat"     pycosat                      "" "-> pip install pycosat               [ad6]" || rc=1
    check_import "python-sat"  pysat.solvers                "" "-> pip install python-sat            [ad6 incremental]" || rc=1
    check_import "pybison"     bison                        "" "-> see Dockerfile: pip install --no-binary :all: pybison==0.6.4  [integration]" || rc=1
    check_import "JPype1"      jpype                        "" "-> pip install JPype1                [APKeep backend]" || rc=1
    check_import "libnetplumber" libnetplumber net_plumber/python \
        "-> build_libnetplumber.sh, OR (more often) a missing liblog4cxx -- see below  [integration/e2e]" || rc=1
    check_import_advisory "z3-solver" z3 "z3-solver==5.1.0.0" \
        "ad6_encoding_bench Axes 2-7 (Z3 comparison engine) -- ADVISORY, blocks no tier"

    echo "== env doctor: apt packages declared in Dockerfile =="
    while read -r pkg; do
        [ -n "$pkg" ] || continue
        status="$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null)"
        case "$status" in
            *"install ok installed"*) printf '  [ok]      %-30s\n' "$pkg" ;;
            *) if apt_advisory "$pkg"; then
                   printf '  [warn]    %-30s %s\n' "$pkg" \
                       "$(apt_purpose "$pkg") -- ADVISORY, blocks no tier"
                   advisory_apt+=("$pkg")
               else
                   printf '  [MISSING] %-30s %s\n' "$pkg" "$(apt_purpose "$pkg")"
                   missing_apt+=("$pkg"); rc=1
               fi ;;
        esac
    done < <(grep -oP 'apt-get \$APT_CONFS install \K[a-z0-9.+-]+' "$ROOT/Dockerfile" | sort -u)

    echo "== env doctor: native artifacts =="
    # Check RESOLVABILITY, not just existence. Checking only the build artifact
    # reported [ok] -- and "environment complete for every tier" -- while the
    # smoke tier could not start NetPlumber at all, because start_np.sh invokes
    # a bare `net_plumber` and nothing had put it on PATH. A doctor that
    # validates something other than what the scripts use is worse than no
    # doctor: it actively certifies a broken environment.
    if command -v net_plumber >/dev/null 2>&1; then
        if [ -n "${NET_PLUMBER_FROM_BUILD_DIR:-}" ]; then
            printf '  [ok]      %-30s %s\n' "net_plumber binary" \
                "(from net_plumber/build; not installed on PATH)"
        else
            printf '  [ok]      %-30s\n' "net_plumber binary"
        fi
    else
        # No "built but unreachable" branch: resolve_net_plumber has already
        # prepended the build directory, so reaching here means the binary is
        # genuinely absent (or not executable), not merely uninstalled.
        printf '  [MISSING] %-30s %s\n' "net_plumber binary" \
            "-> make -C net_plumber/build all && make -C net_plumber/build install   [smoke/integration/e2e/bench]"
        rc=1
    fi
    if compgen -G "$ROOT/net_plumber/python/libnetplumber*.so" >/dev/null; then
        printf '  [ok]      %-30s\n' "libnetplumber .so built"
    else
        printf '  [MISSING] %-30s %s\n' "libnetplumber .so built" \
            "-> bash net_plumber/python/build_libnetplumber.sh"
        rc=1
    fi

    echo "== env doctor: runtime limits (advisory, never fatal) =="
    local shm mem
    shm="$(df -h --output=size /dev/shm 2>/dev/null | tail -1 | tr -d ' ')"
    mem="$("$PYTHON" -c "print(open('/proc/meminfo').readline().split()[1])" 2>/dev/null)"
    printf '  /dev/shm  %s' "${shm:-unknown}"
    case "${shm:-}" in
        *G) echo "" ;;
        *)  echo "   [warn] FaVe writes aggregator.log/rpc.log into /dev/shm/np and the"
            echo "            bench workloads overflow a small one -- redirect logs to disk"
            echo "            for anything at bench scale" ;;
    esac
    [ -n "${mem:-}" ] && printf '  memory    %s MB total\n' "$((mem / 1024))"
    printf '  cores     %s\n' "$(nproc 2>/dev/null || echo unknown)"

    echo "== env doctor: verdict =="
    if [ "${#missing_apt[@]}" -gt 0 ]; then
        echo "  REPAIR (apt-get update FIRST -- without it a fresh container reports"
        echo "  'Unable to locate package' for packages that are perfectly available):"
        echo ""
        echo "    sudo apt-get update && sudo apt-get install -y ${missing_apt[*]}"
        echo ""
    fi
    local n_advisory=$(( ${#advisory_apt[@]} + ${#advisory_pip[@]} ))
    if [ "$n_advisory" -gt 0 ]; then
        echo "  OPTIONAL (nothing in ./test.sh needs these; ad6_encoding_bench does):"
        echo ""
        [ "${#advisory_apt[@]}" -gt 0 ] && \
            echo "    sudo apt-get update && sudo apt-get install -y ${advisory_apt[*]}"
        [ "${#advisory_pip[@]}" -gt 0 ] && \
            echo "    $PYTHON -m pip install ${advisory_pip[*]}"
        echo ""
    fi
    if [ "$rc" -eq 0 ]; then
        if [ "$n_advisory" -gt 0 ]; then
            local noun="dependencies"
            [ "$n_advisory" -eq 1 ] && noun="dependency"
            echo "  environment complete for every tier ($n_advisory advisory $noun absent, see [warn] above)"
        else
            echo "  environment complete for every tier"
        fi
    else
        echo "  see the [MISSING] lines above; each names the tier it blocks."
        echo "  Nothing above is a code defect -- these are container-state gaps."
    fi
    return $rc
}

# WHY THIS TIER EXISTS, and why the failures it catches are worth naming:
# every one of these has cost a session real time by surfacing as something
# that looks like a different problem entirely.
#   * python3-dev missing  -> pybison compiles its generated parser at RUNTIME,
#     that compile fails on a missing Python.h, and pybison then SEGFAULTS,
#     taking the whole pytest process down (no traceback, no failing test --
#     `test_ad6_wl_up.py` just dumps core). Diagnosed the hard way twice.
#   * liblog4cxx15 missing -> `libnetplumber` fails to LOAD, and the harness
#     reports "libnetplumber is not built; run build_libnetplumber.sh" even
#     though the .so is present and correct. The message points at the wrong
#     fix; every live-NetPlumber differential test silently skips.
#   * minisat/clasp missing -> `ad6 make test` reports 4 red suites with
#     FileNotFoundError, which reads like a code regression, not a container
#     one. `which minisat` printing nothing is easy to misread as success --
#     check the exit status.
#   * apt-get update not run first -> `apt-get install minisat` fails with
#     "Unable to locate package minisat" on a container whose package lists
#     were never populated, which reads like the package does not exist.
# The Dockerfile installs all of this; a sandbox NOT built from the Dockerfile
# (e.g. a yolobox with its own base image) starts without any of it, while a
# venv living in a persistent $HOME survives -- which is why the pip side of
# the environment usually looks fine while the apt side is missing wholesale.

# ---- dispatch ---------------------------------------------------------------

tier="${1:-}"
rc=0
resolve_python
resolve_net_plumber
case "$tier" in
    fast)        run_fast || rc=1 ;;
    smoke)       run_smoke || rc=1 ;;
    integration) run_integration || rc=1 ;;
    e2e)         run_e2e || rc=1 ;;
    bench)       run_bench || rc=1 ;;
    all)
        run_fast || rc=1
        run_integration || rc=1
        run_e2e || rc=1
        # The integration and smoke tiers REGENERATE the gitignored benchmark
        # artifacts that fast-tier tests assert on, and they do it after fast
        # has run -- so a green `all` could be validating STALE artifacts. That
        # is not hypothetical: the wl_ifi self-check regression (commit
        # 7706daae) passed `all` and failed the very next `fast`, because smoke
        # rewrote wl_ifi's checks.json once the tests reading it were done.
        # Running fast again at the end closes the window, at ~23 s.
        run_fast "fast (re-run, against regenerated artifacts)" || rc=1
        ;;
    doctor)      run_doctor || rc=1 ;;
    *)
        echo "usage: $0 {fast|smoke|integration|e2e|bench|all|doctor}" >&2
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
