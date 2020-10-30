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

[ -n "$1" ] && WDIR=$1 || WDIR=$(pwd)

RUNS=10
FAVE_RAW=results/fave_raw.dat

RESULTS=results/results.dat
echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

FAVE_RAW=results/raw_fave.dat
echo "" > $FAVE_RAW

for i in $(seq 1 $RUNS); do
  grep "seconds" results/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN { result = 0; } { result += $6; } END { print result * 1000.0; }' >> $FAVE_RAW
done

NP_RAW=results/np_raw.dat
echo -n "" > $NP_RAW

for i in $(seq 1 $RUNS); do
  grep "total" results/$i.raw/$i.np.stdout.log | awk '{ print $4/1000.0; }' >> $NP_RAW
  grep "seconds" results/$i.raw/$i.np.stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_RAW
done

stats FaVe $FAVE_RAW
stats NP $NP_RAW
