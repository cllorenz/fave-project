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
## switch $SWITCH
## packet filter $FIREWALL
## generator $HOST1
## generator $HOST2
## probe $PROBE1
## probe $PROBE2
##

SWITCH=sw0
FIREWALL=fw0
HOST1=hs1
HOST2=hs2
PROBE1=hp1
PROBE2=hp2

PYTHONPATH="${PYTHONPATH}:`pwd`/"
export PYTHONPATH

CNT=0

# test topology
echo -n "read topology... "
# $SWITCH
python2 topology/topology.py -a -t switch -n $SWITCH -p 2
CNT=$(( $? + CNT ))
# packet filter $FIREWALL
python2 topology/topology.py -a -t packet_filter -n $FIREWALL -i 2001:db8::3 -p 2
CNT=$(( $? + CNT ))
# links: $SWITCH <-> $FIREWALL
python2 topology/topology.py -a -l $SWITCH.2:$FIREWALL.1,$FIREWALL.3:$SWITCH.2
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add generators... "
# generator $HOST1
python2 topology/topology.py -a -t generator -n $HOST1 -f "ipv6_dst=2001:db8::1"
CNT=$(( $? + CNT ))
# generator $HOST2
python2 topology/topology.py -a -t generator -n $HOST2 -f "ipv6_dst=2001:db8::2;tcp_dst=80"
CNT=$(( $? + CNT ))

#link: $HOST1 --> $FIREWALL
python2 topology/topology.py -a -l $HOST1.1:$FIREWALL.2
CNT=$(( $? + CNT ))
#link: $HOST2 --> $SWITCH
python2 topology/topology.py -a -l $HOST2.1:$SWITCH.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add probess... "
# PROBE1 $PROBE1
python2 topology/topology.py -a -t probe -n $PROBE1 -q universal -P ".*;(table in ($FIREWALL))"
CNT=$(( $? + CNT ))
python2 topology/topology.py -a -t probe -n $PROBE2 -q universal -P ".*;(table in ($FIREWALL))"
CNT=$(( $? + CNT ))

# link: $FIREWALL --> $PROBE1
python2 topology/topology.py -a -l $FIREWALL.4:$PROBE1.1
CNT=$(( $? + CNT ))
# link: $SWITCH --> PROBE2
python2 topology/topology.py -a -l $SWITCH.1:$PROBE2.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

# test firewall
echo -n "add firewall rules... "
#python2 ip6np/ip6np.py -n $FIREWALL -i 2001:db8::3 -f ip6np/iptables_ruleset_reduced.sh
python2 ip6np/ip6np.py -n $FIREWALL -i 2001:db8::3 -p 2 -f rulesets/simple_ruleset.sh
[ $? -eq 0 ] && echo "ok" || echo "fail"
CNT=0

# test rule setting
echo -n "add switch rules... "
python2 openflow/switch.py -a -i 1 -n $SWITCH -t 1 -f ipv6_dst=2001:db8::1 -c fd=$SWITCH.1
CNT=$(( $? + CNT ))
python2 openflow/switch.py -a -i 2 -n $SWITCH -t 1 -f ipv6_dst=2001:db8::2 -c fd=$SWITCH.2
CNT=$(( $? + CNT ))

python2 openflow/switch.py -a -i 1 -n $FIREWALL -f ipv6_dst=2001:db8::2 -c fd=$FIREWALL.2
CNT=$(( $? + CNT ))

python2 openflow/switch.py -a -i 2 -n $FIREWALL -f ipv6_dst=2001:db8::1 -c fd=$FIREWALL.1
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

python2 netplumber/dump_np.py -anpft

python2 netplumber/print_np.py -utn

# test flow propagation
echo -n "check flow propagation... "

F1='s='$HOST1' && EX t='$FIREWALL'_pre_routing && (EX t='$FIREWALL'_forward_states)'
F2='s='$HOST1' && EX t='$FIREWALL'_pre_routing && EF t='$SWITCH'_1 && EX p='$PROBE2
F3='! s='$HOST1' && EF p='$PROBE1
F4='s='$HOST1' && EX t='$FIREWALL'_pre_routing && EX t='$FIREWALL'_forward_states && EX t='$FIREWALL'_forward_rules'

F5='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EF p='$PROBE1
F6='! s='$HOST2' && EF p='$PROBE2
F7='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EX t='$FIREWALL'_forward_states && EX t='$FIREWALL'_forward_rules'
F8='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EX t='$FIREWALL'_forward_states'

python2 test/check_flows.py -c "$F1;$F2;$F3;$F4;$F5;$F6;$F7;$F8"
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

git checkout examples/example.conf

#kill -s KILL $RYU
