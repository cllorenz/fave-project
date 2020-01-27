#!/usr/bin/env bash

function private_dmz {
    ADDRESS=$1
    PORTS=`echo $2 | tr -s ',' ' '`
    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        # allow access from the wifi
        echo "ip6tables -A FORWARD -s 2001:db8:abc:2::0/64 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT

        # allow access from the subnet clients
        for i in 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18; do
            echo "ip6tables -A FORWARD -s 2001:db8:abc:$i::100/120 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
        done
    done

    # allow ssh access from the admin console
    echo "ip6tables -A FORWARD -s 2001:db8:abc:1::8 -d $ADDRESS -p tcp --dport 22 -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A FORWARD -s 2001:db8:abc:1::8 -d $ADDRESS -p udp --dport 22 -j ACCEPT" >> $SCRIPT
}


function public_dmz {
    ADDRESS=$1
    PORTS=`echo $2 | tr -s ',' ' '`
    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        # allow access from the internet
        echo "ip6tables -A FORWARD -i 1 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done

    # allow access to the internet
    echo "ip6tables -A FORWARD -o 1 -s $ADDRESS -j ACCEPT" >> $SCRIPT

    private_dmz $1 $2
}


function private_sub {
    PREFIX=$1
    POSTFIX=$2
    PORTS=`echo $3 | tr -s ',' ' '`

    ADDRESS=$PREFIX::$POSTFIX

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        # allow access from the subnet clients
        echo "ip6tables -A FORWARD -s $PREFIX::100/120 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
    done

    # allow ssh access from the subnet clients
    echo "ip6tables -A FORWARD -s $PREFIX::100/120 -d $ADDRESS -p tcp --dport 22 -j ACCEPT" >> $SCRIPT
    echo "ip6tables -A FORWARD -s $PREFIX::100/120 -d $ADDRESS -p udp --dport 22 -j ACCEPT" >> $SCRIPT
}

function public_sub {
    PREFIX=$1
    POSTFIX=$2
    PORTS=`echo $3 | tr -s ',' ' '`

    ADDRESS=$PREFIX::$POSTFIX

    for PORT in $PORTS; do
        PROTO=`echo $PORT | cut -d ':' -f 1`
        NO=`echo $PORT | cut -d ':' -f 2`

        # allow access from the internet
        echo "ip6tables -A FORWARD -i 1 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT

        # allow access from the wifi clients
        echo "ip6tables -A FORWARD -s 2001:db8:abc:2::0/64 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT

        # allow access for all subnet clients (skip clients from own subnet)
        SN=`echo $PREFIX | cut -d: -f 4`
        for i in 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18; do
            if [ "$SN" == "$i" ]; then
                continue
            else
                echo "ip6tables -A FORWARD -s 2001:db8:abc:$i::100/120 -d $ADDRESS -p $PROTO --dport $NO -j ACCEPT" >> $SCRIPT
            fi
        done
    done

    private_sub $1 $2 $3
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
echo "ip6tables -P OUTPUT ACCEPT" >> $SCRIPT

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

# accept ssh access from the admin console
echo "ip6tables -A INPUT -s 2001:db8:abc:1::8 -p tcp --dport 22 -j ACCEPT" >> $SCRIPT


# deny internal traffic originating from the internet (prevents spoofing)
echo "ip6tables -A FORWARD -i 1 -s 2001:db8:abc::0/48 -j DROP" >> $SCRIPT

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


# allow the world to access the dns server
echo "ip6tables -A FORWARD -d 2001:db8:abc:1::6 --dport 53 -j ACCEPT" >> $SCRIPT

# allow the admin console to access all dmz servers
echo "ip6tables -A FORWARD -s 2001:db8:abc:1::8 -d 2001:db8:abc:1::0/64 -j ACCEPT" >> $SCRIPT


# allow access to dmz services
public_dmz 2001:db8:abc:1::1 tcp:21,tcp:115
public_dmz 2001:db8:abc:1::2 \
    tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995,udp:143,udp:220
public_dmz 2001:db8:abc:1::3 tcp:80,tcp:443
public_dmz 2001:db8:abc:1::4 tcp:389,tcp:636,udp:389,udp:123
public_dmz 2001:db8:abc:1::5 tcp:1194,tcp:1723,udp:1194,udp:1723
public_dmz 2001:db8:abc:1::6 tcp:53,udp:53
private_dmz 2001:db8:abc:1::7 tcp:118,tcp:156,udp:118,udp:156
private_dmz 2001:db8:abc:1::8 udp:161


# wifi -> internet
echo "ip6tables -A FORWARD -o 1 -s 2001:db8:abc:2::0/64 -j ACCEPT" >> $SCRIPT


# allow access to public subdomain services and restrict usage of private
# services to host in the respective subnet
for SUB in $SUBNETS; do
    PREFIX=`echo $SUB | sed -e 's/::/;/g' | cut -d ';' -f 1`

    # web
    public_sub $PREFIX 1 tcp:80,tcp:443

    # voip
    public_sub $PREFIX 2 tcp:5060,tcp:5061,udp:5060

    # print
    private_sub $PREFIX 3 tcp:631,udp:631

    # mail
    public_sub $PREFIX 4 \
      tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995,udp:143,udp:220

    # file
    private_sub $PREFIX 5 \
      tcp:137,tcp:138,tcp:139,tcp:445,tcp:2049,udp:137,udp:138,udp:139

    # allow subnet clients to access the internet
    echo "ip6tables -A FORWARD -o 1 -s $PREFIX::100/120 -j ACCEPT" >> $SCRIPT
done
