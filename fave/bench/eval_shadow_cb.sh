#!/usr/bin/env bash

RES=$1

RULESETS="fw1 fw2 fw3 fw4 fw5 random"
RULES="500 1000 2000 5000 10000 15000"

for fw in $RULESETS; do
    for c in $RULES; do
        echo -n "" > $RES/$fw"_"$c"_raw.dat"
        echo -n "" > $RES/$fw".dat"
    done
done

for fw in $RULESETS; do
    for c in $RULES; do
        RAW=$RES/$fw"_"$c"_raw.dat"
        grep "check_anomalies" $RES/$fw/$c/*_fave.log | cut -d' ' -f6 >> $RAW
    done
done

for fw in $RULESETS; do
    FW_RESULT=$RES/$fw".dat"
    echo -e "rules\tmean\tmedian\tstddev" > $FW_RESULT
    for c in $RULES; do
        RAW=$RES/$fw"_"$c"_raw.dat"

        MEAN=`awk -f bench/mean.awk < $RAW`
        MEDIAN=`awk -f bench/median.awk < $RAW`
        STDDEV=`awk -f bench/stddev.awk -vMEAN=$MEAN < $RAW`

        echo -e "$c\t$MEAN\t$MEDIAN\t$STDDEV" >> $FW_RESULT
    done
done
