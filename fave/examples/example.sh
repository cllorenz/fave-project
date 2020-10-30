#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

rm -rf /tmp/np

TMP=$(mktemp -d -p /tmp "np.XXXXXX")
TMPESC=$(echo $TMP | sed 's/\//\\\//g')
sed -i "s/\/tmp\/np\......./$TMPESC/g" examples/example.conf

echo -n "generate rule set... "

RS=examples/example-ruleset

echo -n "" > $RS
echo "ip6tables -P INPUT DROP" >> $RS
echo "ip6tables -P FORWARD DROP" >> $RS
echo "ip6tables -P OUTPUT DROP" >> $RS

echo "ip6tables -A INPUT -p icmpv6 -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $RS

echo "ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT" >> $RS

echo "ip6tables -A OUTPUT -s 2001:db8::3 -p icmpv6 -j ACCEPT" >> $RS

#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT" >> $RS
#echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT" >> $RS

echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 --rt-segsleft 0 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 --rt-segsleft 1 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt ! --rt-segsleft 0 -j DROP" >> $RS

echo "ip6tables -A FORWARD -d 2001:db8::2 -p tcp --dport 80 -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -d 2001:db8::2 -p udp --dport 80 -j ACCEPT" >> $RS

echo "ok"

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
python2 topology/topology.py -a -t generators -G "$HOST1\ipv6_dst=2001:db8::1|$HOST2\ipv6_dst=2001:db8::2"
CNT=$(( $? + CNT ))

#links: $HOST1 --> $FIREWALL, $HOST2 --> $SWITCH
python2 topology/topology.py -a -l $HOST1.1:$FIREWALL.2,$HOST2.1:$SWITCH.1
CNT=$(( $? + CNT ))

[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add probes... "
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
python2 ip6np/ip6np.py -n $FIREWALL -i 2001:db8::3 -p 2 -f $RS
#python2 ip6np/ip6np.py -n $FIREWALL -i 2001:db8::3 -p 2 -f rulesets/simple_ruleset.sh
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

F1='s='$HOST1' && EX t='$FIREWALL'_pre_routing && (EX t='$FIREWALL'_forward_filter)'
F2='s='$HOST1' && EX t='$FIREWALL'_pre_routing && EF t='$SWITCH'_1 && EX p='$PROBE2
F3='! s='$HOST1' && EF p='$PROBE1

F4='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EF p='$PROBE1
F5='! s='$HOST2' && EF p='$PROBE2
F6='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EX t='$FIREWALL'_forward_filter'

F7='s='$HOST2' && EF p='$PROBE1
F8='s='$HOST1' && EF p='$PROBE2' && f=related:1'
F9='! s='$HOST1' && EF p='$PROBE2' && f=related:0'

python2 test/check_flows.py -b -c "$F1;$F2;$F3;$F4;$F5;$F6;$F7;$F8;$F9"
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

git checkout examples/example.conf 2> /dev/null

#kill -s KILL $RYU
