#!/usr/bin/env bash

RUNS=10
RESULTS=results/mb_ssnap
mkdir -p $RESULTS
#rm -rf $RESULTS/*

FWOP=$RESULTS/raw_wo_policy.dat
FWIP=$RESULTS/raw_with_policy.dat

echo -n "hz" > $FWOP
echo -n "hz" > $FWIP
for i in $(seq 1 $RUNS); do
	echo -n " ot$i" >> $FWOP
	echo -n " ot$i" >> $FWIP
done
echo "" >> $FWOP
echo "" >> $FWIP

export PYTHONPATH=.
for hz in 1 10 100 200 300 400 500 600 700 800 900 1000; do
	echo -n "$hz"
	echo -n "$hz" >> $FWOP
	echo -n "$hz" >> $FWIP
	for i in $(seq 1 $RUNS); do
		RES=`python2 bench/wl_state_snapshots/benchmark.py -f $hz | cut -d ' ' -f 3`
		echo -n " $RES" >> $FWOP

		RES=`python2 bench/wl_state_snapshots/benchmark.py -p -f $hz | cut -d ' ' -f 3`
		echo -n " $RES"
		echo -n " $RES" >> $FWIP
	done
	echo ""
	echo "" >> $FWOP
	echo "" >> $FWIP
done

