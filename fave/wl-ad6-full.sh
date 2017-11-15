#!/usr/bin/env bash


TMPDIR=/tmp/np
mkdir -p $TMPDIR

PFLOG=$TMPDIR/pf.log
PFRLOG=$TMPDIR/pfr.log
SUBLOG=$TMPDIR/sub.log
SUBLLOG=$TMPDIR/subl.log
SWLOG=$TMPDIR/sw.log
SRCLOG=$TMPDIR/source.log
SRCLLOG=$TMPDIR/sourcel.log
PROBELOG=$TMPDIR/probe.log
PROBELLOG=$TMPDIR/probel.log

TIME='/usr/bin/time -f %e'

echo -n "delete old logs and measurements... "
rm -f /tmp/np/*.log
echo "ok"

echo -n "start netplumber... "
scripts/start_np.sh test-workload-ad6.conf
echo "ok"

echo -n "start aggregator... "
scripts/start_aggr.sh
echo "ok"

# build topology
echo "read topology..."
echo -n "create pgf... "
PYTHONPATH=. $TIME -o $PFLOG python2 topology/topology.py -a -t packet_filter -n pgf -i 2001:db8:abc::1 -p 24
echo "ok"

# create dmz
echo -n "create dmz... "
PYTHONPATH=. $TIME -o $SUBLOG  python2 topology/topology.py -a -t switch -n dmz -p 9
PYTHONPATH=. $TIME -o $SUBLLOG python2 topology/topology.py -a -l pgf.2:dmz.1,dmz.1:pgf.2


HOSTS="file,2001:db8:abc:0::1,tcp:21,tcp:115,tcp:22,udp:22 \
    mail,2001:db8:abc:0::2,tcp:25,tcp:587,tcp:110,tcp:143,tcp:220,tcp:465,\
tcp:993,tcp:995,udp:143,udp:220,tcp:22,udp:22 \
    web,2001:db8:abc:0::3,tcp:80,tcp:443,tcp:22,udp:22 \
    ldap,2001:db8:abc:0::4,tcp:389,tcp:636,udp:389,udp:123,tcp:22,udp:22 \
    vpn,2001:db8:abc:0::5,tcp:1194,tcp:1723,udp:1194,udp:1723,tcp:22,udp:22 \
    dns,2001:db8:abc:0::6,tcp:53,udp:53,tcp:22,udp:22 \
    data,2001:db8:abc:0::7,tcp:118,tcp:156,tcp:22,udp:118,udp:156,udp:22 \
    adm,2001:db8:abc:0::8,udp:161,tcp:22,udp:22"

echo "ok"

# create wifi
echo -n "create wifi... "
PYTHONPATH=. $TIME -ao $SUBLOG python2 topology/topology.py -a -t switch -n wifi -p 2
PYTHONPATH=. $TIME -ao $SUBLLOG python2 topology/topology.py -a -l pgf.3:wifi.1,wifi.1:pgf.3
#PYTHONPATH=. $TIME -ao $SUBLOG python2 topology/topology.py -a -t generator -n wifi-clients -f ipv6_src=2001:db8:abc:1::0/64
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
    echo -n "  create subnet $NET... "

    # create switch for subnet
    PYTHONPATH=. $TIME -ao $SUBLOG python2 topology/topology.py -at switch -n $NET -p 7

    # link switch to firewall
    PYTHONPATH=. $TIME -ao $SUBLLOG python2 topology/topology.py -al pgf.$cnt:$NET.1,$NET.1:pgf.$cnt

    echo "ok"

    cnt=$(($cnt+1))
done


# populate firewall
echo -n "populate firewall... "
PYTHONPATH=. $TIME -o $PFRLOG python2 ip6np/ip6np.py -n pgf -i 2001:db8:abc::1 -f rulesets/pgf-ruleset

# dmz (route)
PYTHONPATH=. $TIME -o $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -t 1 -f ipv6_dst=2001:db8:abc:0::0/64 -c fd=pgf.2

# wifi (route)
PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -t 1 -f ipv6_dst=2001:db8:abc:1::0/64 -c fd=pgf.3

# subnets (routes)
cnt=4
for NET in $SUBNETS; do
    PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n pgf -f ipv6_dst=2001:db8:abc:$cnt::0/64 -c fd=pgf.$cnt

    cnt=$(($cnt+1))
done
echo "ok"


echo -n "populate switches... "

# dmz
cnt=2
for HOST in $HOSTS; do
    ADDR=`echo $HOST | cut -d ',' -f 2`

    # forwarding rule to host
    PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n dmz -t 1 -f ipv6_dst=$ADDR -c fd=dmz.1
done

# forwarding rule to firewall (default rule)
PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n dmz -t 1 -c fd=dmz.1

# wifi
# forwarding rule to client
PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n wifi -t 1 -f ipv6_dst=2001:db8:abc:1::0/64 -c fd=wifi.2

# forwarding rule to firewall (default rule)
PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n wifi -t 1 -c fd=wifi.1

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
        PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n $NET -t 1 -f ipv6_dst=$ADDR -c fd=$NET.$port
    done

    # forwarding rule to firewall (default rule)
    PYTHONPATH=. $TIME -ao $SWLOG python2 openflow/switch.py -a -i 1 -n $NET -t 1 -c fd=$NET.1
done
echo "ok"

echo -n "create internet (source)... "
PYTHONPATH=. $TIME -o $SRCLOG python2 topology/topology.py -at generator -n internet
PYTHONPATH=. $TIME -o $SRCLLOG python2 topology/topology.py -al internet.1:pgf.1
echo "ok"

echo -n "create hosts (pf + source) in dmz... "
cnt=2
for  HOST in $HOSTS; do
    H=`echo $HOST | cut -d ',' -f 1`
    A=`echo $HOST | cut -d ',' -f 2`
    P=`echo $HOST | cut -d ',' -f 3-`

    PYTHONPATH=. $TIME -ao $PFLOG python2 topology/topology.py -a -t packet_filter -n $H -i $A -p 1
    # TODO: correct logging file: $TIME -ao $PFRLOG 
    PYTHONPATH=. python2 topology/topology.py -a -l $H.1:dmz.$cnt,dmz.$cnt:$H.1

    PYTHONPATH=. $TIME -ao $SRCLOG python2 topology/topology.py -a -t generator -n source.$H -f "ipv6_src=$A"

    PYTHONPATH=. $TIME -ao $PFRLOG python2 ip6np/ip6np.py -n $H -i $A -f "rulesets/$H-ruleset"

    PYTHONPATH=. $TIME -ao $SRCLLOG python2 topology/topology.py -a -l source.$H.1:$H"_output_states_in"

    cnt=$(($cnt+1))
done
echo "ok"

echo "create hosts (pf + source) in subnets..."
cnt=4
for NET in $SUBNETS; do
    echo -n "  create host $NET... "

    srv=1
    for HOST in $SUBHOSTS; do
        port=$(($srv+1))
        HN=`echo $HOST | cut -d ',' -f 1`.$NET
        SRV=source.$HN
        ADDR=2001:db8:abc:$cnt::$srv
        PORTS=`echo $HOST | cut -d ',' -f 2-`

        PYTHONPATH=. $TIME -ao $PFLOG python2 topology/topology.py -a -t packet_filter -n $HN -i $A -p 1
        # TODO: correct logging file: $TIME -ao $PFRLOG 
        PYTHONPATH=. python2 topology/topology.py -a -l $HN.1:$NET.$port,$NET.$port:$HN.1

        PYTHONPATH=. $TIME -ao $SRCLOG python2 topology/topology.py -a -t generator -n $SRV -f "ipv6_src=$A"

        PYTHONPATH=. $TIME -ao $PFRLOG python2 ip6np/ip6np.py -n $HN -i $A -f "rulesets/$H-ruleset"

        PYTHONPATH=. $TIME -ao $SRCLLOG python2 topology/topology.py -a -l $SRV.1:$H"_output_states_in"

        srv=$(($srv+1))
    done

    echo "ok"

    cnt=$(($cnt+1))
done

echo "test ssh reachability from the internet..."
touch $PROBELOG
touch $PROBELLOG

echo -n "  test dmz... "
cnt=2
for  HOST in $HOSTS; do
    H=probe.`echo $HOST | cut -d ',' -f 1`
    A=`echo $HOST | cut -d ',' -f 2`
    P=`echo $HOST | cut -d ',' -f 3-`

    # add probe that looks for incoming flows for tcp port 22 (ssh) originating from the internet
    PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -a -t probe -n $H -q existential -P ".*(p=pgf.1);$" -F "tcp_dst=22"
    # link probe to switch
    PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -a -l $H.1:dmz.$cnt

    # remove probe
    #PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -d -n $H
    # ... and link
    #PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -d -l $H.1:dmz.$cnt

    cnt=$(($cnt+1))
done
echo "ok"

echo "  test subnets... "
cnt=4
for NET in $SUBNETS; do
    srv=1

    echo -n "    test $NET... "

    for HOST in $SUBHOSTS; do
        port=$(($srv+1))
        HN=`echo $HOST | cut -d ',' -f 1`.$NET
        SRV=probe.$HN
        ADDR=2001:db8:abc:$cnt::$srv
        PORTS=`echo $HOST | cut -d ',' -f 2-`

        # add probe that looks for incoming flows for tcp port 22 (ssh) originating from the internet
        PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -a -t probe -n $SRV -q existential -P ".*(p=pgf.1);$" -F "tcp_dst=22"
        # link probe to switch
        PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -a -l $HN"_internals_in":$SRV.1

        # remove probe
        #PYTHONPATH=. $TIME -ao $PROBELOG python2 topology/topology.py -d -n $SRV
        # ... and link
        #PYTHONPATH=. $TIME -ao $PROBELLOG python2 topology/topology.py -d -l $NET.$port:$SRV.1
    done

    echo "ok"

    cnt=$(($cnt+1))
done

scripts/stop_aggr.sh
scripts/stop_np.sh
