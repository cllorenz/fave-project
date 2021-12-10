#!/usr/bin/env python2

import json

from devices.router import parse_cisco_interfaces

CISCO_CONF = "bench/wl_ifi/acls.txt"
OFILE = "bench/wl_ifi/cisco_to_inventory.json"

VLAN_TO_DOMAIN, _VTP, VLAN_TO_IPS, _VTA, _ITV = parse_cisco_interfaces(CISCO_CONF)

RES = {}

for VLAN, DOMAIN in VLAN_TO_DOMAIN.iteritems():
    DNAME = DOMAIN + '.ifi' if not DOMAIN in ['Internet'] else DOMAIN
    RES[DNAME] = (VLAN, VLAN_TO_IPS.get(VLAN, None))

with open(OFILE, 'w') as ofile:
    json.dump(RES, ofile, indent=2)
