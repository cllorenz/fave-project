#!/usr/bin/env bash

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
