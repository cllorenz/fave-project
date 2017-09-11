#!/usr/bin/env bash

NPADDR=127.0.0.1
NPPORT=1234

TMPDIR=/tmp/np
mkdir -p $TMPDIR

PFLOG=$TMPDIR/pf.log
PFRLOG=$TMPDIR/pfr.log
SUBLOG=$TMPDIR/sub.log
SUBLLOG=$TMPDIR/subl.log
SWLOG=$TMPDIR/sw.log

FORMAT="%e"

alias time='/usr/bin/time -f $FORMAT'

echo -n "start netplumber... "
TMPFILE=$TMPDIR/np.log
net_plumber --hdr-len 1 --server $NPADDR $NPPORT > $TMPFILE &
NP=$!
sleep 1
echo "ok"

echo -n "start aggregator... "
PYTHONPATH=. python2 aggregator/aggregator.py &
AGGR=$!
sleep 1
echo "ok"

# build topology
echo "read topology..."
echo -n "create pgf... "
PYTHONPATH=. time -o $PFLOG python2 topology/topology.py -a -t packet_filter -n pgf -i 2001:db8:abc::1 -p 24
echo "ok"

# create dmz
echo -n "create dmz... "
PYTHONPATH=. time -o $SUBLOG  python2 topology/topology.py -a -t switch -n dmz -p 9
PYTHONPATH=. time -o $SUBLLOG python2 topology/topology.py -a -l pgf.2:dmz.1,dmz.1:pgf.2


HOSTS="file,2001:db8:abc:0::1,tcp:21,tcp:115,tcp:22,udp:22 \
    mail,2001:db8:abc:0::2,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,\
tcp:993,tcp:995,udp:143,udp:220,tcp:22,udp:22 \
    web,2001:db8:abc:0::3,tcp:80,tcp:443,tcp:22,udp:22 \
    ldap,2001:db8:abc:0::4,tcp:389,tcp:636,udp:389,udp:123,tcp:22,udp:22 \
    vpn,2001:db8:abc:0::5,tcp:1194,tcp:1723,udp:1194,udp:1723,tcp:22,udp:22 \
    dns,2001:db8:abc:0::6,tcp:53,udp:53,tcp:22,udp:22 \
    data,2001:db8:abc:0::7,tcp:118,tcp:156,tcp:22,udp:118,udp:156,udp:22 \
    adm,2001:db8:abc:0::8,udp:161,tcp:22,udp:22"

cnt=2
for  HOST in $HOSTS; do
    H=`echo $HOST | cut -d ',' -f 1`
    A=`echo $HOST | cut -d ',' -f 2`
    P=`echo $HOST | cut -d ',' -f 3-`

    PYTHONPATH=. python2 topology/topology.py -a -t host -n $H -i $A -u $P
    PYTHONPATH=. python2 topology/topology.py -a -l $H.1:dmz.$cnt,dmz.$cnt:$H.1

    cnt=$(($cnt+1))
done

echo "ok"

# create wifi
echo -n "create wifi... "
PYTHONPATH=. time -ao $SUBLOG python2 topology/topology.py -a -t switch -n wifi -p 2
PYTHONPATH=. time -ao $SUBLLOG python2 topology/topology.py -a -l pgf.3:wifi.1,wifi.1:pgf.3
PYTHONPATH=. time -ao $SUBLOG python2 topology/topology.py -a -t generator -n wifi-clients -f ipv6_src=2001:db8:abc:1::0/64
echo "ok"

# create subnets
echo "create subnets..."
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

SUBHOSTS="web,tcp:80,tcp:443,tcp:22,udp:22 \
    voip,tcp:5060,tcp:5061,udp:5060,tcp:22,udp:22 \
    print,tcp:631,tcp:22,udp:631,udp:22 \
    mail,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,tcp:993,tcp:995,tcp:22,\
udp:143,udp:220,udp:22 \
    file,tcp:137,tcp:138,tcp:139,tcp:445,tcp:2049,tcp:22,udp:137,udp:138,udp:139,udp:22"

cnt=4
for NET in $SUBNETS; do
    echo -n "create subnet $NET... "

    # create switch for subnet
    PYTHONPATH=. time -ao $SUBLOG python2 topology/topology.py -at switch -n $NET -p 7

    # link switch to firewall
    PYTHONPATH=. time -ao $SUBLLOG python2 topology/topology.py -al pgf.$cnt:$NET.1,$NET.1:pgf.$cnt

    srv=1
    for HOST in $SUBHOSTS; do
        port=$(($srv+1))
        SRV=`echo $HOST | cut -d ',' -f 1`.$NET
        ADDR=2001:db8:abc:$cnt::$srv
        PORTS=`echo $HOST | cut -d ',' -f 2-`

        PYTHONPATH=. time -ao $SUBLOG python2 topology/topology.py -at host -n $SRV -i $ADDR -u $PORTS

        # link switch to server
        PYTHONPATH=. time -ao $SUBLLOG python2 topology/topology.py -al $SRV.1:$NET.$port,$NET.$port:$SRV.1
    done

    echo "ok"

    cnt=$(($cnt+1))
done


# populate firewall
echo -n "populate firewall... "
PYTHONPATH=. time -o $PFRLOG python2 ip6np/ip6np.py -n pgf -i 2001:db8:abc::1 -f pgf-ruleset

# dmz
PYTHONPATH=. time -o $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -t 1 -f ipv6_dst=2001:db8:abc:0::0/64 -c fd=pgf.2

# wifi
PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -t 1 -f ipv6_dst=2001:db8:abc:1::0/64 -c fd=pgf.3

# subnets
cnt=4
for NET in $SUBNETS; do
    PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -f ipv6_dst=2001:db8:abc:$cnt::0/64 -c fd=pgf.$cnt

    cnt=$(($cnt+1))
done
echo "ok"


echo -n "populate switches... "

# dmz
cnt=2
for HOST in $HOSTS; do
    ADDR=`echo $HOST | cut -d ',' -f 2`

    # forwarding rule to host
    PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n dmz -t 1 -f ipv6_dst=$ADDR -c fd=dmz.1
done

# forwarding rule to firewall (default rule)
PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n dmz -t 1 -c fd=dmz.1

# wifi
# forwarding rule to client
PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n wifi -t 1 -f ipv6_dst=2001:db8:abc:1::0/64 -c fd=wifi.2

# forwarding rule to firewall (default rule)
PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n wifi -t 1 -c fd=wifi.1

# subnets
cnt=4
for NET in $SUBNETS; do
    srv=1
    for HOST in $SUBHOSTS; do
        port=$(($srv+1))
        SRV=`echo $HOST | cut -d ',' -f 1`.$NET
        ADDR=2001:db8:abc:$cnt::$srv
        PORTS=`echo $HOST | cut -d ',' -f 2-`

        # forwarding rule to server
        PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n $NET -t 1 -f ipv6_dst=$ADDR -c fd=$NET.$port
    done

    # forwarding rule to firewall (default rule)
    PYTHONPATH=. time -ao $SWLOG python2 openflow/switch.py -a -i 1 -n $NET -t 1 -c fd=$NET.1
done
echo "ok"

PYTHONPATH=. python2 netplumber/print_np.py -t
PYTHONPATH=. python2 netplumber/print_np.py -n

kill -s KILL $AGGR
kill -s KILL $NP
#kill -s KILL $RYU
