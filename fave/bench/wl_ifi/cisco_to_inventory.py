#!/usr/bin/env python2

import json

from topology.router import parse_cisco_interfaces

CISCO_CONF="bench/wl_ifi/acls.txt"
OFILE="bench/wl_ifi/cisco_to_inventory.json"

vlan_to_domain, _vtp, vlan_to_ips, _vta = parse_cisco_interfaces(CISCO_CONF)

res = {}

for vlan, domain in vlan_to_domain.iteritems():
    dn = domain + '.ifi' if not domain in ['Internet'] else domain
    res[dn] = (vlan, vlan_to_ips.get(vlan, None))

with open(OFILE, 'w') as ofile:
    json.dump(res, ofile, indent=2)
