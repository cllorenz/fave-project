#!/usr/bin/env bash

TMPDIR=/tmp/np
mkdir -p $TMPDIR

echo -n "clean log files... "
rm -f $TMPDIR/*.log
echo "ok"

echo -n "start netplumber... "
scripts/start_np.sh example.conf
echo "ok"

echo -n "start aggregator... "
scripts/start_aggr.sh
echo "ok"

##
## switch foo
## packet filter bar
## generator baz
## generator boz
## probe bla
##

# test topology
echo -n "read topology"
PYTHONPATH=. python2 topology/topology.py -a -t switch -n foo -p 2
PYTHONPATH=. python2 topology/topology.py -a -t packet_filter -n bar -i 2001:db8::3 -p 2
echo -n ", links (foo<->bar)... "
PYTHONPATH=. python2 topology/topology.py -a -l foo.2:bar.1,bar.3:foo.2
echo "ok"

echo -n "add hosts... generator"
PYTHONPATH=. python2 topology/topology.py -a -t generator -n baz -f "ipv6_dst=2001:db8::1"
echo -n ", generator"
PYTHONPATH=. python2 topology/topology.py -a -t generator -n boz -f "ipv6_dst=2001:db8::2;tcp_dst=80"

echo -n ", link (baz-->bar)"
PYTHONPATH=. python2 topology/topology.py -a -l baz.1:bar.2
echo -n ", link (boz-->foo)"
PYTHONPATH=. python2 topology/topology.py -a -l boz.1:foo.1

echo -n ", probe"
PYTHONPATH=. python2 topology/topology.py -a -t probe -n bla -q universal -P ".*(table=bar)"

echo -n ", link (bar-->bla)... "
PYTHONPATH=. python2 topology/topology.py -a -l bar.4:bla.1
echo "ok"

# test firewall
echo -n "add firewall rules... "
#PYTHONPATH=. python2 ip6np/ip6np.py -n bar -i 2001:db8::3 -f ip6np/iptables_ruleset_reduced.sh
PYTHONPATH=. python2 ip6np/ip6np.py -n bar -i 2001:db8::3 -f simple_ruleset.sh
echo "ok"

# test rule setting
echo -n "add switch rules... "
PYTHONPATH=. python2 openflow/switch.py -a -i 1 -n foo -t 1 -f ipv6_dst=2001:db8::1 -c fd=foo.1
PYTHONPATH=. python2 openflow/switch.py -a -i 2 -n foo -t 1 -f ipv6_dst=2001:db8::2 -c fd=foo.2

PYTHONPATH=. python2 openflow/switch.py -a -i 1 -n bar -f ipv6_dst=2001:db8::2 -c fd=bar.2
PYTHONPATH=. python2 openflow/switch.py -a -i 2 -n bar -f ipv6_dst=2001:db8::1 -c fd=bar.1
echo "ok"


PYTHONPATH=. python2 netplumber/print_np.py -t
PYTHONPATH=. python2 netplumber/print_np.py -n


# test openflow
#echo -n "start ryu... "
#ryu-manager --ofp-tcp-listen-port 6653 ryu.app.simple_switch_13.py &
#RYU=$!
#echo "ok"

#echo "start openflow proxy..."
#PYTHONPATH=. python2 openflow/ofproxy.py

scripts/stop_aggr.sh
scripts/stop_np.sh

#kill -s KILL $RYU
