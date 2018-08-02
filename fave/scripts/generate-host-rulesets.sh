#!/usr/bin/env bash

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
    PRE=$1
    ADDRESS=$2
    PORTS=`echo $3 | tr -s ',' ' '`

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A INPUT ! -s $PRE -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}

HOSTS="file,2001:db8:abc:0::1,tcp:21,tcp:115;tcp:22,udp:22 \
    mail,2001:db8:abc:0::2,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,\
tcp:993,tcp:995,udp:143,udp:220;tcp:22,udp:22 \
    web,2001:db8:abc:0::3,tcp:80,tcp:443;tcp:22,udp:22 \
    ldap,2001:db8:abc:0::4,tcp:389,tcp:636,udp:389,udp:123;tcp:22,udp:22 \
    vpn,2001:db8:abc:0::5,tcp:1194,tcp:1723,udp:1194,udp:1723;tcp:22,udp:22 \
    dns,2001:db8:abc:0::6,tcp:53,udp:53;tcp:22,udp:22 \
    data,2001:db8:abc:0::7,;tcp:118,tcp:156,tcp:22,udp:118,udp:156,udp:22 \
    adm,2001:db8:abc:0::8,;udp:161,tcp:22,udp:22"

SUBNETS="api \
    asta \
    botanischer-garten-potsdam.de \
    chem \
    cs \
    geo \
    geographie \
    hgp-potsdam.de \
    hpi \
    hssport \
    intern \
    jura \
    ling \
    math \
    mmz-potsdam.de \
    physik \
    pogs \
    psych \
    sq-brandenburg.de \
    ub \
    welcome-center-potsdam.de"

SUBHOSTS="web,tcp:80,tcp:443;tcp:22,udp:22 \
    voip,tcp:5060,tcp:5061,udp:5060;tcp:22,udp:22 \
    print,;tcp:631,tcp:22,udp:631,udp:22 \
    mail,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995;tcp:22,\
udp:143,udp:220,udp:22 \
    file,;tcp:137,tcp:138,tcp:139,tcp:445,tcp:2049,tcp:22,udp:137,udp:138,udp:139,udp:22"



for HOST in $HOSTS; do
    H="`echo $HOST | cut -d ',' -f 1`.dmz"
    A=`echo $HOST | cut -d ',' -f 2`
    PUB=`echo $HOST | cut -d ',' -f 3- | cut -d ';' -f 1`
    PRIV=`echo $HOST | cut -d ',' -f 3- | cut -d ';' -f 2`

    SCRIPT="rulesets/$H-ruleset"
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

    # accept traffic for public services
    for PORT in $PUB; do
        public $A $PORT
    done

    # accept traffic for private services
    for PORT in $PRIV; do
        private 2001:db8:abc::0/80 $A $PORT
    done
done

cnt=4
for SUB in $SUBNETS; do
    srv=1
    for HOST in $SUBHOSTS; do
        H=`echo $HOST | cut -d ',' -f 1`
        A="2001:db8:abc:$cnt::$srv"
        PUB=`echo $HOST | cut -d ',' -f 2- | cut -d ';' -f 1`
        PRIV=`echo $HOST | cut -d ',' -f 2- | cut -d ';' -f 2`

        SCRIPT="rulesets/$SUB-$H-ruleset"
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

        # accept traffic for public services
        for PORT in $PUB; do
            public $A $PORT
        done

        # accept traffic for private services
        for PORT in $PRIV; do
            private 2001:db8:abc::0/80 $A $PORT
        done

        srv=$(($srv+1))
    done
    cnt=$(($cnt+1))
done
