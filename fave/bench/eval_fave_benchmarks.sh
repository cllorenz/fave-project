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

  MEAN=`awk -f bench/mean.awk < $DATA`
  MEDIAN=`awk -f bench/median.awk < $DATA`
  MIN=`awk -f bench/min.awk < $DATA`
  MAX=`awk -f bench/max.awk < $DATA`

  echo "$ASPECT $MEAN $MEDIAN $MIN $MAX" >> $RESULTS
}

RDIR=$1

RUNS=10

RESULTS=$RDIR/results.dat
[ ! -f $RESULTS ] && echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

PARSING=$RDIR/raw_parsing.dat
echo -n "" > $PARSING
FAVE_INIT=$RDIR/raw_fave_init.dat
echo -n "" > $FAVE_INIT
FAVE_REACH=$RDIR/raw_fave_reach.dat
echo -n "" > $FAVE_REACH

for i in $(seq 1 $RUNS); do
  grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN {
    done = 0; result = 0;
  } {
    if (done || $4 == "generators" || $4 == "generator") {
      done = 1;
    } else if (done && $4 == "probe") {
      done = 0;
      result += $6;
    } else {
      result += $6;
    }
  } END {
    print result * 1000.0;
  }' >> $FAVE_INIT

  grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN {
    start = 0;
    result = 0;
  } {
    if (start || $4 == "generators" || $4 == "generator") {
      start = 1;
      if ($4 == "generators" || $4 == "generator") {
        result += $6;
      } else if ($4 == "links") {
        result += $6;
      } else if ($4 == "probe") {
        start = 0;
      }
    }
  } END {
    print result * 1000.0
  }' >> $FAVE_REACH
done

NP_INIT=$RDIR/raw_np_init.dat
echo -n "" > $NP_INIT
NP_REACH=$RDIR/raw_np_reach.dat
echo -n "" > $NP_REACH

for i in $(seq 1 $RUNS); do
  grep "total" $RDIR/np/$i.raw/stdout.log | awk '{ print $4/1000.0; }' >> $NP_INIT
  grep "seconds" $RDIR/np/$i.raw/stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_REACH
done

CHECKS=$RDIR/raw_checks.dat
echo -n "" > $CHECKS

for i in $(seq 1 $RUNS); do
  grep "parse device" $RDIR/fave/$i.raw/stdout.log | cut -d' ' -f4 | \
    awk 'BEGIN { result = 0; } { result += $1; } END { print result; }' >> $PARSING
  grep "checked flow tree in" $RDIR/fave/$i.raw/stdout.log | cut -d' ' -f5 | \
    awk 'BEGIN { result = 0; } { result += $1; } END { print result; }' >> $CHECKS
done

stats Parsing $PARSING
stats "\"FaVe Init\"" $FAVE_INIT
stats "\"FaVe Reach\"" $FAVE_REACH
stats "\"NP Init\"" $NP_INIT
stats "\"NP Reach\"" $NP_REACH
stats Checks $CHECKS
