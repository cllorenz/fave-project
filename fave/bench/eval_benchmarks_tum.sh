#!/usr/bin/env bash

function stats {
  ASPECT=$1
  DATA=$2

  MEAN=`awk 'BEGIN { total = 0; } { total += $1; } END { print total/NR; }' < $DATA`

  MEDIAN=`sort -n $DATA | awk '{ count[NR] = $1; } END { if (NR % 2) { print count[(NR + 1) / 2]; } else { print (count[NR / 2]); } }'`

  MIN=`awk 'BEGIN { min = "inf"; } { if ( $1 < min ) { min = $1; } } END { print min; }' < $DATA`

  MAX=`awk 'BEGIN { max = 0.0; } {if ( $1 > max) { max = $1; } } END { print max; }' < $DATA`

  echo "$ASPECT $MEAN $MEDIAN $MIN $MAX" >> $RESULTS
}

RUNS=10

RESULTS=results/results.dat
echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

FAVE_RAW=results/raw_fave.dat
echo "" > $FAVE_RAW

for i in $(seq 1 $RUNS); do
  grep "seconds" results/$i.raw/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN { result = 0; } { result += $6; } END { print result * 1000.0; }' >> $FAVE_RAW
done

NP_RAW=results/raw_np.dat
echo -n "" > $NP_RAW

for i in $(seq 1 $RUNS); do
  grep "total" results/$i.raw/$i.np.stdout.log | awk '{ print $4/1000.0; }' >> $NP_RAW
  grep "seconds" results/$i.raw/$i.np.stdout.log | tr -d '()us' | awk '{ print $7/1000.0; }' >> $NP_RAW
done

stats FaVe $FAVE_RAW
stats NP $NP_RAW
