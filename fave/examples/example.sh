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

ROOTDIR=$(pwd)

rm -rf /dev/shm/np
rm -f /dev/shm/*.socket

TMP=$(mktemp -d -p /tmp "np.XXXXXX")
TMPESC=$(echo $TMP | sed 's/\//\\\//g')
sed -i "s/\/tmp\/np\......./$TMPESC/g" $ROOTDIR/examples/example.conf

echo -n "generate rule set... "

RS=$ROOTDIR/examples/example-ruleset

echo -n "" > $RS
echo "ip6tables -P INPUT DROP" >> $RS
echo "ip6tables -P FORWARD DROP" >> $RS
echo "ip6tables -P OUTPUT DROP" >> $RS


echo "ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $RS

echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $RS
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $RS

echo "ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT" >> $RS


echo "ip6tables -A OUTPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $RS

echo "ip6tables -A OUTPUT -p icmpv6 -j ACCEPT" >> $RS


echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 --rt-segsleft 0 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 --rt-segsleft 1 -j DROP" >> $RS
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt ! --rt-segsleft 0 -j DROP" >> $RS

echo "ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $RS

echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT" >> $RS

echo "ip6tables -A FORWARD -d 2001:db8::2 -p tcp --dport 80 -j ACCEPT" >> $RS
echo "ip6tables -A FORWARD -d 2001:db8::2 -p udp --dport 80 -j ACCEPT" >> $RS

echo "ok"

export PYTHONPATH="$ROOTDIR:${PYTHONPATH}"

echo -n "start netplumber... "
bash $ROOTDIR/scripts/start_np.sh -l $ROOTDIR/examples/example.conf
[ $? -eq 0 ] && echo "ok" || echo "fail"

sleep 1

echo -n "start aggregator... "
bash $ROOTDIR/scripts/start_aggr.sh -a
[ $? -eq 0 ] && echo "ok" || echo "fail"

##
## switch $SWITCH
## packet filter $FIREWALL
## firewall generator $FWSOURCE
## firewall probe $FWPROBE
## generator $HOST1
## generator $HOST2
## probe $PROBE1
## probe $PROBE2
##

SWITCH=sw0
FIREWALL=fw0
FWSOURCE=fs
FWPROBE=fp
HOST1=hs1
HOST2=hs2
PROBE1=hp1
PROBE2=hp2


CNT=0

# test topology
echo -n "read topology... "
# $SWITCH
python2 $ROOTDIR/topology/topology.py -a -t switch -n $SWITCH -p 2
CNT=$(( $? + CNT ))
# packet filter $FIREWALL
python2 $ROOTDIR/topology/topology.py -a -t packet_filter -n $FIREWALL -i 2001:db8::3 -p "['eth0','eth1']" -r $RS
CNT=$(( $? + CNT ))
# links: $SWITCH <-> $FIREWALL
python2 $ROOTDIR/topology/topology.py -a -l $SWITCH.2:$FIREWALL.eth0:False,$FIREWALL.eth0:$SWITCH.2:False
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add generators... "
# generators $HOST1 $HOST2 $FWSOURCE
python2 $ROOTDIR/topology/topology.py -a -t generators -G "$HOST1\ipv6_src=2001:db8::2|$HOST2\ipv6_src=2001:db8::1|$FWSOURCE\ipv6_src=2001:db8::3"
CNT=$(( $? + CNT ))

#links: $HOST1 --> $FIREWALL, $HOST2 --> $SWITCH, $FWSOURCE -> $FIREWALL
python2 $ROOTDIR/topology/topology.py -a -l $HOST1.1:$FIREWALL.eth1:True,$HOST2.1:$SWITCH.1:True,$FWSOURCE.1:$FIREWALL".output_filter_in":True
CNT=$(( $? + CNT ))

[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

echo -n "add probes... "
# PROBE1 $PROBE1
python2 $ROOTDIR/topology/topology.py -a -t probe -n $PROBE1 -q universal -P ".*;(table in ($FIREWALL))"
CNT=$(( $? + CNT ))
# PROBE2 $PROBE2
python2 $ROOTDIR/topology/topology.py -a -t probe -n $PROBE2 -q universal -P ".*;(table in ($FIREWALL))"
CNT=$(( $? + CNT ))
# FIREWALL $FWPROBE
python2 $ROOTDIR/topology/topology.py -a -t probe -n $FWPROBE -q universal -P ".*;(table in ($FIREWALL))"

# link: $FIREWALL --> $PROBE1
python2 $ROOTDIR/topology/topology.py -a -l $FIREWALL.eth1:$PROBE1.1:False
CNT=$(( $? + CNT ))
# link: $SWITCH --> PROBE2
python2 $ROOTDIR/topology/topology.py -a -l $SWITCH.1:$PROBE2.1:False
CNT=$(( $? + CNT ))
# link: $FW INPUT --> PROBE2
python2 $ROOTDIR/topology/topology.py -a -l $FIREWALL".input_filter_accept":$FWPROBE.1:False
CNT=$(( $? + CNT ))
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

# test rule setting
echo -n "add switch rules... "
python2 $ROOTDIR/devices/switch.py -a -i 1 -n $SWITCH -t 1 -f ipv6_dst=2001:db8::1 -c fd=$SWITCH.1
CNT=$(( $? + CNT ))
python2 $ROOTDIR/devices/switch.py -a -i 2 -n $SWITCH -t 1 -f ipv6_dst=2001:db8::2 -c fd=$SWITCH.2
CNT=$(( $? + CNT ))
python2 $ROOTDIR/devices/switch.py -a -i 3 -n $SWITCH -t 1 -f ipv6_dst=2001:db8::3 -c fd=$SWITCH.2
CNT=$(( $? + CNT ))

python2 $ROOTDIR/devices/switch.py -a -i 1 -n $FIREWALL -f ipv6_dst=2001:db8::2 -c fd=$FIREWALL.eth1
CNT=$(( $? + CNT ))

python2 $ROOTDIR/devices/switch.py -a -i 2 -n $FIREWALL -f ipv6_dst=2001:db8::1 -c fd=$FIREWALL.eth0
[ $(( $? + CNT )) -eq 0 ] && echo "ok" || echo "fail"
CNT=0

python2 $ROOTDIR/netplumber/dump_np.py -anpft

# test flow propagation
echo -n "check flow propagation... "

F1='s='$HOST1' && EX t='$FIREWALL'.pre_routing && (EX t='$FIREWALL'.forward_filter)'
F2='s='$HOST1' && EX t='$FIREWALL'.pre_routing && EF t='$SWITCH'_1 && EX p='$PROBE2
F3='! s='$HOST1' && EF p='$PROBE1

F4='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EF p='$PROBE1
F5='! s='$HOST2' && EF p='$PROBE2
F6='s='$HOST2' && EX t='$SWITCH'_1 && EX t='$FIREWALL'_pre_routing && EX t='$FIREWALL'.forward_filter'

F7='s='$HOST2' && EF p='$PROBE1
F8='s='$HOST1' && EF p='$PROBE2' && f=related:1'
F9='! s='$HOST1' && EF p='$PROBE2' && f=related:0'

F10='s='$HOST1' && EF p='$FWPROBE
F11='s='$HOST2' && EF p='$FWPROBE
F12='s='$FWSOURCE' && EF p='$PROBE1' && f=related:1'
F13='s='$FWSOURCE' && EF p='$PROBE2' && f=related:1'

python2 $ROOTDIR/test/check_flows.py -b -c "$F1;$F2;$F3;$F4;$F5;$F6;$F7;$F8;$F9;$F10;$F11;$F12;$F13"
[ $? -eq 0 ] && echo "all example flow tests ok" || echo "some example flow tests failed"

# test openflow
#echo -n "start ryu... "
#ryu-manager --ofp-tcp-listen-port 6653 ryu.app.simple_switch_13.py &
#RYU=$!
#echo "ok"

#echo "start openflow proxy..."
#PYTHONPATH=. python2 openflow/ofproxy.py

bash $ROOTDIR/scripts/stop_fave.sh

rm -rf $TMP

git checkout $ROOTDIR/examples/example.conf 2> /dev/null

#kill -s KILL $RYU
