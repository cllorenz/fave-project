#!/usr/bin/env bash

for SEED in fw1_seed fw2_seed fw3_seed fw4_seed fw5_seed; do
    for RULES in 500 1000 2000 5000 10000 15000 20000; do
        classbench generate v6 vendor/parameter_files/$SEED --count $RULES > $SEED"_"$RULES".cb"
    done
done
