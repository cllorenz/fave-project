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
#RES_UP=$(pwd)/results/up-full
RES_UP=$(pwd)/results/up-parallel
rm -rf $RES_UP
mkdir -p $RES_UP

echo "run fave on up workload..."
#bash bench/run_fave_benchmarks.sh $RES_UP bench/wl_up/benchmark.py
bash bench/run_fave_benchmarks_parallel.sh $RES_UP bench/wl_up/benchmark.py

echo "evaluate fave and np for up workload..."
bash bench/eval_fave_benchmarks.sh $RES_UP
bash bench/eval_fave_aggr_benchmarks.sh $RES_UP
