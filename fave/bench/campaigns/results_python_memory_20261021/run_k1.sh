#!/bin/sh
# PROTOCOL_k1.txt's one cell, alone. Run from fave/.
C=bench/campaigns/results_python_memory_20261021
T=bench/campaigns/results_ndd_berkeley_k1_trial_20261020
PYTHONPATH=. ../.venv/bin/python3 bench/campaign_inputs.py check $T || exit 1
FAVE_JVM_XMX=32g PYTHONPATH=. ../.venv/bin/python3 bench/incremental_cell.py \
  $T/inputs/wl_berkeley_k1 --engine ndd-apkeep --stream z --checks checks.json \
  --limit-rss-margin 2048 --memory-floor 0 --limit-wall 43200 \
  --out $C/cells/Z_wl_berkeley_k1_ndd-apkeep
echo "rc=$?"
