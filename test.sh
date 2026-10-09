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
#   FAVE_SKIP_AD6  If set to 1, every ad6 test module (fave/test/test_ad6_*.py)
#              is left out of every tier -- the pure-Python units in `fast`
#              (~180 tests, about half its runtime) and the solver-backed
#              differentials in `integration` (several minutes). For routine
#              runs: the owner's standing direction is to use ad6 as an ARBITER,
#              when NetPlumber and NDD-APKeep disagree, not as a third
#              confirmation of an agreement. Measurement-affecting, so the
#              RESULT line says so; never set it in CI's gating jobs. Tests
#              that merely construct an Ad6Adapter or call ad6's translator
#              without solving (test_aggregator_backend, test_table_semantics,
#              test_reporter_engine_results) are not ad6 tests and still run.

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
FAVE_SKIP_AD6="${FAVE_SKIP_AD6:-0}"

# `without_ad6 <files...>` prints its arguments minus fave/test/test_ad6_*.py
# when FAVE_SKIP_AD6=1, and all of them otherwise. Applied at each call site
# rather than to the lists themselves: the fast tier IGNORES everything in
# those lists, so filtering the lists would move the costly ad6 differentials
# INTO `fast` -- the opposite of skipping them.
without_ad6() {
    local t
    for t in "$@"; do
        if [ "$FAVE_SKIP_AD6" = "1" ]; then
            case "$t" in test/test_ad6_*.py) continue ;; esac
        fi
        printf '%s\n' "$t"
    done
}

# Say it where the tier's output is read, so a partial run is never mistaken
# for a whole one.
note_ad6_skip() {
    [ "$FAVE_SKIP_AD6" = "1" ] && echo "   (FAVE_SKIP_AD6=1: $1)"
    return 0
}

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
    test/test_ndd_vlan_slot.py  # a `+ filter` rule's VLAN slot means the same to BOTH engines (TABLE_SEMANTICS_PLAN.md §8); skips if either is unavailable
    test/test_table_semantics.py  # declared table semantics reach the ENGINE, not just the JSON (TABLE_SEMANTICS_PLAN.md S1+S2)
    test/test_apkeep_adapter.py  # APKeepAdapter: FaVe model -> APKeep (P4); skips if unavailable
    test/test_apkeep_update_refused.py  # a model change after the one-time build is refused, not dropped (TODO item 31); skips if unavailable
    test/test_apkeep_wl_ifi.py   # APKeepAdapter driven by the real wl_ifi models (P4); skips if unavailable
    test/test_apkeep_i2.py       # APKeep scale validation on wl_i2 (77k dst-IP routes, P5); skips if unavailable
    test/test_apkeep_stanford.py # APKeep on wl_stanford (in/mid/out HSA, out-stage collapse, P7); skips if unavailable
    test/test_wl_ifi_stateless_gate.py  # wl_ifi's <--> policy variant end to end: zero violations; needs the JVM + generated stateless inputs
    test/test_apkeep_i2_admission.py  # wl_i2 faithful VLAN admission is per (ingress port, VLAN) and applies to transit hops; skips if unavailable
    test/test_apkeep_stanford_admission.py  # wl_stanford faithful VLAN admission is per (ingress port, VLAN) and gates the arrival edge; skips if unavailable
    # MOVED here from the fast tier 2026-10-01 (TODO item 34). All three build an
    # APKeepAdapter, whose __init__ constructs a LibNDD and so needs JPype1 + a
    # built NDD jar -- neither of which the fast tier's `pip install -r
    # requirements.txt` can provide, and a JVM is not something pip supplies at
    # all. They did not SKIP without it: APKeepAdapter raises from __init__, so on
    # a clean runner this was 39 errors/failures, measured. The per-class
    # require_or_skip guards in two of them sit below that constructor and never
    # got the chance to fire.
    test/test_apkeep_out_stage.py      # the out-stage becomes APKeep elements (P7c); needs JPype + both jars
    test/test_apkeep_ingress_contract.py  # a table is checked against the ingress ports its rules name; needs JPype + both jars
    test/test_apkeep_tcp_flags.py      # tcp_flags survives the `+ filter` slot layout in BOTH engines; needs JPype + both jars
    # ad6 tests with a NATIVE dependency -- the ad6 bridge itself is pure Python
    # (a sys.executable subprocess), but these reach past it:
    test/test_ad6_wl_stanford.py # full-model structural translation (48 tables, ~1s, ALWAYS runs) + the 256-query differential vs a libnetplumber worker, which is opt-in (AD6_STANFORD_FULL_DIFFERENTIAL) and normally skips
    test/test_ad6_wl_stanford_plain.py # N=2 differential vs a libnetplumber worker (bench.apkeep_convergence._emit_worker)
    # MOVED here from the fast tier 2026-10-01 (TODO item 42). All three need
    # bench/wl_ifi/'s GENERATED model, which only this tier produces
    # (gen_wl_ifi_inputs.sh, above) -- so in `fast` they were twelve tests that
    # skipped on every clean checkout, and since no list named them they ran in
    # NO CI job at all. Measured: `./test.sh fast` in a pristine git-archive
    # export gives 808 passed / 15 skipped against the working tree's 823 / 0,
    # and twelve of those fifteen are these. Tier membership follows the
    # DEPENDENCY FOOTPRINT (see the header), and a generated workload is one --
    # the same argument item 34 used for the three APKeep modules above.
    # Sharper here than for the other three: these gate with require_or_skip, so
    # under FAVE_REQUIRE_BACKENDS=1 they are hard failures rather than skips --
    # and that flag is set by the integration job, which did not run them.
    test/test_ad6_wl_ifi.py          # ad6 vs the wl_ifi model (3)
    test/test_ad6_wl_ifi_stateful.py # the stateful wl_ifi variant (5)
    test/test_ad6_grounding.py       # the grounding constraint on wl_ifi (4)
    test/test_ad6_cloud_differential.py # ad6 vs libnetplumber on wl_cloud, anchored to the dataset's own verdicts (~2 min)
    test/test_apkeep_first_match.py  # a forwarding table decides its APKeep element by its RULES, not by the device name; skips if unavailable
    test/test_apkeep_nat_rewrite.py  # a NAT's rewrite outputs stay atomic predicates across rules applied to OTHER elements (TODO item 29); skips if unavailable
    test/test_apkeep_cloud_differential.py # APKeep vs libnetplumber on wl_cloud, one engine per process, anchored to the dataset
    test/test_ad6_port_pair.py   # a rule matching BOTH transport ports means AND, not OR -- and same-direction ports still alternate (CLOUD_BENCH_PLAN.md 1.7.4)
    # MOVED here from the fast tier 2026-10-01 (TODO item 34). 143 of its tests are
    # pure Python and would be welcome in `fast`, but ten of them reach
    # src/solver/pycosat.py, and pycosat ships NO wheel -- it compiles against
    # Python.h at install time. Tier membership follows the DEPENDENCY FOOTPRINT
    # (see the header), and this file's footprint includes a C extension built
    # from source, so the whole file moves. Splitting the ten solver-backed tests
    # out would return the other 143 to the inner loop and is the better end
    # state; it is a 1,200-line file and was not attempted here.
    test/test_ad6_translate.py   # model -> ad6 config/CNF translation; the reachability cases solve with pycosat
    # Integration rather than fast, although its first half is pure Python: the
    # second half asserts that every REGISTERED Delta-net workload carries a
    # SOURCE.json, and the inputs only exist after this tier generates them. In
    # the fast tier that half would skip in every run, and a permanent skip is
    # the failure mode the test itself is about.
    test/test_deltanet_stamp.py  # SOURCE.json: a generated workload records which trace produced it (D6)
    # Pure Python, and here purely on COST (owner, 2026-09-25). It builds a
    # 39,500-rule model per trace and walks packets through it; moving its six
    # tests off the fast tier took that tier from 105s to 74s and cost this one
    # 19s. It needs no backend and no generated input, so this is NOT a
    # dependency -- and the file's own docstring says so, because a reader who
    # assumes one would hesitate to run it by hand.
    test/test_deltanet_lpm.py    # LPM is load-bearing on BOTH traces, and the matrix cannot see it (3's standing rule)
    # Needs the generated reachable.json. wl_berkeley's matrix is stated FROM
    # this walk (CLOUD_BENCH_PLAN.md 2.15), so it is validated where the answer
    # is known independently: airtel, cell for cell.
    test/test_deltanet_fib_walk.py # the reference FIB walk reproduces airtel's homing-derived matrix, and is LPM-blind there
    test/test_veriflow_airtel.py # VeriFlow-FR V1 gates: airtel matrices == oracle == NetPlumber, and an LPM guard that can fail (~50s)
    test/test_veriflow_adapter.py # VeriFlow-FR V4: its measurement-affecting choices reach the run's log
    test/test_veriflow_census.py # VeriFlow-FR V2: EC counts reproduce APKeep's Table 3 (Airtel 2,799; Stanford* 2,283); multi-field products pinned (~45s)
    # Folded in from the former FAVE_OUT_IFACE_TESTS group when TODO.md
    # item 13a was closed: these parse rulesets that use `-o`, which no
    # longer needs an opt-in because it is no longer refused.
    test/test_ad6_wl_up.py       # wl_up's gateway firewall carries one `-o` rule
    test/test_apkeep_tum.py      # wl_tum's tum-ruleset carries 3,286 of them
    test/test_backend_differential.py  # APKeep-vs-NetPlumber reachability differential (P5); skips if either backend unavailable
    test/test_veriflow_differential.py # VeriFlow-FR V3 vs NetPlumber on the rewriting workloads; wl_tum a measured did-not-finish; wl_i2 opt-in (VERIFLOW_FULL_DIFFERENTIAL=1)
)
# Also integration-tier, but these must run in their OWN pytest process. JPype
# allows exactly one JVM per process and APKeep holds its network in Java static
# fields, so an APKeep test earlier in the same process leaves the shared heap
# too full for the NDD engine to build its diagrams -- co-running them dies with
# `java.lang.OutOfMemoryError: Java heap space` (default JVM heap is ~1/4 of RAM;
# ~4 GB on a 16 GB CI runner). A fresh JVM per engine is the robust split; raising
# FAVE_JVM_XMX only moves the wall. Both are gated by FAVE_REQUIRE_BACKENDS.
FAVE_NDD_TESTS=(
    test/test_apkeep_ndd_fwd.py  # NDD engine: IPv4 forwarding benchmarks (needs the NDD jar); wl_tum
    test/test_apkeep_ndd_wlup.py # NDD engine: wl_up parity vs the frozen BDD baseline (needs jar + wl_up inputs)
    test/test_apkeep_compliance_cond.py # a check's `related:N` CONDITION is honoured (or refused), never dropped; needs jar + wl_up inputs
    test/test_revisit_router_on_a_stick.py # Q4 / TODO item 33: a packet passing one table twice -- VeriFlow-FR(state) and ad6 right; NetPlumber and APKeep defects pinned (starts NDD too)
)
FAVE_E2E_TESTS=(           # need a live net_plumber backend + /dev/shm state
    test/test_rpc.py
    test/test_lib_equivalence.py  # libnetplumber vs net_plumber-RPC (skips if .so unbuilt)
)
# Everything excluded from the fast tier (pure-Python discovery ignores these).
FAVE_NATIVE_TESTS=( "${FAVE_INTEGRATION_TESTS[@]}" \
                    "${FAVE_NDD_TESTS[@]}" "${FAVE_E2E_TESTS[@]}" )

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
    if [ "$FAVE_SKIP_AD6" = "1" ]; then
        ignores+=("--ignore-glob=test/test_ad6_*.py")
        note_ad6_skip "the ad6 unit modules are ignored"
    fi
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
    ( cd "$ROOT/fave" && PYTHONPATH=. \
        "$PYTHON" bench/wl_example/benchmark.py ) || rc=1
    echo "== smoke: wl_ifi =="
    ( cd "$ROOT/fave" && PYTHONPATH=. "$PYTHON" bench/wl_ifi/benchmark.py ) || rc=1
    # VeriFlow-FR's production path (VERIFLOW_PLAN.md V4): the same benchmark
    # with only FAVE_BACKEND changed must report the same violations, line for
    # line. Skipped, loudly, when libveriflow_fr is not built.
    echo "== smoke: wl_ifi on veriflow, against the netplumber report =="
    if compgen -G "$ROOT/veriflow_fr/python/libveriflow_fr*.so" >/dev/null; then
        local np_report vf_report
        np_report="$(mktemp)"; vf_report="$(mktemp)"
        grep '^- `' "$ROOT/fave/report.md" | sort > "$np_report" || true
        ( cd "$ROOT/fave" && PYTHONPATH=. FAVE_BACKEND=veriflow "$PYTHON" bench/wl_ifi/benchmark.py ) || rc=1
        grep '^- `' "$ROOT/fave/report.md" | sort > "$vf_report" || true
        if [ -s "$np_report" ] && diff -q "$np_report" "$vf_report" >/dev/null; then
            echo "  veriflow == netplumber: $(wc -l < "$vf_report") violation line(s)"
        else
            echo "  veriflow's report differs from netplumber's:"; diff "$np_report" "$vf_report" | head -20
            rc=1
        fi
        rm -f "$np_report" "$vf_report"
    else
        echo "  SKIPPED: libveriflow_fr is not built (veriflow_fr/python/build_libveriflow_fr.sh)"
    fi
    return $rc
}

run_integration() {
    local rc=0 pt
    pt="$(pytest_cmd)"

    echo "== integration: NetPlumber C++ unit tests =="
    make -j -C "$ROOT/net_plumber/build" test || rc=1

    # VeriFlow-FR (VERIFLOW_PLAN.md): its own C++ suite -- the literature's
    # examples L1-L6/L10 and the concrete-packet oracle -- and the in-process
    # binding test_veriflow_airtel.py drives. Both build in seconds, so they are
    # built here rather than required up front.
    echo "== integration: VeriFlow-FR C++ unit tests + libveriflow_fr =="
    make -j -C "$ROOT/veriflow_fr" test || rc=1
    PYTHON="$PYTHON" bash "$ROOT/veriflow_fr/python/build_libveriflow_fr.sh" || rc=1

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

    # Generate the wl_cloud inputs. The sixth and last of the gen_wl_*_inputs.sh
    # generators to be wired in: until 2026-10-01 it ran in no tier, which is
    # what let TODO item 36 (the two differentials' self-pre-empting gate) go
    # unnoticed for as long as it did.
    #
    # It is NOT what makes those differentials run -- each regenerates in its own
    # setUpClass, because bench/wl_cloud/*.json is shared by the oracle and
    # matrix phases and whichever ran last wins. It is here for the two things
    # that regeneration cannot do:
    #   * the raw scenario's INTEGRITY check (sha256sum -c against cloud-tf/
    #     SHA256SUMS) becomes a named tier step, so an edited dataset fails where
    #     a reader can see it, instead of inside a differential's setUpClass as a
    #     truncated "could not regenerate the wl_cloud inputs";
    #   * it still runs when both differentials do not -- FAVE_SKIP_AD6=1, or no
    #     JVM -- so wl_cloud is never the one workload the tier stopped checking.
    echo "== integration: generate wl_cloud inputs (raw-scenario integrity + both cloud differentials) =="
    bash "$ROOT/fave/test/gen_wl_cloud_inputs.sh" || rc=1

    # Every Delta-net workload's directory is derived from the vendored traces,
    # so a clean checkout has none of it and the backend differential would skip
    # the workload that exposed APKeep's ingress gap in the first place
    # (CLOUD_BENCH_PLAN.md §2.6). No live backend: the model, the FPL and
    # reachable.json all come out of bench/deltanet/traces/. No workload is
    # named here -- the script loops over bench/deltanet/registry.py, so a newly
    # registered workload is generated without this line being touched (D6).
    echo "== integration: generate Delta-net workload inputs (for test_backend_differential) =="
    bash "$ROOT/fave/test/gen_deltanet_inputs.sh" || rc=1

    local group
    echo "== integration: fave bison-dependent tests (no backend) =="
    mapfile -t group < <(without_ad6 "${FAVE_INTEGRATION_TESTS[@]}")
    note_ad6_skip "$(( ${#FAVE_INTEGRATION_TESTS[@]} - ${#group[@]} )) ad6 module(s) left out"
    # Never hand pytest an EMPTY list: with no paths it discovers everything.
    [ "${#group[@]}" -gt 0 ] && { ( cd "$ROOT/fave" && PYTHONPATH=. $pt "${group[@]}" ) || rc=1; }

    # Own process so the opt-in is SCOPED: test_iptables_out_iface.py, in the
    # group above, asserts that `-o` is refused by default (see

    # Separate process => fresh JVM for the NDD engine (see FAVE_NDD_TESTS),
    # which also needs the item 13a opt-in -- all three replay wl_up or wl_tum.
    echo "== integration: NDD engine tests (own JVM) =="
    ( cd "$ROOT/fave" && PYTHONPATH=. \
        $pt "${FAVE_NDD_TESTS[@]}" ) || rc=1

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
    for wl in wl_up wl_tum wl_stanford wl_i2 wl_airtel1; do
        echo "== bench: $wl =="
        # TODO.md item 13a, as in run_smoke. wl_up's gateway firewall carries
        # one `-o` rule and wl_tum's tum-ruleset carries 3,286; wl_stanford and
        # wl_i2 have no rulesets at all, so they are left strict rather than
        # opted in wholesale. Passed via `env` because an assignment that comes
        # from an expansion is NOT recognised as an assignment prefix.
        envs=()
        case "$wl" in
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

# ONE freshness check, for every build artifact this tree produces (TODO item 41).
#
# The comment below was written for the two Java jars and said they were "the
# same class of artifact as the .so above" -- and then the .so above, and the
# net_plumber binary, and libveriflow_fr, went on being checked with a bare
# `compgen -G`. The reasoning was written down and applied to one of the halves.
#
# What existence alone misses, MEASURED 2026-10-01:
# `net_plumber/python/libnetplumber.so` was built at 08:21; `23265ec2` had added
# `loop_reports` to `libnetplumber.cpp` the day before. The doctor printed
# `[ok] libnetplumber .so built` and the verdict "environment complete for every
# tier", while `FAVE_REQUIRE_BACKENDS=1 ./test.sh integration` died in
# `test_revisit_router_on_a_stick.py` with `AttributeError: ... has no attribute
# 'loop_reports'`. Rebuilding the .so -> 6 passed, no code change. That one was
# loud because the method was simply absent; a stale .so whose signatures still
# matched would have answered, wrongly.
#
# The NetPlumber artifacts are MORE exposed than the jars, not less. The
# integration tier builds the APKeep jar, the NDD jar and libveriflow_fr, so a
# stale one of those is repaired by running the tier. NOTHING a developer
# routinely runs builds `net_plumber` or `libnetplumber` -- only the CI composite
# does, once per job, on a runner with no previous build.
#
# Java build artifacts. apkeep/ and ndd/ are Maven subtrees whose target/ is
# gitignored, so the three states below are genuinely different and only one of
# them is worth failing on:
#
#   absent  the normal state of a clean checkout or a reset container. The
#           integration tier BUILDS both jars (apkeep_smoke.sh, ndd_build.sh)
#           and the jar-backed tests skip until it has, so this is a [warn] and
#           never the verdict -- unlike the NetPlumber artifacts above, which no
#           tier builds and whose absence therefore blocks one.
#   stale   a jar older than its own sources. It still LOADS, so every jar-backed
#           test runs, against an engine that predates the source change. This
#           state is the reason this check exists.
#   fresh   [ok].
#
# Why stale is fatal: the two test_apkeep_tcp_flags cases failed exactly this way
# against jars built before `tcp_flags` became slot 19 of the `+ filter` layout,
# and they read as an engine computing a WRONG ANSWER rather than as an unbuilt
# artifact -- while this doctor reported "environment complete for every tier",
# because its apt and pip halves were complete and this section checked only the
# two NetPlumber artifacts. The differential class in that same file
# (TestBothEnginesAgree) kept PASSING throughout, since both engines agreed on a
# field neither jar had: agreement is not correctness when the agreement is on
# nothing, and a green differential beside two red per-engine classes is not a
# signature anyone reads as "rebuild the jar".
#
# The paths are the CONSUMERS' own -- lib_apkeep.py and lib_ndd.py hardcode these
# two -- on the rule stated for net_plumber above: check what the scripts use,
# never something merely equivalent to it.
# The staleness half, on its own, because one artifact cannot use the other half:
# `net_plumber` is checked for RESOLVABILITY rather than for existence at a path
# (see the comment at its call site), and still wants its mtime compared.
#
#   $1 label   as printed
#   $2 file    the artifact, a real path -- the CONSUMER's own, never something
#              merely equivalent to it
#   $3 srcs    space-separated files/dirs to compare against (word-split)
#   $4 pats    space-separated find(1) -name patterns selecting the sources
#   $5 note    trailing text for the [STALE] line (the repair, and who it bites)
#   $6 ok      optional trailing text for the [ok] line
check_freshness() {
    local label="$1" file="$2" srcs="$3" pats="$4" note="$5" ok="${6:-}"
    local newer pat
    local -a expr=()
    for pat in $pats; do
        if [ "${#expr[@]}" -eq 0 ]; then expr=( -name "$pat" ); else expr+=( -o -name "$pat" ); fi
    done
    # mtime, which is what a rebuild moves. A build FILE counts as a source: a
    # pom's dependency or compiler-target change makes a jar stale exactly as an
    # edit to a .java does, and the same holds for a Makefile.
    newer="$(find $srcs \( "${expr[@]}" \) -newer "$file" -print -quit 2>/dev/null)"
    if [ -n "$newer" ]; then
        printf '  [STALE]   %-30s %s\n' "$label" \
            "older than ${newer#"$ROOT"/}${note:+   $note}"
        return 1
    fi
    if [ -n "$ok" ]; then
        printf '  [ok]      %-30s %s\n' "$label" "$ok"
    else
        printf '  [ok]      %-30s\n' "$label"
    fi
}

# Existence policy + freshness, for the four artifacts that live at a known path.
#
#   $3 absent  "fatal" when NO tier builds it (its absence blocks one), "warn"
#              when the integration tier does (the tests skip until it has).
#              The three labels now mean the same thing for every artifact:
#              before this, [MISSING] was fatal for two and advisory for
#              libveriflow_fr, which printed it and set no rc.
#   $4 repair  the command that produces it, named in every message
#   $7 note    extra trailing text for [STALE] only -- it says who the stale
#              artifact bites, which is not the same audience as "not built".
check_artifact() {
    local label="$1" glob="$2" absent="$3" repair="$4" srcs="$5" pats="$6" note="${7:-}"
    local found
    found="$(compgen -G "$glob" 2>/dev/null | head -1)"
    if [ -z "$found" ]; then
        if [ "$absent" = "fatal" ]; then
            printf '  [MISSING] %-30s %s\n' "$label" "-> $repair"
            return 1
        fi
        printf '  [warn]    %-30s %s\n' "$label" \
            "not built -- its tests SKIP; built by ./test.sh integration, or: $repair"
        return 0
    fi
    check_freshness "$label" "$found" "$srcs" "$pats" "-> $repair${note:+   $note}"
}

run_doctor() {
    local rc=0 missing_apt=() advisory_apt=() advisory_pip=() pkg status np_ok

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
    check_import "lxml"        lxml.etree                   "" "-> pip install -r requirements.txt   [fast: the ad6 translator/bridge tests]" || rc=1
    check_import "pycosat"     pycosat                      "" "-> pip install pycosat==0.6.6        [integration: test_ad6_translate; SOURCE build, needs python3-dev]" || rc=1
    check_import "python-sat"  pysat.solvers                "" "-> pip install -r requirements.txt   [fast: ad6/fave_bridge.py imports it at module level]" || rc=1
    check_import "pybison"     bison                        "" "-> see Dockerfile: pip install --no-binary :all: pybison==0.6.4  [integration]" || rc=1
    check_import "JPype1"      jpype                        "" "-> pip install JPype1==1.7.1         [integration: every APKeep/NDD test; an adapter raises from __init__, it does not skip]" || rc=1
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
        # Freshness against net_plumber/src, on the binary PATH actually
        # resolves to. The repair is `clean && all`, not `all`: item 0's
        # follow-up records a binary left linked against an older liblog4cxx,
        # failing at runtime with `undefined symbol: ...log4cxx...`, while
        # `make all` reported "nothing to be done" because the object
        # timestamps were current.
        np_ok=""
        [ -n "${NET_PLUMBER_FROM_BUILD_DIR:-}" ] && \
            np_ok="(from net_plumber/build; not installed on PATH)"
        check_freshness "net_plumber binary" "$(command -v net_plumber)" \
            "$ROOT/net_plumber/src" '*.cc *.cpp *.c *.h *.hh' \
            "-> make -C net_plumber/build clean && make -C net_plumber/build all   [no tier builds it]" \
            "$np_ok" || rc=1
    else
        # No "built but unreachable" branch: resolve_net_plumber has already
        # prepended the build directory, so reaching here means the binary is
        # genuinely absent (or not executable), not merely uninstalled.
        printf '  [MISSING] %-30s %s\n' "net_plumber binary" \
            "-> make -C net_plumber/build all && make -C net_plumber/build install   [smoke/integration/e2e/bench]"
        rc=1
    fi
    # fatal when absent: no tier builds this one, so its absence blocks
    # integration and e2e. Its sources are the binding AND the engine it wraps --
    # the measured case was an engine header change the binding exposes.
    check_artifact "libnetplumber .so built" \
        "$ROOT/net_plumber/python/libnetplumber*.so" \
        fatal "bash net_plumber/python/build_libnetplumber.sh" \
        "$ROOT/net_plumber/python $ROOT/net_plumber/src" '*.cc *.cpp *.c *.h *.hh' \
        "[no tier builds it; integration then fails as a WRONG ANSWER]" || rc=1
    # warn when absent, like the jars: run_integration builds it (test.sh's
    # build_libveriflow_fr.sh step), so absence is the normal clean-checkout
    # state. This used to print [MISSING] and set no rc -- the one artifact
    # whose three labels did not mean what they mean everywhere else.
    check_artifact "libveriflow_fr .so built" \
        "$ROOT/veriflow_fr/python/libveriflow_fr*.so" \
        warn "bash veriflow_fr/python/build_libveriflow_fr.sh" \
        "$ROOT/veriflow_fr/python $ROOT/veriflow_fr/src" '*.cc *.cpp *.c *.h *.hh' \
        "[integration rebuilds it]" || rc=1
    # The two Java engine jars, checked for FRESHNESS and not merely existence --
    # they are the same class of artifact as the .so above and fail the same way,
    # as a wrong answer rather than as a missing file. See check_jar's notes for
    # why only STALE is fatal here.
    check_artifact "APKeep engine jar" "$ROOT/apkeep/target/apkeep-1.0.0.jar" \
        warn "bash fave/test/apkeep_smoke.sh" \
        "$ROOT/apkeep/src $ROOT/apkeep/pom.xml" '*.java pom.xml' \
        "[fast: WRONG failures; integration rebuilds it]" || rc=1
    check_artifact "NDD engine jar" "$ROOT/ndd/target/ndd-1.0.1-jar-with-dependencies.jar" \
        warn "bash fave/test/ndd_build.sh" \
        "$ROOT/ndd/src $ROOT/ndd/pom.xml" '*.java pom.xml' \
        "[fast: WRONG failures; integration rebuilds it]" || rc=1

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
        echo "  see the [MISSING]/[STALE] lines above; each names the tier it blocks."
        echo "  Nothing above is a code defect -- these are container- and build-state gaps."
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
#   * a STALE apkeep/ndd jar -> the jar still loads, so the jar-backed tests RUN
#     and assert against an engine that predates the source change; they fail as
#     if an engine had computed a wrong answer. target/ is gitignored, so nothing
#     in git keeps jar and sources in step -- a jar built before a source change
#     simply survives it.
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

skipped=""
[ "$FAVE_SKIP_AD6" = "1" ] && skipped=" (ad6 tests SKIPPED: FAVE_SKIP_AD6=1)"
if [ "$rc" -eq 0 ]; then
    echo "RESULT: $tier PASSED$skipped"
else
    echo "RESULT: $tier FAILED$skipped"
fi
exit "$rc"
