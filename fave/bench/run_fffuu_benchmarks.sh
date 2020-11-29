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

RES_PATH=$1
[ -n "$2" ] && RULESET=$2 || RULESET=bench/wl_tum/tum-ruleset
[ "$3" == "-6" ] && TOOL=fffuu6 || TOOL=fffuu

RUNS=10

TUM_TOTAL=$RES_PATH/raw_runtimes.dat

echo -n "" > $TUM_TOTAL

echo -n "run $TOOL:"
mkdir -p $RES_PATH/fffuu
for i in $(seq 1 $RUNS); do
    LOG=$RES_PATH/fffuu/$i.stdout.log
    ELOG=$RES_PATH/fffuu/$i.stderr.log
    echo -n " $i"
    cd ../../fffuu/haskell_tool
    /usr/bin/time -f "%e" -o $i.time \
        cabal run $TOOL -- \
	    --service_matrix_dport 80 \
	    $RULESET > $LOG 2> $ELOG
done
echo ""
