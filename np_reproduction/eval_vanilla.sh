#!/use/bin/env bash

RUNS=10
BENCH=$1
RESULTS=$2

RDIR=$RESULTS/$BENCH

INIT_RAW=$RDIR/init.raw
echo -n "" > $INIT_RAW
REACH_RAW=$RDIR/reach.raw
echo -n "" > $REACH_RAW
TOTAL_RAW=$RDIR/total.raw
echo -n "" > $TOTAL_RAW

for i in $(seq 1 $RUNS); do
    VANILLA_LOG=$RESULTS/$BENCH/$i.vnp/stdout.log
    INIT_VANILLA=`grep "total run time" $VANILLA_LOG | cut -d' ' -f 5 | awk '{ print $1 / 1000.0; }'`
    echo $INIT_VANILLA >> $INIT_RAW
    REACH_VANILLA=`grep "Loaded policy" $VANILLA_LOG | cut -d' ' -f5 | awk '{ print $1 * 1000.0; }'`
    echo $REACH_VANILLA >> $REACH_RAW
    echo "$INIT_VANILLA $REACH_VANILLA" | awk '{ print $1 + $2; }' >> $TOTAL_RAW
done

RESULTS_VANILLA=$RDIR/results.dat
echo "tool init(ms) reach(ms) total(ms)" > $RESULTS_VANILLA

INIT_MEAN=`awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum / NR; }' $INIT_RAW`
REACH_MEAN=`awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum / NR; }' $REACH_RAW`
TOTAL_MEAN=`awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum / NR; }' $TOTAL_RAW`

echo "Vanilla-NP $INIT_MEAN $REACH_MEAN $TOTAL_MEAN" >> $RESULTS_VANILLA
