#!/usr/bin/env bash

# Generate the wl_stanford inputs that test_apkeep_stanford consumes: the device
# model (device_topology.json / routes.json / sources.json / probes.json) and the
# policy oracle reachable.json. These are gitignored generated artifacts.
#
# Regenerated from *tracked* inputs with no live backend, mirroring the
# wl_stanford benchmark's preparation: prepare_benchmark converts the HSA transfer
# functions (stanford-json/*.tf.json + config.json + mapping.json) into FaVe's
# in/mid/out switch model; policy_translator turns the policy (roles.txt +
# reach.txt) into the reach.csv matrix; reach_csv_to_checks turns that into
# reachable.json. --no-internet mirrors wl_stanford/benchmark.py (use_internet=False).

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

D=bench/wl_stanford/stanford-json
W=bench/wl_stanford

# device model: HSA transfer functions -> FaVe in/mid/out switches. The 3-table
# intervals mirror wl_stanford/benchmark.py _pre_preparation.
"$PYTHON" - <<'PY'
import json
from netplumber.mapping import Mapping
from bench.np_preparation import prepare_benchmark
D = 'bench/wl_stanford/stanford-json'
intervals = {
    (0, 1): 0, (1, 10000): 0,          # ingress table
    (20000, 20001): 1, (10001, 20000): 1,  # mid table
    (20001, 30000): 2, (30001, 40000): 2,  # egress table
}
mapping = Mapping.from_json(json.load(open(D + '/mapping.json')))
prepare_benchmark(D, D + '/device_topology.json', D + '/sources.json',
                  D + '/probes.json', D + '/routes.json', mapping, intervals)
PY

# oracle: policy (roles.txt + reach.txt) -> reach.csv -> reachable.json.
"$PYTHON" ../policy_translator/policy_translator.py --no-internet --csv \
    --out "$W/reach.csv" "$W/roles.txt" "$W/reach.txt"
"$PYTHON" bench/reach_csv_to_checks.py -p "$W/reach.csv" -m bench/empty.json \
    -c "$W/checks.json" --cchecks "$W/cchecks.json" -j "$W/reachable.json"

echo "wl_stanford inputs generated under $D/ + reachable.json"
