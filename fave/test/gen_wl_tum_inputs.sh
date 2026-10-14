#!/usr/bin/env bash
# Generate wl_tum's inputs -- gitignored generated artifacts, from tracked
# sources only, no live backend (bench/wl_tum/WORKLOAD.md):
#
#  * the policy model (owner, 2026-10-14): service_matrix.py reads the ruleset
#    independently of FaVe's engines, fplgen.py writes the FPL inventory and
#    policy, policy_translator and reach_csv_to_checks.py turn it into
#    checks.json, and topogen/routegen/policygen/inventorygen write the model
#    -- fw.tum, the VLAN demultiplexer, a source and a probe per endpoint --
#    the steps and options bench/wl_tum/benchmark.py takes;
#  * the SINGLE variant under bench/wl_tum/single/ -- the model wl_tum had
#    until then (one source, one universal probe, no checks), which V5 and
#    D11 measured and test_apkeep_tum, test_apkeep_ndd_fwd and
#    test_veriflow_differential replay.
#
# IPv4 and tum-ruleset, as bench/wl_tum/benchmark.py's defaults.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"
RULESET=bench/wl_tum/rulesets/tum-ruleset
W=bench/wl_tum

"$PYTHON" $W/service_matrix.py
"$PYTHON" $W/fplgen.py
"$PYTHON" ../policy_translator/policy_translator.py --strict --roles $W/roles.json \
    --csv --out $W/reachability.csv $W/roles_and_services.txt $W/reach.txt
"$PYTHON" $W/inventorygen.py
"$PYTHON" bench/reach_csv_to_checks.py --strict --only-with Internet --deny-unpermitted-services \
    -p $W/reachability.csv -m $W/inventory.json --roles $W/roles.json \
    -c $W/checks.json --cchecks $W/cchecks.json -j $W/reachable.json
"$PYTHON" $W/routegen.py
"$PYTHON" $W/policygen.py
"$PYTHON" $W/topogen.py ipv4 "$RULESET"
"$PYTHON" $W/single/gen.py ipv4 "$RULESET"
echo "wl_tum inputs generated under $W/ (the policy model) and $W/single/ (the single variant)"
