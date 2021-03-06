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

function public {
    ADDRESS=$1
    PORTS=`echo $2 | tr -s ',' ' '`
    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A INPUT -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}


function private {
#    PRE=$1
#    ADDRESS=$2
    SADDR=$1
    DADDR=$2
    PORTS=`echo $3 | tr -s ',' ' '`

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A INPUT -s $SADDR -d $DADDR -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}


DMZ="file.uni-potsdam.de,2001:db8:abc:1::1,tcp:21,tcp:115;tcp:22 \
    mail.uni-potsdam.de,2001:db8:abc:1::2,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,\
tcp:993,tcp:995;tcp:22 \
    web.uni-potsdam.de,2001:db8:abc:1::3,tcp:80,tcp:443;tcp:22 \
    ldap.uni-potsdam.de,2001:db8:abc:1::4,tcp:389,tcp:636;tcp:22 \
    vpn.uni-potsdam.de,2001:db8:abc:1::5,tcp:1194,tcp:1723;tcp:22 \
    dns.uni-potsdam.de,2001:db8:abc:1::6,tcp:53,udp:53;tcp:22 \
    data.uni-potsdam.de,2001:db8:abc:1::7,;tcp:118,tcp:156,tcp:22 \
    adm.uni-potsdam.de,2001:db8:abc:1::8,;udp:161,tcp:22"
#DMZ="file.uni-potsdam.de,2001:db8:abc:1::1,tcp:21,tcp:115;tcp:22,udp:22 \
#    mail.uni-potsdam.de,2001:db8:abc:1::2,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,\
#tcp:993,tcp:995,udp:143,udp:220;tcp:22,udp:22 \
#    web.uni-potsdam.de,2001:db8:abc:1::3,tcp:80,tcp:443;tcp:22,udp:22 \
#    ldap.uni-potsdam.de,2001:db8:abc:1::4,tcp:389,tcp:636,udp:389,udp:123;tcp:22,udp:22 \
#    vpn.uni-potsdam.de,2001:db8:abc:1::5,tcp:1194,tcp:1723,udp:1194,udp:1723;tcp:22,udp:22 \
#    dns.uni-potsdam.de,2001:db8:abc:1::6,tcp:53,udp:53;tcp:22,udp:22 \
#    data.uni-potsdam.de,2001:db8:abc:1::7,;tcp:118,tcp:156,tcp:22,udp:118,udp:156,udp:22 \
#    adm.uni-potsdam.de,2001:db8:abc:1::8,;udp:161,tcp:22,udp:22"

SUBNETS="api.uni-potsdam.de \
    asta.uni-potsdam.de \
    botanischer-garten-potsdam.de \
    chem.uni-potsdam.de \
    cs.uni-potsdam.de \
    geo.uni-potsdam.de \
    geographie.uni-potsdam.de \
    hgp-potsdam.de \
    hpi.uni-potsdam.de \
    hssport.uni-potsdam.de \
    intern.uni-potsdam.de \
    jura.uni-potsdam.de \
    ling.uni-potsdam.de \
    math.uni-potsdam.de \
    mmz-potsdam.de \
    physik.uni-potsdam.de \
    pogs.uni-potsdam.de \
    psych.uni-potsdam.de \
    sq-brandenburg.de \
    ub.uni-potsdam.de \
    welcome-center-potsdam.de"

SUBHOSTS="web,tcp:80,tcp:443;tcp:22,udp:22 \
    voip,tcp:5060,tcp:5061;tcp:22,udp:22 \
    mail,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995;tcp:22,udp:143,udp:220,udp:22 \
    print,;tcp:631,tcp:22,udp:631,udp:22 \
    file,;tcp:137,tcp:138,tcp:139,tcp:445,tcp:2049,tcp:22,udp:137,udp:138,udp:139,udp:22"


for HOST in $DMZ; do
    H=`echo $HOST | cut -d ',' -f 1`
    A=`echo $HOST | cut -d ',' -f 2`
    PUB=`echo $HOST | cut -d ',' -f 3- | cut -d ';' -f 1`
    PRIV=`echo $HOST | cut -d ',' -f 3- | cut -d ';' -f 2`

    SCRIPT="$1/rulesets/dmz-$H-ruleset"
    echo -n "" > $SCRIPT

    # preamble
    echo "ip6tables -P INPUT DROP" >> $SCRIPT
    echo "ip6tables -P FORWARD DROP" >> $SCRIPT
    echo "ip6tables -P OUTPUT ACCEPT" >> $SCRIPT

    # handle incoming icmpv6
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $SCRIPT

    # handle established connections
    echo "ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $SCRIPT

    # accept traffic for public services
    for PORT in $PUB; do
        public $A $PORT
    done

    # accept traffic for private services
    for PORT in $PRIV; do
        private 2001:db8:abc::0/48 $A $PORT
    done
done

cnt=4
for SUB in $SUBNETS; do
    srv=1
    for HOST in $SUBHOSTS; do
        H=`echo $HOST | cut -d ',' -f 1`
        hcnt=`printf %x $cnt`
        A="2001:db8:abc:$hcnt::$srv"
        PUB=`echo $HOST | cut -d ',' -f 2- | cut -d ';' -f 1`
        PRIV=`echo $HOST | cut -d ',' -f 2- | cut -d ';' -f 2`

        SCRIPT="$1/rulesets/$SUB-$H-ruleset"
        echo -n "" > $SCRIPT

        # preamble
        echo "ip6tables -P INPUT DROP" >> $SCRIPT
        echo "ip6tables -P FORWARD DROP" >> $SCRIPT
        echo "ip6tables -P OUTPUT DROP" >> $SCRIPT


        # handle established connections
        echo "ip6tables -A OUTPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $SCRIPT

        # allow access to the dns server
        echo "ip6tables -A OUTPUT -d 2001:db8:abc:1::6 -p tcp --dport 53 -j ACCEPT" >> $SCRIPT

        # deny access to dmz hosts
        echo "ip6tables -A OUTPUT -d 2001:db8:abc:1::0/64 -j DROP" >> $SCRIPT


        # handle established connections
        echo "ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT" >> $SCRIPT

        # handle incoming icmpv6
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $SCRIPT
        echo "ip6tables -A INPUT -s 2001:db8:abc:$hcnt::100/120 -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $SCRIPT

        # deny access from dmz hosts
        echo "ip6tables -A INPUT -s 2001:db8:abc:1::0/64 -j DROP" >> $SCRIPT

        # accept traffic for public services
        for PORT in $PUB; do
            public $A $PORT
        done

        # accept traffic for private services
        for PORT in $PRIV; do
            private 2001:db8:abc:$hcnt::100/120 $A $PORT
        done

        srv=$(($srv+1))
    done
    cnt=$(($cnt+1))
done
