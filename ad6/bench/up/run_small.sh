#!/usr/bin/env bash

RSPATH="bench/up"
RULESETS="up_client_fw:$RSPATH/small-client-ruleset,up_server_fw:$RSPATH/small-server-ruleset"
ANOMALIES="shadow"

export PYTHONPATH=.
python3 main.py \
    --no-active-interfaces \
    --network bench/up/small.xml \
    --rulesets $RULESETS \
    --anomalies $ANOMALIES

