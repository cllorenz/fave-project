#!/usr/bin/env bash

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

RSPATH="bench/up"
RULESETS="up_client_fw:$RSPATH/medium-client-ruleset,up_server_fw:$RSPATH/medium-server-ruleset,up_gateway_fw:$RSPATH/pgf.uni-potsdam.de-ruleset"
ANOMALIES="shadow"

export PYTHONPATH=.
"$PYTHON" main.py \
    --no-active-interfaces \
    --network bench/up/medium.xml \
    --rulesets $RULESETS \
    --anomalies $ANOMALIES

