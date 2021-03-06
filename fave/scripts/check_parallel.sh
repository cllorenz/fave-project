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


CHECKS=$1
THREADS=$2

DUMP=$3

for i in $(seq 0 $((THREADS-1))); do
     python2 test/check_flows.py -b -r -t "$i:$THREADS" -f "$CHECKS" -d $DUMP &
     pids[${i}]=$!
done

for pid in ${pids[*]}; do
     wait $pid
done
