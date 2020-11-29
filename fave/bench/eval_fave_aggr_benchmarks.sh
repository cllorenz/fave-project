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
  TOOL=$1
  DATA=$2

  MEAN=`awk -f bench/mean.awk < $DATA`
  MEDIAN=`awk -f bench/median.awk < $DATA`
  MIN=`awk -f bench/min.awk < $DATA`
  MAX=`awk -f bench/max.awk < $DATA`

  echo "$TOOL $MEAN $MEDIAN $MIN $MAX" >> $RESULTS
}

RDIR=$1

RUNS=10

RESULTS=$RDIR/results_aggr.dat
[ ! -f $RESULTS ] && echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

FAVE_RAW=$RDIR/fave_raw.dat
echo -n "" > $FAVE_RAW

for i in $(seq 1 $RUNS); do
  grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN { result = 0; } { result += $6; } END { print result * 1000.0; }' >> $FAVE_RAW
done

NP_RAW_INIT=$RDIR/raw_np_init.dat
echo -n "" > $NP_RAW_INIT
NP_RAW_REACH=$RDIR/raw_np_reach.dat
echo -n "" > $NP_RAW_REACH

for i in $(seq 1 $RUNS); do
  grep "total" $RDIR/np/$i.raw/stdout.log | awk '{ print $4/1000.0; }' >> $NP_RAW_INIT
  grep "seconds" $RDIR/np/$i.raw/stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_RAW_REACH
done

NP_RAW=$RDIR/raw_np.dat
paste $NP_RAW_INIT $NP_RAW_REACH | awk '{ sum = $1 + $2; print sum; }' > $NP_RAW

stats FaVe $FAVE_RAW
stats NP $NP_RAW
