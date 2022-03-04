#!/usr/bin/env bash

RES=results_up/np

mkdir -p $RES
rm -rf $RES/*

echo -n "Run NetPlumber..."
for i in {1..10}; do
    echo -n " $i"
    net_plumber --hdr-len 51 --load np_dump --anomalies > $RES/$i.stdout.log 2> $RES/$i.stderr.log
done
echo ""
