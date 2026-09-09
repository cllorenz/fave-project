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
# matrix bench/wl_up/eval/mat_apk.json, NOT reachable.json, so the ground-truth
# generation steps (reachability.csv -> reachable.json) are intentionally absent.

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

echo "wl_up inputs generated under $W/"
