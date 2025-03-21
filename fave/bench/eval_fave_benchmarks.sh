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

# without this, mawk converts floats to the format specified as locale,
# e.g., using a comma instead of a dot in German
export LC_NUMERIC=C

RDIR=$1

RUNS=$(ls $RDIR/fave | cut -d'.' -f1 | sort -n | tail -n1)

RESULTS=$RDIR/results.dat
[ ! -f $RESULTS ] && echo "Tool Initialization Reachability Compliance Total \"Initialization StdDev.\" \"Reachability StdDev.\" \"Compliance StdDev.\" \"Total StdDev.\"" > $RESULTS

PARSING=$RDIR/raw_parsing.dat
echo -n "" > $PARSING

FAVE_INIT=$RDIR/raw_fave_init.dat
echo -n "" > $FAVE_INIT

FAVE_REACH=$RDIR/raw_fave_reach.dat
echo -n "" > $FAVE_REACH

FAVE_TOTAL=$RDIR/raw_fave_total.dat
echo -n "" > $FAVE_TOTAL

CHECKS=$RDIR/raw_checks.dat
echo -n "" > $CHECKS

for i in $(seq 1 $RUNS); do
  grep "parse device" $RDIR/fave/$i.raw/stdout.log |
    awk 'BEGIN { result = 0; } { result += $4; } END { print result; }' >> $PARSING

  FAVE_INIT_TMP=`grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log | grep -v "dump\|stop\|anomalies\|report\|compliance" | \
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
    }'`
  echo $FAVE_INIT_TMP >> $FAVE_INIT

  FAVE_REACH_TMP=`grep "seconds" $RDIR/fave/$i.raw/np/aggregator.log |
    grep -v "dump\|stop\|anomalies\|report\|compliance" | \
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
      print result * 1000.0;
    }'`
  echo $FAVE_REACH_TMP >> $FAVE_REACH

  FAVE_CHECKS_TMP=`grep "check_compliance in" $RDIR/fave/$i.raw/np/aggregator.log | \
    awk '{ print $6 * 1000.0; }'
    #cut -d' ' -f6`

#  FAVE_CHECKS_TMP=`grep "checked flow tree in" $RDIR/fave/$i.raw/np/aggregator.log | \
#    awk 'BEGIN { result = 0; } { result += $7; } END { print result; }'`
  echo $FAVE_CHECKS_TMP >> $CHECKS

  echo "$FAVE_INIT_TMP + $FAVE_REACH_TMP + $FAVE_CHECKS_TMP" | bc >> $FAVE_TOTAL
done

NP_INIT=$RDIR/raw_np_init.dat
echo -n "" > $NP_INIT

NP_REACH=$RDIR/raw_np_reach.dat
echo -n "" > $NP_REACH

NP_CHECK=$RDIR/raw_np_check.dat
echo -n "" > $NP_CHECK

NP_TOTAL=$RDIR/raw_np_total.dat
echo -n "" > $NP_TOTAL

for i in $(seq 1 $RUNS); do
  NP_INIT_TMP=`grep "total" $RDIR/np/$i.raw/stdout.log | \
    awk '{ print $4/1000.0; }'`
  echo $NP_INIT_TMP >> $NP_INIT
  NP_REACH_TMP=`grep "policy file in" $RDIR/np/$i.raw/stdout.log | tr -d '()us' | \
    awk '{ print $7/1000.0; }'`
  echo $NP_REACH_TMP >> $NP_REACH
  NP_CHECK_TMP=`grep "compliance in" $RDIR/np/$i.raw/stdout.log | tr -d '()us' | \
    awk '{ print $6/1000.0; }'`
  echo $NP_CHECK_TMP >> $NP_CHECK
  echo "$NP_INIT_TMP + $NP_REACH_TMP + $NP_CHECK_TMP" | bc >> $NP_TOTAL
done

stats "FaVe" $FAVE_INIT $FAVE_REACH $CHECKS $FAVE_TOTAL
stats "NetPlumber" $NP_INIT $NP_REACH $NP_CHECK $NP_TOTAL #<(echo -e "0\n0")
