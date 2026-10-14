#!/usr/bin/env python3

""" wl_tum's topology and sources (owner, 2026-10-14; layout.py): the
firewall `fw.tum`, the VLAN demultiplexer `vlans.tum` behind its forward
chain's accept port, and one source per endpoint entering the forward chain
as if from its VLAN on eth1 -- `in_port` eth1's ingress, `svlan` its VLAN,
`ipv4_src` its addresses (the Internet: the anonymous prefix on uplink 110).

Until 2026-10-14 wl_tum had one source (`tcp_src=10000;tcp_dst=80`, no
address) and one universal probe, and no checks.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.wl_tum import layout, service_matrix, vlans  # pylint: disable=wrong-import-position

TOPOLOGY = "bench/wl_tum/topology.json"
SOURCES = "bench/wl_tum/sources.json"


def _main(argv):
    # the ruleset service_matrix.py derived the policy from, over IPv4; the
    # single variant keeps the old defaults (single/gen.py)
    address = "10.0.0.1"
    ruleset = "bench/wl_tum/rulesets/tum-ruleset"
    if len(argv) == 3:
        address = "2001:db8::1" if argv[1] == "ipv6" else "10.0.0.1"
        ruleset = argv[2]

    eps = layout.endpoints()
    devices = [
        (layout.FW, "packet_filter", ['eth0', 'eth1'], address, ruleset),
        (layout.DEMUX, "switch", [str(layout.DEMUX_IN)] + [str(port) for _n, port, _e in eps],
         {layout.DEMUX: layout.DEMUX_TABLE}),
    ]
    links = [("%s.forward_filter_accept" % layout.FW, "%s.%d" % (layout.DEMUX, layout.DEMUX_IN), False)]

    sources, source_links = [], []
    for name, _port, ep in eps:
        if name == 'Internet':
            vlan, src = vlans.UPLINK, service_matrix.INTERNET
        else:
            vlan = ep['vlan']
            src = ep['address'] if '/' in ep['address'] else ep['address'] + '/32'
        sid = "source.%s" % layout.endpoint_id(name)
        sources.append((sid, "generator", [
            "in_port=%s.eth1_ingress" % layout.FW, "svlan=%d" % vlan, "ipv4_src=%s" % src]))
        source_links.append(("%s.1" % sid, "%s.forward_filter_in" % layout.FW, True))

    json.dump({'devices': devices, 'links': links}, open(TOPOLOGY, 'w'), indent=2)
    json.dump({'devices': sources, 'links': source_links}, open(SOURCES, 'w'), indent=2)


if __name__ == '__main__':
    _main(sys.argv)
