#!/usr/bin/env bash

# Generate the wl_up benchmark device-model JSON that test_apkeep_ndd_wlup
# consumes: the pgf ip6tables ruleset plus topology.json / sources.json /
# routes.json / policies.json. These are gitignored generated artifacts
# (fave/.gitignore: bench/wl_up/*.json and bench/wl_up/rulesets/*-ruleset), so a
# clean integration checkout lacks them; this regenerates them from the tracked
# generators (the three ruleset scripts + topogen/routegen/policygen), which
# depend only on tracked sources -- no live backend, no reachability.csv needed.
#
# The reachability ORACLE for the NDD test is the tracked frozen BDD baseline
# matrix bench/wl_up/eval/mat_apk.json, NOT reachable.json. The policy artifacts
# are generated here all the same (they were not, until 2026-09-18): they are
# gitignored, test_apkeep_compliance_cond consumes checks.json, and without this
# it SKIPPED on a clean checkout rather than running. Generating them here also
# makes the invariant executable -- checks.json / cchecks.json / reachable.json
# are derived from the FPL inventory and policy (roles_and_services.txt +
# reach.txt) and from nothing else.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

W=bench/wl_up

# The ip6tables rulesets topogen.py references (and iptables/parser.py reads):
# the pgf firewall, the per-host DMZ/net rulesets, and the per-subnet client
# rulesets. Also gitignored (bench/wl_up/rulesets/*-ruleset) and deterministically
# derived from the tracked generator scripts, so they belong here with the rest of
# the regeneration -- otherwise the consuming test dies on a missing ruleset file.
# These are exactly the three steps wl_up/benchmark.py runs in _pre_preparation.
bash scripts/generate-pgf-ruleset.sh "$W"
bash scripts/generate-host-rulesets.sh "$W"
bash scripts/generate-clients-rulesets.sh "$W"

# device model: topology + sources, routes, probes/policies
"$PYTHON" "$W/topogen.py"
"$PYTHON" "$W/routegen.py"
"$PYTHON" "$W/policygen.py"

# policy artifacts: FPL inventory + policy -> reachability matrix -> checks.
# --strict and the default (enabled) Internet role mirror wl_up/benchmark.py;
# --roles carries each role's FPL attributes through to the check generator, so
# a role whose one node stands for a subnet (wl_up's Wifi, a /64 with no hosts)
# keeps the self-check its `Wifi <--> Wifi` rule asks for.
"$PYTHON" ../policy_translator/policy_translator.py --strict --csv \
    --out "$W/reachability.csv" --roles "$W/roles.json" \
    "$W/roles_and_services.txt" "$W/reach.txt"
# inventory.json (role -> model hosts) is gitignored too, and inventorygen reads
# the matrix produced above, so it belongs between the two steps.
"$PYTHON" "$W/inventorygen.py"
"$PYTHON" bench/reach_csv_to_checks.py -p "$W/reachability.csv" \
    -m "$W/inventory.json" --roles "$W/roles.json" --strict \
    -c "$W/checks.json" --cchecks "$W/cchecks.json" -j "$W/reachable.json"

echo "wl_up inputs generated under $W/"
