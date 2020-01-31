#!/usr/bin/env bash

export PYTHONPATH=.
while read line; do
    if [[ $line =~ ^\@.* ]]; then
        python2 scripts/rule_print.py np_dump/fave.json <(echo "$line")
    else
        python2 scripts/hs_print.py np_dump/fave.json <(echo "$line")
    fi
done <$1
