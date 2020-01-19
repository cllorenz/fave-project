#!/usr/bin/env bash


export PYTHONPATH=$(pwd)

POLICY_HTML_URI=$(pwd)/../policy-translator/examples/ifi-klemens.html
REACH_HTML_URI=$(pwd)/../policy-translator/examples/ifi-klemens-reach.html

read -n1 -r -p "Generate policy matrix from inventory and policy. Press any key to continue..."

python2 ../policy-translator/policy_translator.py \
    --html --out $POLICY_HTML_URI \
    bench/wl_ifi/roles_and_services.orig.txt \
    bench/wl_ifi/policy.orig.txt

firefox --new-window file://$POLICY_HTML_URI 2> /dev/null &

read -n1 -r -p "Calculate reachability with fave and net_plumber. Press any key to continue..."

python2 bench/wl_ifi/benchmark.py -v

read -n1 -r -p "Generate reachability matrix from results. Press any key to continue..."

python2 ../policy-translator/policy_translator.py \
    --html --out $REACH_HTML_URI \
    --report np_dump/reach.csv \
    bench/wl_ifi/roles_and_services.orig.txt \
    bench/wl_ifi/policy.orig.txt

firefox --new-window file://$REACH_HTML_URI 2> /dev/null &
