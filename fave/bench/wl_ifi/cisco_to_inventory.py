#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" Converts Cisco ACL to inventory file.
"""

import json

from devices.router import parse_cisco_interfaces

CISCO_CONF = "bench/wl_ifi/acls.txt"
OFILE = "bench/wl_ifi/cisco_to_inventory.json"

VLAN_TO_DOMAIN, _VTP, VLAN_TO_IPS, _VTA, _ITV = parse_cisco_interfaces(CISCO_CONF)

RES = {}

for VLAN, DOMAIN in list(VLAN_TO_DOMAIN.items()):
    DNAME = DOMAIN + '.ifi' if not DOMAIN in ['Internet'] else DOMAIN
    RES[DNAME] = (VLAN, VLAN_TO_IPS.get(VLAN, None))

with open(OFILE, 'w') as ofile:
    json.dump(RES, ofile, indent=2)
