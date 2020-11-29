#!/usr/bin/env bash

RULESET_IN=$1
SAVE_OUT=$2
echo \
'*raw
:PREROUTING ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
COMMIT
*filter' > $SAVE_OUT

grep "\-P\|\-\-policy" $RULESET_IN | awk '{ print ":"$3" "$4" [0:0]"; }' >> $SAVE_OUT

grep -E "(\-A|\-\-append) (INPUT|OUTPUT|FORWARD)" $RULESET_IN | cut -d' ' -f2- >> $SAVE_OUT

echo 'COMMIT' >> $SAVE_OUT
