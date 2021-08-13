#!/usr/bin/env bash

RULESET=$1
OFILE=$2

echo "[" > $OFILE
grep -oE '((\-i)|(\-o)|(\-\-in-interface)|(\-\-out-interface))[[:space:]]+[0-9A-Za-z\.]+' $RULESET | \
    cut -d' ' -f2 | \
    cut -d'.' -f1 | \
    sort -u | \
    awk '{ if ( NR == 1 ) { print "\""$1"\""; } else { print ",\""$1"\""; } }' >> $OFILE
echo "]" >> $OFILE
