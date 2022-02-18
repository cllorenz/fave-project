#!/usr/bin/env bash

RES=$1

RESULT=$RES/result.dat

for fw in fw1 fw2 fw3 fw4 fw5 random; do
    for c in 500 1000 2000; do
        echo -n "" > $RES/$fw"_"$c"_raw.dat"
        echo -n "" > $RES/$fw".dat"
    done
done

for fw in fw1 fw2 fw3 fw4 fw5 random; do
    for c in 500 1000 2000; do
        RAW=$RES/$fw"_"$c"_raw.dat"
        grep "check_anomalies" $RES/$fw/$c/*_fave.log | cut -d' ' -f6 >> $RAW
    done
done

for fw in fw1 fw2 fw3 fw4 fw5 random; do
    FW_RESULT=$RES/result_$fw".dat"
    echo -e "rules\tmean\tmedian\tstddev" > $FW_RESULT
    for c in 500 1000 2000; do
        RAW=$RES/$fw"_"$c"_raw.dat"

        MEAN=`awk -f bench/mean.awk < $RAW`
        MEDIAN=`awk -f bench/median.awk < $RAW`
        STDDEV=`awk -f bench/stddev.awk -vMEAN=$MEAN < $RAW`

        echo -e "$c\t$MEAN\t$MEDIAN\t$STDDEV" >> $FW_RESULT
    done
done
