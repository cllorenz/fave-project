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
    SCRIPT="$1/rulesets/$SUB-clients-ruleset"
    echo -n "" > $SCRIPT

    # preamble
    echo "ip6tables -P INPUT DROP" >> $SCRIPT
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
