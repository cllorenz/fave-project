#!/usr/bin/env python2

""" Generates the inventory for the IfI workload.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

inventory = {}

inventory["domains"] = ["%s.ifi" % pre for pre in SUBNETS]

with open("bench/wl_ifi/cisco_to_inventory.json", "r") as vdf:
#with open("bench/wl_ifi/vlan_to_dn.json", "r") as vdf:
#    mapping = json.loads('\n'.join([
#        line for line in vdf.read().splitlines() if not line.startswith('#')
#    ]))
    mapping = json.load(vdf)

    get_vlan = lambda vlan, _ip: vlan
    get_ip = lambda _vlan, ip: ip
    has_ip = lambda _vlan, ip: ip is not None

    inventory["vlan_to_domain"] = {
        get_vlan(*v) : d for d, v in mapping.iteritems()
    }
    inventory["domain_to_vlan"] = {
        d : get_vlan(*v) for d, v in mapping.iteritems()
    }
    inventory["domain_to_ip"] = {
        d : get_ip(*v) for d, v in mapping.iteritems() if has_ip(*v)
    }
    inventory["ip_to_domain"] = {
        get_ip(*v) : d for d, v in mapping.iteritems() if has_ip(*v)
    }
    inventory["domain_to_ports"] = {
        sub : (3+idx, 20+idx) for idx, sub in enumerate(SUBNETS, start=0)
    }

with open("bench/wl_ifi/inventory.json", "w") as ivf:
    json.dump(inventory, ivf, indent=2)
