#!/usr/bin/env python2

""" This module provides the inventory for the IFI workload.
"""

import json

INVENTORY='bench/wl_ifi/cisco_to_inventory.json'

WITH_IP = []
WITHOUT_IP = []

with open(INVENTORY, 'r') as invf:
    exception = lambda x: x in ['Internet', 'external.ifi']
    inv = json.load(invf)
    has_ip = lambda _vlan, ip: ip is not None
    WITH_IP = [d for d, v in inv.items() if has_ip(*v) if not exception(d)]
    WITHOUT_IP = [d for d, v in inv.items() if not has_ip(*v)]

SUBNETS = WITH_IP + WITHOUT_IP
