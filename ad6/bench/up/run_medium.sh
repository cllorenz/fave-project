#!/usr/bin/env bash

RSPATH="bench/up"
RULESETS="up_client_fw:$RSPATH/medium-client-ruleset,up_server_fw:$RSPATH/medium-server-ruleset,up_gateway_fw:$RSPATH/pgf.uni-potsdam.de-ruleset"
ANOMALIES="shadow"

export PYTHONPATH=.
python3 main.py \
    --no-active-interfaces \
    --network bench/up/medium.xml \
    --rulesets $RULESETS \
    --anomalies $ANOMALIES

