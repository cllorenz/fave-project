#!/usr/bin/env bash

TMP=/tmp/pylint.log

# to be ignored (generated code):
IGNORE="\
ip6np/ip6tables_lexer.py \
ip6np/ip6tables_listener.py \
ip6np/ip6tables_parser.py \
test/antlr/ip6tables_lexer.py \
test/antlr/ip6tables_lexer.py \
test/antlr/ip6tables_listener.py \
test/antlr/ip6tables_parser.py \
test/antlr/parser.py \
test/antlr/test.py \
examples/example-traverse.py
"

#PYFILES=`find . -name "*.py"`
PYFILES="\
test/test_rpc.py \
netplumber/jsonrpc.py \
__init__.py \
test/test_netplumber.py \
netplumber/mapping.py \
netplumber/vector.py \
netplumber/model.py \
test/test_tree.py \
ip6np/tree.py \
test/test_topology.py \
topology/topology.py \
test/unit_tests.py \
test/test_utils.py \
util/print_util.py \
util/path_util.py \
util/packet_util.py \
util/match_util.py \
util/json_util.py \
util/collections_util.py \
aggregator/aggregator_mock.py \
aggregator/stop.py \
netplumber/dump_np.py \
netplumber/print_np.py
"

#./aggregator/aggregator.py
#./ip6np/generator.py
#./ip6np/parser.py
#./ip6np/ip6np.py
#./ip6np/ip6tables_custom_listener.py
#./ip6np/packet_filter.py
#./openflow/ofproxy.py
#./openflow/switch.py
#./test/check_flows.py
#./topology/generator.py
#./topology/host.py
#./topology/probe.py
#./wl-ad6-full.py

for PYFILE in $PYFILES; do
    echo -n "lint $PYFILE: "

    if [[ $IGNORE =~ $(echo "./$PYFILE" | cut -d/ -f2-) ]]; then
        echo "skip"
        continue
    fi

    PYTHONPATH=. pylint $PYFILE > $TMP 2>&1
    [ $? -eq 0 ] && echo "ok" || ( echo "fail" && cat $TMP )

done

[ -f $TMP ] && rm $TMP
