#!/bin/bash
# From fave/, once, AFTER the integration tier passed on the code to be
# measured (it generates the grid workloads' inputs) and BEFORE the protocol
# is declared: the machine and artifact records, wl_berkeley per size, and
# the hashes of every input (INCREMENTAL_PLAN.md D17.3, D17.7).
set -eu
OUT=bench/campaigns/results_inc_dev_d16_fave_20261017
PY=../.venv/bin/python3
$PY bench/campaign_stamps.py write $OUT
$PY bench/campaign_inputs.py berkeley $OUT 3 1
SPLIT=topology=device_topology.json,policies=probes.json
$PY bench/campaign_inputs.py record $OUT bench/wl_airtel1 bench/wl_airtel2 bench/wl_cloud \
    bench/wl_up bench/wl_tum bench/wl_stanford/stanford-json:$SPLIT bench/wl_i2/i2-json:$SPLIT \
    $OUT/inputs/wl_berkeley_k3 \
    $OUT/inputs/wl_berkeley_k1
