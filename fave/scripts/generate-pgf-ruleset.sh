#!/usr/bin/env bash

function public {
    ADDRESS=$1
    PORTS=`echo $2 | tr -s ',' ' '`
    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A FORWARD -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}

function private {
    ADDRESS=$1
    PORTS=`echo $2 | tr -s ',' ' '`

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A FORWARD -s 2001:db8:abc::0/48 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}

function private_sub {
    IF=$1
    ADDRESS=$2
    PORTS=`echo $3 | tr -s ',' ' '`

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        echo "ip6tables -A FORWARD -s 2001:db8:abc::0/48 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done
}


SCRIPT="$1/rulesets/pgf.uni-potsdam.de-ruleset"
echo -n "" > $SCRIPT


SUBNETS="2001:db8:abc:4::0/64 \
    2001:db8:abc:5::0/64 \
    2001:db8:abc:6::0/64 \
    2001:db8:abc:7::0/64 \
    2001:db8:abc:8::0/64 \
    2001:db8:abc:9::0/64 \
    2001:db8:abc:a::0/64 \
    2001:db8:abc:b::0/64 \
    2001:db8:abc:c::0/64 \
    2001:db8:abc:d::0/64 \
    2001:db8:abc:e::0/64 \
    2001:db8:abc:f::0/64 \
    2001:db8:abc:10::0/64 \
    2001:db8:abc:11::0/64 \
    2001:db8:abc:12::0/64 \
    2001:db8:abc:13::0/64 \
    2001:db8:abc:14::0/64 \
    2001:db8:abc:15::0/64 \
    2001:db8:abc:16::0/64 \
    2001:db8:abc:17::0/64 \
    2001:db8:abc:18::0/64"


# preamble
echo "ip6tables -P INPUT DROP" >> $SCRIPT
echo "ip6tables -P FORWARD DROP" >> $SCRIPT
echo "ip6tables -P OUTPUT DROP" >> $SCRIPT

# deny access on the firewall from the internet
echo "ip6tables -A INPUT -i 1 -j DROP" >> $SCRIPT

# handle incoming icmpv6
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT" >> $SCRIPT
echo "ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT" >> $SCRIPT

# accept ssh access from internal hosts
echo "ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT" >> $SCRIPT

# allow dns for the pgf
echo "ip6tables -A OUTPUT -d 2001:db8:abc:1::6 -p udp --dport 53 -j ACCEPT" >> $SCRIPT



# deny internal traffic originating from the internet (prevents spoofing)
echo "ip6tables -A FORWARD -i 1 -s 2001:db8:abc::0/48 -j DROP" >> $SCRIPT

# allow outgoing flows
#echo "ip6tables -A FORWARD -o 1 -s 2001:db8:abc::0/48 -j ACCEPT" >> $SCRIPT

# handle forwarding of icmpv6
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT" >> $SCRIPT

echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP" >> $SCRIPT
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP" >> $SCRIPT
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 --rt-segsleft 0 -j DROP" >> $SCRIPT
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 --rt-segsleft 1 -j DROP" >> $SCRIPT
echo "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt ! --rt-segsleft 0 -j DROP" >> $SCRIPT

# allow access to dmz services
public 2001:db8:abc:1::1 tcp:21,tcp:115
private 2001:db8:abc:1::1 tcp:22,udp:22

public 2001:db8:abc:1::2 \
    tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995,udp:143,udp:220
private 2001:db8:abc:1::2 tcp:22,udp:22

public 2001:db8:abc:1::3 tcp:80,tcp:443
private 2001:db8:abc:1::3 tcp:22,udp:22

public 2001:db8:abc:1::4 tcp:389,tcp:636,udp:389,udp:123
private 2001:db8:abc:1::4 tcp:22,udp:22

public 2001:db8:abc:1::5 tcp:1194,tcp:1723,udp:1194,udp:1723
private 2001:db8:abc:1::5 tcp:22,udp:22

public 2001:db8:abc:1::6 tcp:53,udp:53
private 2001:db8:abc:1::6 tcp:22,udp:22

private 2001:db8:abc:1::7 tcp:118,tcp:156,tcp:22,udp:118,udp:156,udp:22

private 2001:db8:abc:1::8 udp:161,tcp:22,udp:22


# restrict wifi to public communication (internet and public servers)
#echo "ip6tables -A FORWARD ! -i 1 -s 2001:db8:abc:2::1/64 -j DROP" >> $SCRIPT

# wifi -> internet
echo "ip6tables -A FORWARD -s 2001:db8:abc:2::0/64 -o 1 -p tcp -j ACCEPT" >> $SCRIPT
echo "ip6tables -A FORWARD -s 2001:db8:abc:2::0/64 -o 1 -j ACCEPT" >> $SCRIPT

# allow access to public subdomain services and restrict usage of private
# services to host in the respective subnet
cnt=4
for SUB in $SUBNETS; do
    PREFIX=`echo $SUB | sed -e 's/::/;/g' | cut -d ';' -f 1`

    # web
    public $PREFIX::1 tcp:80,tcp:443
    private_sub $cnt $PREFIX::1 tcp:22,udp:22

    # voip
    public $PREFIX::2 tcp:5060,tcp:5061,udp:5060
    private_sub $cnt $PREFIX::2 tcp:22,udp:22

    # print
    private_sub $cnt $PREFIX::3 tcp:631,tcp:22,udp:631,udp:22

    # mail
    public $PREFIX::4 \
      tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995,udp:143,udp:220
    private_sub $cnt $PREFIX::4 tcp:22,udp:22

    # file
    private_sub $cnt $PREFIX::5 \
      tcp:137,tcp:138,tcp:139,tcp:445,tcp:2049,tcp:22,udp:137,udp:138,udp:139,udp:22

    cnt=$(($cnt+1))
done


