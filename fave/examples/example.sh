#!/usr/bin/env bash

TMP=$(mktemp -d -p /tmp "np.XXXXXX")
TMPESC=$(echo $TMP | sed 's/\//\\\//g')
sed -i "s/\/tmp\/np\......./$TMPESC/g" examples/example.conf

echo -n "start netplumber... "
scripts/start_np.sh examples/example.conf
[ $? -eq 0 ] && echo "ok" || echo "fail"

echo -n "start aggregator... "
scripts/start_aggr.sh
[ $? -eq 0 ] && echo "ok" || echo "fail"

##
## switch foo
## packet filter bar
## generator baz
## generator boz
## probe bla
##

PYTHONPATH="${PYTHONPATH}:`pwd`/"
export PYTHONPATH

CNT=0

# test topology
echo -n "read topology... "
# switch foo
python2 topology/topology.py -a -t switch -n foo -p 2
CNT=$(( $? + CNT ))
# packet filter bar
python2 topology/topology.py -a -t packet_filter -n bar -i 2001:db8::3 -p 2
CNT=$(( $? + CNT ))
# links: foo<->bar
python2 topology/topology.py -a -l foo.2:bar.1,bar.3:foo.2
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add generators... "
# generator baz
python2 topology/topology.py -a -t generator -n baz -f "ipv6_dst=2001:db8::1"
CNT=$(( $? + CNT ))
# generator boz
python2 topology/topology.py -a -t generator -n boz -f "ipv6_dst=2001:db8::2;tcp_dst=80"
CNT=$(( $? + CNT ))

#link: baz-->bar
python2 topology/topology.py -a -l baz.1:bar.2
CNT=$(( $? + CNT ))
#link: boz-->foo
python2 topology/topology.py -a -l boz.1:foo.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add probes... "
# probe bla
python2 topology/topology.py -a -t probe -n bla -q universal -P ".*;(table in (bar))"
CNT=$(( $? + CNT ))
python2 topology/topology.py -a -t probe -n blubb -q universal -P ".*;(table in (bar))"
CNT=$(( $? + CNT ))

# link: bar-->bla
python2 topology/topology.py -a -l bar.4:bla.1
CNT=$(( $? + CNT ))
# link: foo-->blubb
python2 topology/topology.py -a -l foo.1:blubb.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

# test firewall
echo -n "add firewall rules... "
#python2 ip6np/ip6np.py -n bar -i 2001:db8::3 -f ip6np/iptables_ruleset_reduced.sh
python2 ip6np/ip6np.py -n bar -i 2001:db8::3 -f rulesets/simple_ruleset.sh
[ $? -eq 0 ] && echo "ok" || echo "fail"
CNT=0

# test rule setting
echo -n "add switch rules... "
python2 openflow/switch.py -a -i 1 -n foo -t 1 -f ipv6_dst=2001:db8::1 -c fd=foo.1
CNT=$(( $? + CNT ))
python2 openflow/switch.py -a -i 2 -n foo -t 1 -f ipv6_dst=2001:db8::2 -c fd=foo.2
CNT=$(( $? + CNT ))

python2 openflow/switch.py -a -i 1 -n bar -f ipv6_dst=2001:db8::2 -c fd=bar.2
CNT=$(( $? + CNT ))

python2 openflow/switch.py -a -i 2 -n bar -f ipv6_dst=2001:db8::1 -c fd=bar.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

python2 netplumber/dump_np.py -anpft

python2 netplumber/print_np.py -utn

# test flow propagation
echo -n "check flow propagation... "

#[ 1, 34359738372, 30064771074 ],
#[ 1, 34359738372, 30064771073, 38654705665, 8589934594, 4294967297, 4 ],
#[ 1, 34359738372, 30064771073, 38654705666, 8589934593, 3 ],
#[ 1, 34359738372, 30064771073, 38654705667 ],
F1='s=baz && EX t=bar_pre_routing && (EX t=bar_forward_states)'
F2='s=baz && EX t=bar_pre_routing && EF t=foo_1 && EX p=blubb'
F3='s=baz && EX t=bar_pre_routing && EF p=bla'
F4='s=baz && EX t=bar_pre_routing && EX t=bar_forward_states && EX t=bar_forward_rules'

#[ 2, 4294967298, 34359738371, 30064771073, 38654705665, 8589934594, 4294967297, 4 ],
#[ 2, 4294967298, 34359738371, 30064771073, 38654705667 ],
#[ 2, 4294967298, 34359738371, 30064771074 ]
F5='s=boz && EX t=foo_1 && EX t=bar_pre_routing && EF t=foo_1 && EX p=blubb'
F6='s=boz && EX t=foo_1 && EX t=bar_pre_routing && EX t=bar_forward_states && EX t=bar_forward_rules'
F7='s=boz && EX t=foo_1 && EX t=bar_pre_routing && EX t=bar_forward_states'

python2 test/check_flows.py -c "$F1;$F2;$F3;$F4;$F5;$F6;$F7"
[ $? -eq 0 ] && echo "all example flow tests ok" || echo "some example flow tests failed"

# test openflow
#echo -n "start ryu... "
#ryu-manager --ofp-tcp-listen-port 6653 ryu.app.simple_switch_13.py &
#RYU=$!
#echo "ok"

#echo "start openflow proxy..."
#PYTHONPATH=. python2 openflow/ofproxy.py

bash scripts/stop_fave.sh

rm -rf $TMP

#kill -s KILL $RYU
