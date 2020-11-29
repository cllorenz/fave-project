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

RUNS=10
RES_TUM=$(pwd)/results/tum
RES_UP=$(pwd)/results/up
rm -rf $(pwd)/results
mkdir -p $RES_TUM
mkdir -p $RES_UP

bash scripts/generate-pgf-ruleset.sh bench/wl_tum

FAVE_TUM_RS=bench/wl_tum/rulesets/tum-ruleset
FAVE_UP_RS=bench/wl_tum/rulesets/pgf.uni-potsdam.de-ruleset
FFFUU_TUM_RS=../thy/Iptables_Semantics/Examples/TUM_Net_Firewall/iptables-save-2015-05-15_15-23-41_cheating
FFFUU6_UP_RS=../thy/Iptables_Semantics/Examples/UP/ip6tables-save-up

#bash scripts/convert-ruleset-to-iptables-save.sh $FAVE_UP_RS $FFFUU_UP_RS

echo "run fffuu6 on up workload..."
bash bench/run_fffuu_benchmarks.sh $RES_UP $FFFUU6_UP_RS -6

echo "evaluate fffuu6 on up workload..."
bash bench/eval_fffuu_benchmarks.sh $RES_UP -6

echo "run fave on up workload..."
bash bench/run_fave_benchmarks.sh $RES_UP bench/wl_tum/benchmark.py $FAVE_UP_RS -6

echo "evaluate fave and np for up workload..."
bash bench/eval_fave_benchmarks.sh $RES_UP
bash bench/eval_fave_aggr_benchmarks.sh $RES_UP

echo "run fffuu on tum workload..."
bash bench/run_fffuu_benchmarks.sh $RES_TUM $FFFUU_TUM_RS

echo "evaluate fffuu on tum workload"
bash bench/eval_fffuu_benchmarks.sh $RES_TUM

echo "run fave on tum workload..."
bash bench/run_fave_benchmarks.sh $RES_TUM bench/wl_tum/benchmark.py $FAVE_TUM_RS -4

echo "evaluate fave and np on tum workload"
bash bench/eval_fave_benchmarks.sh $RES_TUM
bash bench/eval_fave_aggr_benchmarks.sh $RES_TUM
