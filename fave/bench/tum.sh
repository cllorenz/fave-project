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

function stats {
    ASPECT=$1
    DATA=$2

    MEAN=`awk -f $WDIR/bench/mean.awk < $DATA`
    MEDIAN=`awk -f $WDIR/bench/median.awk < $DATA`
    MIN=`awk -f $WDIR/bench/min.awk < $DATA`
    MAX=`awk -f $WDIR/bench/max.awk < $DATA`

    echo "$ASPECT $MEAN $MEDIAN $MIN $MAX" >> $RESULTS
}

RUNS=10
RES_PATH=$(pwd)/tum/fffuu6
rm -rf $(pwd)/tum
mkdir -p $RES_PATH/raw

WDIR=fave-code/fave
TUM_RS=bench/wl_tum/tum-ruleset

RESULTS=$RES_PATH/results.dat
echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

TUM_TOTAL=$RES_PATH/raw_runtimes.dat

echo -n "" > $TUM_TOTAL

echo -n "run fffuu6:"
for i in $(seq 1 $RUNS); do
    LOG=$RES_PATH/raw/$i.up.log
    echo -n " $i"
    cd fffuu/haskell_tool
    /usr/bin/time -f "%e" -o $i.time \
        cabal run fffuu6 -- \
	    --service_matrix_dport 80 \
	    ../thy/Iptables_Semantics/Examples/UP/ip6tables-save-up > $LOG 2> /dev/null

    grep "^measure" $LOG | \
        grep -v "spoofing" | \
	cut -d ':' -f 2 | \
	tr -d ' s' | \
	awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum * 1000.0; }' >> $TUM_TOTAL
     cd ../..
done
echo ""

echo "run fave"
cd fave-code/fave
bash bench/run_benchmarks.sh bench/wl_tum/benchmark.py -4 -r $TUM_RS
bash bench/eval_benchmarks_tum.sh
cd ../..

mv fave-code/fave/results $RES_PATH/../fave
stats "fffuu6" $TUM_TOTAL

grep -v "Checks" $RES_PATH/../fave/results.dat | tail -n+2 >> $RESULTS
mv $RESULTS tum/
