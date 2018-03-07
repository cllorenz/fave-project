#!/usr/bin/env bash

TIME='/usr/bin/time -f %e'

scripts/start_aggr.sh

echo "pgf firewall (pf+ruleset)"
PYTHONPATH=. $TIME -o /tmp/np/test.log python2 topology/topology.py -a -t packet_filter -n pgf -i 2001:db8:abc::1 -p 24
PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 ip6np/ip6np.py -n pgf -i 2001:db8:abc::1 -f rulesets/pgf-ruleset

echo "776x empty python scripts"
for i in {1..776}; do
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 profile_dummy.py
done

echo "113x packet filter (pf+rulesets)"
for i in {1..113};do
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 topology/topology.py -a -t packet_filter -n mail.api -i 2001:db8:abc::2 -p 1
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 ip6np/ip6np.py -n mail.api -i 2001:db8:abc::2 -f "rulesets/api-mail-ruleset"
done

scripts/stop_aggr.sh
