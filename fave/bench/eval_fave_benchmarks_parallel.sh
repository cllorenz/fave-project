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

function fave_stats {
  TOOL=$1

  for threads in 1 2 4 8 16 24; do
      echo -n "$TOOL$threads" >> $RESULTS

      for DATA in ${@:2}; do
          MEAN=`grep "^$threads " $DATA | cut -d' ' -f2 | awk -f bench/mean.awk`
          if [ "$MEAN" == "0" ]; then
              echo -n " NaN" >> $RESULTS
          else
              echo -n " $MEAN" >> $RESULTS
          fi
      done

      for DATA in ${@:2}; do
          MEAN=`grep "^$threads " $DATA | cut -d' ' -f2 | awk -f bench/mean.awk`
          STDDEV=`grep "^$threads " $DATA | cut -d' ' -f2 | awk -f bench/stddev.awk -vMEAN=$MEAN`
          if [ "$STDDEV" == "0" ]; then
              echo -n " NaN" >> $RESULTS
          else
              echo -n " $STDDEV" >> $RESULTS
          fi
      done

      echo "" >> $RESULTS
  done
}

function np_stats {
  TOOL=$1

  echo -n $TOOL >> $RESULTS

  for DATA in ${@:2}; do
      MEAN=`awk -f bench/mean.awk < $DATA`
      if [ "$MEAN" == "0" ]; then
          echo -n " NaN" >> $RESULTS
      else
          echo -n " $MEAN" >> $RESULTS
      fi
  done

  for DATA in ${@:2}; do
      MEAN=`awk -f bench/mean.awk < $DATA`
      STDDEV=`awk -f bench/stddev.awk -vMEAN=$MEAN < $DATA`
      if [ "$STDDEV" == "0" ]; then
          echo -n " NaN" >> $RESULTS
      else
          echo -n " $STDDEV" >> $RESULTS
      fi
  done

  echo "" >> $RESULTS
}

RDIR=$1

RUNS=10

RESULTS=$RDIR/results.dat
[ ! -f $RESULTS ] && echo "Tool Initialization Reachability Compliance \"Initialization StdDev.\" \"Reachability StdDev.\" \"Compliance StdDev.\"" > $RESULTS

PARSING=$RDIR/raw_parsing.dat
echo -n "" > $PARSING
FAVE_INIT=$RDIR/raw_fave_init.dat
echo -n "" > $FAVE_INIT
FAVE_REACH=$RDIR/raw_fave_reach.dat
echo -n "" > $FAVE_REACH

for threads in 1 2 4 8 16 24; do
    for i in $(seq 1 $RUNS); do
      echo -n "$threads " >> $FAVE_INIT
      grep "seconds" $RDIR/fave/$threads/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
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

      echo -n "$threads " >> $FAVE_REACH
      grep "seconds" $RDIR/fave/$threads/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
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

for threads in 1 2 4 8 16 24; do
    for i in $(seq 1 $RUNS); do
      grep "parse device" $RDIR/fave/$threads/$i.raw/stdout.log | cut -d' ' -f4 | \
        awk 'BEGIN { result = 0; } { result += $1; } END { print result; }' >> $PARSING
      echo -n "$threads " >> $CHECKS
      grep "total:" $RDIR/fave/$threads/$i.raw/stdout.log | awk 'BEGIN { max = -1; } { if ( max < $2 ) { max = $2; } } END { print max; }' >> $CHECKS
    done
done

fave_stats "FaVe" $FAVE_INIT $FAVE_REACH $CHECKS
np_stats "NetPlumber" $NP_INIT $NP_REACH <(echo -e "0\n0")
