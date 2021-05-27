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
  INIT=$2
  REACH=$3

  MEAN_INIT=`awk -f bench/mean.awk < $INIT`
  STDDEV_INIT=`awk -f bench/stddev.awk -vMEAN=$MEAN_INIT < $INIT`

  MEAN_REACH=`awk -f bench/mean.awk < $REACH`
  STDDEV_REACH=`awk -f bench/stddev.awk -vMEAN=$MEAN_REACH < $REACH`

  echo "$TOOL $MEAN_INIT $MEAN_REACH NaN $STDDEV_INIT $STDDEV_REACH NaN" >> $RESULTS
}

RDIR=$1
[ -n "$2" ] && TOOL=fffuu6 || TOOL=fffuu

RUNS=10

RESULTS=$RDIR/results.dat
[ ! -f $RESULTS ] && echo "Tool Initialization Reachability Compliance \"Initialization StdDev.\" \"Reachability StdDev.\" \"Compliance StdDev.\"" > $RESULTS

FFFUU_INIT_RAW=$RDIR/raw_fffuu_init.dat
FFFUU_REACH_RAW=$RDIR/raw_fffuu_reach.dat
echo -n "" > $FFFUU_INIT_RAW
echo -n "" > $FFFUU_REACH_RAW

for i in $(seq 1 $RUNS); do
    grep "^measure" $RDIR/fffuu/$i.stdout.log | \
        grep -v "spoofing\|matrices" | \
        cut -d ':' -f 2 | \
        tr -d ' s' | \
        awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum * 1000.0; }' >> $FFFUU_INIT_RAW

    grep "^measure" $RDIR/fffuu/$i.stdout.log | \
        grep "matrices" | \
        cut -d ':' -f 2 | \
        tr -d ' s' | \
        awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum * 1000.0; }' >> $FFFUU_REACH_RAW
done

#FAVE_RAW=$RDIR/fave_raw.dat
#echo "" > $FAVE_RAW
#
#for i in $(seq 1 $RUNS); do
#  grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
#  awk 'BEGIN { result = 0; } { result += $6; } END { print result * 1000.0; }' >> $FAVE_RAW
#done
#
#NP_RAW=$RDIR/np_raw.dat
#echo -n "" > $NP_RAW
#
#for i in $(seq 1 $RUNS); do
#  grep "total" $RDIR/np/$i.raw/stdout.log | awk '{ print $4/1000.0; }' >> $NP_RAW
#  grep "seconds" $RDIR/np/$i.raw/stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_RAW
#done

stats $TOOL $FFFUU_INIT_RAW $FFFUU_REACH_RAW
#stats FaVe $FAVE_RAW
#stats NP $NP_RAW
