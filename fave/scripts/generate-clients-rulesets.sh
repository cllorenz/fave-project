#!/usr/bin/env bash

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
    welcome-center-potsdam.de \
    wifi.uni-potsdam.de"

cnt=4
for SUB in $SUBNETS; do
    SCRIPT="rulesets/$SUB-clients-ruleset"
    echo -n "" > $SCRIPT

    # preamble
    echo "ip6tables -P INPUT ACCEPT" >> $SCRIPT
    echo "ip6tables -P FORWARD DROP" >> $SCRIPT
    echo "ip6tables -P OUTPUT ACCEPT" >> $SCRIPT

    # handle incoming icmpv6
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $SCRIPT
#   echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $SCRIPT

    cnt=$(($cnt+1))
done
