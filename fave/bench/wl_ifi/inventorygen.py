#!/usr/bin/env python2

""" Generates the inventory for the IfI workload.
"""

import json

from bench.wl_ifi.inventory import SUBNETS

inventory = {}

inventory["domains"] = ["%s.ifi" % pre for pre in SUBNETS]

with open("bench/wl_ifi/vlan_to_dn.json", "r") as vdf:
    inventory["vlan_to_domain"] = json.loads('\n'.join([
        line for line in vdf.read().split('\n') if not line.startswith('#')
    ]))

with open("bench/wl_ifi/inventory.json", "w") as ivf:
    json.dump(inventory, ivf)
