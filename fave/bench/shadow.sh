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
RES_SHADOW=$(pwd)/results/shadow
#rm -rf $RES_SHADOW/*
mkdir -p $RES_SHADOW

export PYTHONPATH=.

FWS="fw1 fw2 fw3 fw4 fw5 random"
RULES="500 1000 2000 5000 10000 15000"

# random
for fw in $FWS; do
    for c in $RULES; do
        RES_RUN=$RES_SHADOW/$fw/$c
        mkdir -p $RES_RUN
	for r in $(seq 1 $RUNS); do
#            echo $RES_RUN/$r/$fw"_"$c".fw"
            python3 bench/wl_shadow/benchmark.py -u -r bench/wl_shadow/rulesets/$fw"_"$c".fw"
            cp /dev/shm/np/aggregator.log $RES_RUN/$r"_fave.log"
            cp /dev/shm/np/rpc.log $RES_RUN/$r"_np.log"
        done
        cp -r np_dump $RES_RUN/
    done
done
