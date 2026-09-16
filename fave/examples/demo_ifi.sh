#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

# The interpreter to run this project's Python with. A bare `python3` is whatever
# PATH resolves first, which in a container whose venv is not activated is the
# SYSTEM interpreter, with none of the dependencies -- see resolve_python.sh.
# `./test.sh` exports the interpreter it resolved; standalone callers keep the
# old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

export PYTHONPATH=$(pwd)

POLICY_HTML_URI=$(pwd)/../policy_translator/examples/ifi-klemens.html
REACH_HTML_URI=$(pwd)/../policy_translator/examples/ifi-klemens-reach.html

read -n1 -r -p "Generate policy matrix from inventory and policy. Press any key to continue..."

"$PYTHON" ../policy_translator/policy_translator.py \
    --html --out $POLICY_HTML_URI \
    bench/wl_ifi/roles_and_services.orig.txt \
    bench/wl_ifi/policy.orig.txt

firefox --new-window file://$POLICY_HTML_URI 2> /dev/null &

read -n1 -r -p "Calculate reachability with fave and net_plumber. Press any key to continue..."

"$PYTHON" bench/wl_ifi/benchmark.py -v

read -n1 -r -p "Generate reachability matrix from results. Press any key to continue..."

"$PYTHON" ../policy_translator/policy_translator.py \
    --html --out $REACH_HTML_URI \
    --report np_dump/reach.csv \
    bench/wl_ifi/roles_and_services.orig.txt \
    bench/wl_ifi/policy.orig.txt

firefox --new-window file://$REACH_HTML_URI 2> /dev/null &
