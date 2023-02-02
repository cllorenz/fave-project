#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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
RESULTS=results/mb_expand
mkdir -p $RESULTS
rm -rf $RESULTS/*

export PYTHONPATH=.

for count in 10 100 1000 10000 20000 30000 40000 50000 60000; do
	for i in $(seq 1 $RUNS); do
		python3 bench/wl_expand/benchmark.py -v -c $count
		cp /dev/shm/np/rpc.log $RESULTS/$count.$i.rpc.log
	done
done
