#!/usr/bin/env bash

# Generate the wl_ifi benchmark input JSON that test_apkeep_wl_ifi consumes:
# topology.json / routes.json / sources.json / policies.json (the device model)
# and reachable.json (the NetPlumber-derived ground truth). These are gitignored
# generated artifacts -- the live benchmark produces them in the e2e/smoke tier,
# but the deterministic integration tier (where the APKeep wl_ifi test runs) gets
# a clean checkout without them. This regenerates them from the *tracked* inputs
# (ifi.csv, acls.txt, reachability.csv, bench/empty.json), i.e. the same steps
# GenericBenchmark._preparation runs MINUS the policy_translator pass (the policy
# matrix reachability.csv is already committed), so no live backend is needed.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

W=bench/wl_ifi

# inventory: cisco config -> inventory.json (matches the benchmark's _pre_/_preparation)
"$PYTHON" "$W/cisco_to_inventory.py"
"$PYTHON" "$W/inventorygen.py"

# ground truth: the committed policy matrix (reachability.csv) -> reachable.json
# (+ checks/cchecks). -m bench/empty.json and -s .ifi mirror wl_ifi/benchmark.py.
# --roles is what decides whether a role's SELF-rule states something real:
# without it `_load_role_attributes` returns {} and every self-rule is dropped
# as degenerate. wl_ifi's 16 roles each abstract a proper subnet, so each
# self-rule is a genuine compliance question (commit 7ec21124, TODO.md item
# 14). GenericBenchmark._convert_policy_to_checks passes it; this script did
# not, so the two produced different ground truth for the same workload -- 54
# pairs here against the benchmark's 70 -- and whichever ran last silently won.
"$PYTHON" bench/reach_csv_to_checks.py -s .ifi -p "$W/reachability.csv" \
    -m bench/empty.json --roles "$W/roles.json" \
    -c "$W/checks.json" --cchecks "$W/cchecks.json" \
    -j "$W/reachable.json"
# The STATELESS variant of the same policy (APKEEP_BACKEND.md, 2026-09-18):
# `<-->` where the original says `<->>`, so the policy asks only for what
# wl_ifi's state-blind Cisco ACLs can express and a correct tool must report
# ZERO violations. Generated alongside rather than instead of the original --
# the stateful configuration is the one that documents the policy/model
# mismatch, and running both exercises a tool on each kind of policy.
"$PYTHON" bench/reach_csv_to_checks.py -s .ifi \
    -p "$W/reachability_stateless.csv" \
    -m bench/empty.json --roles "$W/roles.json" \
    -c "$W/checks_stateless.json" \
    --cchecks "$W/cchecks_stateless.json" \
    -j "$W/reachable_stateless.json"

# device model: topology, routes, sources + probes
"$PYTHON" "$W/topogen.py"
"$PYTHON" "$W/routegen.py"
"$PYTHON" "$W/policygen.py"

echo "wl_ifi inputs generated under $W/"
