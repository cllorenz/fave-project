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
RES_PATH=$(pwd)/tum/fffuu6
rm -rf $(pwd)/tum
mkdir -p $RES_PATH/raw

RESULTS=$RES_PATH/results.dat
echo "aspect mean(ms) median(ms) min(ms) max(ms)" > $RESULTS

TUM_TOTAL=$RES_PATH/raw_runtimes.dat

echo -n "" > $TUM_TOTAL

echo -n "run fffuu6:"
for i in $(seq 1 $RUNS); do
    LOG=$RES_PATH/raw/$i.up.log
    echo -n " $i"
    cd fffuu/haskell_tool
    /usr/bin/time -f "%e" -o $i.time \
        cabal run fffuu6 -- \
	    --service_matrix_dport 80 \
	    ../thy/Iptables_Semantics/Examples/UP/ip6tables-save-up > $LOG 2> /dev/null

    grep "^measure" $LOG | \
        grep -v "spoofing" | \
	cut -d ':' -f 2 | \
	tr -d ' s' | \
	awk 'BEGIN { sum = 0.0; } { sum += $1; } END { print sum * 1000.0; }' >> $TUM_TOTAL
     cd ../..
done
echo ""

echo "run fave"
cd fave-code/fave
bash bench/run_benchmarks.sh bench/wl_tum/benchmark.py
bash bench/eval_benchmarks.sh
cd ../..

mv fave-code/fave/results $RES_PATH/../fave
stats "fffuu6" $TUM_TOTAL

grep -v "Checks" $RES_PATH/../fave/results.dat | tail -n+2 >> $RESULTS
mv $RESULTS tum/
