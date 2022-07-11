#!/usr/bin/env bash

RES=$1

AD6_RAW=$RES/ad6_raw.dat
Z3_RAW=$RES/z3_raw.dat
BV_RAW=$RES/bv_raw.dat
NP_RAW=$RES/np_raw.dat

RESULT=$RES/result.dat

echo -n "" > $AD6_RAW
echo -n "" > $Z3_RAW
echo -n "" > $BV_RAW
echo -n "" > $NP_RAW

# analyse ad6
grep "Solving" $RES/ad6/*.stdout.log | cut -f7 >> $AD6_RAW

# analyse z3
grep "Analysis" $RES/z3/*.stdout.log | cut -d' ' -f3 >> $Z3_RAW

# analyse bv
grep "Analysis" $RES/bv/*.stdout.log | cut -d' ' -f3 >> $BV_RAW

# analyse np
grep "Checked anomalies" $RES/np/*.stdout.log | cut -d' ' -f7 >> $NP_RAW

echo -e "tool\tmean\tmedian\tstddev" > $RESULT

for T in ad6:$AD6_RAW Z3:$Z3_RAW BV:$BV_RAW FaVe:$NP_RAW; do
    echo $T

    TOOL=$(echo $T | cut -d: -f1)
    RAW=$(echo $T | cut -d: -f2)

    MEAN=`awk -f bench/mean.awk < $RAW`
    MEDIAN=`awk -f bench/median.awk < $RAW`
    STDDEV=`awk -f bench/stddev.awk -vMEAN=$MEAN < $RAW`

    echo -e "$TOOL\t$MEAN\t$MEDIAN\t$STDDEV" >> $RESULT
done
