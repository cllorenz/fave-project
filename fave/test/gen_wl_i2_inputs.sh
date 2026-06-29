#!/usr/bin/env bash

# Generate the wl_i2 (Internet2) inputs that test_apkeep_i2 consumes: the device
# model (device_topology.json / routes.json / sources.json / probes.json) and
# the policy oracle reachable.json. These are gitignored generated artifacts --
# the live benchmark produces them, but the deterministic integration tier needs
# them in a clean checkout.
#
# Both regenerate from *tracked* inputs with no live backend, mirroring the wl_i2
# benchmark's preparation: prepare_benchmark converts the HSA transfer functions
# (i2-json/*.tf.json + config.json + mapping.json) into the FaVe device model;
# policy_translator turns the policy (roles.txt + reach.txt) into the reach.csv
# matrix; and reach_csv_to_checks turns that into reachable.json.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> fave/
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$(pwd)"

D=bench/wl_i2/i2-json
W=bench/wl_i2

# device model: HSA transfer functions -> FaVe switches + dst-IP rules.
# The intervals mirror wl_i2/benchmark.py _pre_preparation.
"$PYTHON" - <<'PY'
import json
from netplumber.mapping import Mapping
from bench.np_preparation import prepare_benchmark
D = 'bench/wl_i2/i2-json'
intervals = {(0, 1): 0, (1, 10000): 0, (10000, 10001): 1, (20001, 30000): 1}
mapping = Mapping.from_json(json.load(open(D + '/mapping.json')))
prepare_benchmark(D, D + '/device_topology.json', D + '/sources.json',
                  D + '/probes.json', D + '/routes.json', mapping, intervals)
PY

# oracle: policy (roles.txt + reach.txt) -> reach.csv matrix -> reachable.json.
# --no-internet, -m empty.json and no suffix mirror wl_i2/benchmark.py.
"$PYTHON" ../policy_translator/policy_translator.py --no-internet --csv \
    --out "$W/reach.csv" "$W/roles.txt" "$W/reach.txt"
"$PYTHON" bench/reach_csv_to_checks.py -p "$W/reach.csv" -m bench/empty.json \
    -c "$W/checks.json" --cchecks "$W/cchecks.json" -j "$W/reachable.json"

echo "wl_i2 inputs generated under $D/ + bench/wl_i2/reachable.json"
