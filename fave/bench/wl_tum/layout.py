""" wl_tum's endpoints as the model lays them out (owner, 2026-10-14): one
source and one probe each, the probe behind the VLAN demultiplexer
`vlans.tum`, a FaVe switch hanging off `fw.tum.forward_filter_accept`.
topogen.py, routegen.py, policygen.py and inventorygen.py all read this, so
they agree on names, order and port numbers.

The demultiplexer selects what ROUTING would send to an endpoint -- the
firewall's chains tag a flow's destination VLAN (`-o eth1.<v>` is
`dvlan=<v>`, FaVe's `-o` semantics, devices/abstract_firewall.py) and routing
picks it by destination address -- so each rule matches the endpoint's VLAN
AND its addresses: a host's /32 first, then its VLAN's prefixes (the rest of
the VLAN), then the Internet's anonymous prefix on either uplink. Everything
else matches no rule and goes nowhere.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MATRIX = os.path.join(HERE, 'service_matrix.json')
FW = 'fw.tum'
DEMUX = 'vlans.tum'
#: The table a route names: a FaVe switch has one, `<node>.1` (devices/switch.py),
#: so 1, as in wl_cloud. Not a table id -- the switch declares none.
DEMUX_TABLE = 1
#: the demultiplexer's input port; endpoints take the ports after it. Not 1:
#: a FaVe switch's table is named `<node>.1` (devices/switch.py), and a port
#: of that name is the table's name too -- with it, every probe saw every flow.
#: wl_cloud's switches number their ports from 1000 as well.
DEMUX_IN = 1000


def endpoints():
    """ [(endpoint, demux port, dict)] -- the Internet first, then hosts,
    then the VLAN rests, as service_matrix.json lists them. """
    with open(MATRIX) as raw:
        m = json.load(raw)
    names = ['Internet'] + sorted(n for n in m['endpoints'] if n.startswith('h')) \
        + sorted((n for n in m['endpoints'] if n.startswith('vlan')), key=lambda n: int(n[4:]))
    out = []
    for port, name in enumerate(names, start=DEMUX_IN + 1):
        out.append((name, port, m['endpoints'].get(name)))
    return out


def endpoint_id(name):
    """ The source/probe suffix: `internet` for the Internet (the name every
    workload's checks use), the endpoint name otherwise. """
    return 'internet' if name == 'Internet' else name
