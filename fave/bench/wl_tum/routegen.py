#!/usr/bin/env python3

""" wl_tum's routes: the VLAN demultiplexer's table (layout.py). A rule per
endpoint address -- a host's /32 before its VLAN's prefixes, then the
Internet's anonymous prefix on each uplink -- matching the destination VLAN
the firewall's `-o` tagged and the address routing would choose by. """

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.wl_tum import layout, service_matrix, vlans  # pylint: disable=wrong-import-position

OFILE = "bench/wl_tum/routes.json"


def routes():
    out = []
    def rule(vlan, prefix, port):
        out.append([layout.DEMUX, layout.DEMUX_TABLE, len(out) + 1,
                     ["dvlan=%d" % vlan, "ipv4_dst=%s" % prefix],
                     ["fd=%s.%d" % (layout.DEMUX, port)],
                     ["%s.%d" % (layout.DEMUX, layout.DEMUX_IN)]])
    eps = layout.endpoints()
    for name, port, ep in eps:
        if name.startswith('h'):
            rule(ep['vlan'], ep['address'] + '/32', port)
    for name, port, ep in eps:
        if name.startswith('vlan'):
            for prefix in ep['prefixes']:
                rule(ep['vlan'], prefix, port)
    internet_port = next(port for name, port, _e in eps if name == 'Internet')
    for vlan in vlans.UPLINKS:
        rule(vlan, service_matrix.INTERNET, internet_port)
    return out


if __name__ == '__main__':
    with open(OFILE, 'w') as of:
        of.write(json.dumps(routes(), indent=2) + "\n")
