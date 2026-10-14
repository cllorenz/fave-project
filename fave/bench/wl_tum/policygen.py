#!/usr/bin/env python3

""" wl_tum's probes: one per endpoint, behind its port of the VLAN
demultiplexer (layout.py). Existential, as wl_up's per-host probes: compliance
comes from the checks, never from a probe's fields. """

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.wl_tum import layout  # pylint: disable=wrong-import-position

OFILE = "bench/wl_tum/policies.json"

if __name__ == '__main__':
    probes, links = [], []
    for name, port, _ep in layout.endpoints():
        pid = "probe.%s" % layout.endpoint_id(name)
        probes.append((pid, "probe", "existential", None, None, None, None))
        links.append(("%s.%d" % (layout.DEMUX, port), "%s.1" % pid, False))
    with open(OFILE, 'w') as of:
        of.write(json.dumps({"devices": probes, "links": links}, indent=2) + "\n")
