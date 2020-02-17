#!/usr/bin/env bash

function stats {
  ASPECT=$1
  DATA=$2
#  TOTAL=`awk -v runs="$RUNS" 'BEGIN { total = 0; } { total += $1; } END { print total/runs; }' < $DATA`

  MEAN=`awk 'BEGIN { total = 0; } { total += $1; } END { print total/NR; }' < $DATA`

  MEDIAN=`sort -n $DATA | awk '{ count[NR] = $1; } END { if (NR % 2) { print count[(NR + 1) / 2]; } else { print (count[NR / 2]); } }'`

  MIN=`awk 'BEGIN { min = 100000.0; } { if ( $1 < min ) { min = $1; } } END { print min; }' < $DATA`

  MAX=`awk 'BEGIN { max = 0.0; } {if ( $1 > max) { max = $1; } } END { print max; }' < $DATA`

  echo "$ASPECT $MEAN $MEDIAN $MIN $MAX" >> $RESULTS
}

RUNS=2

RESULTS=results/results.dat
echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

FAVE_INIT=results/raw_fave_init.dat
echo -n "" > $FAVE_INIT
FAVE_REACH=results/raw_fave_reach.dat
echo -n "" > $FAVE_REACH

for i in $(seq 1 $RUNS); do
  grep "seconds" results/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN { done = 0; result = 0; } { if (done || $4 == "generator") { done = 1; } else if (done && $4 == "probe") { done = 0; result += $6; } else { result += $6; } } END { print result * 1000.0; }' >> $FAVE_INIT
#  awk 'BEGIN { done = 0; } { if (done || $4 == "generator") { done = 1; } else if (done && $4 == "probe") { done = 0; print $6 * 1000.0 } else { print $6 * 1000.0 } }' >> $FAVE_INIT
  grep "seconds" results/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN { start = 0; result = 0; } { if (start || $4 == "generator") { start = 1;  if ($4 == "generator") { result += $6; } else if ($4 == "links") { result += $6; } else if ($4 == "probe") { start = 0; } } } END { print result * 1000.0 }' >> $FAVE_REACH
#  awk 'BEGIN { start = 0; pos = 1; pos2 = 1; } { if (start || $4 == "generator") { start = 1;  if ($4 == "generator") { sources[pos] = $6; pos++; } else if ($4 == "links") { print (sources[pos2] + $6) * 1000.0; pos2++ } else if ($4 == "probe") { start = 0; } } }' >> $FAVE_REACH
done

NP_INIT=results/raw_np_init.dat
echo -n "" > $NP_INIT
NP_REACH=results/raw_np_reach.dat
echo -n "" > $NP_REACH

for i in $(seq 1 $RUNS); do
  grep "total" results/$i.raw/$i.np.stdout.log | awk '{ print $4/1000.0; }' >> $NP_INIT
  grep "seconds" results/$i.raw/$i.np.stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_REACH
done

CHECKS=results/raw_checks.dat
echo -n "" > $CHECKS

for i in $(seq 1 $RUNS); do
  RDIR=results/$i.raw
  grep "checked flow in" $RDIR/$i.stdout.log | cut -d' ' -f4 | \
    awk 'BEGIN { result = 0; } { result += $1; } END { print result; }' >> $CHECKS
done

stats fave_init $FAVE_INIT
stats fave_reach $FAVE_REACH
stats np_init $NP_INIT
stats np_reach $NP_REACH
stats checks $CHECKS
