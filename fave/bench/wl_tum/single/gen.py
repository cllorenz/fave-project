#!/usr/bin/env python3

""" wl_tum's SINGLE variant (owner, 2026-10-14): the model wl_tum had until
then -- fw.tum alone, one source (`tcp_src=10000;tcp_dst=80`, no address)
into its forward chain and one universal probe on its accept port, no routes,
no checks. V5 and the D11 run measured this model, and the tests written
for it (test_apkeep_tum, test_apkeep_ndd_fwd, test_veriflow_differential)
replay it from this directory, which holds the four files a replay reads.
Writes exactly what topogen.py, policygen.py and routegen.py wrote before
wl_tum got its policy (bench/wl_tum/WORKLOAD.md). """

import json
import os
import sys

OUT = "bench/wl_tum/single"


def _main(argv):
    address = "2001:db8::1"
    ruleset = "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset"
    if len(argv) == 3:
        address = "2001:db8::1" if argv[1] == "ipv6" else "10.0.0.1"
        ruleset = argv[2]
    topology = {'devices': [("fw.tum", "packet_filter", ['eth0', 'eth1'], address, ruleset)],
                'links': []}
    sources = {'devices': [("source.tum", "generator", ["tcp_src=10000;tcp_dst=80"])],
               'links': [("source.tum.1", "fw.tum.forward_filter_in", True)]}
    policies = {"devices": [("probe.tum", "probe", "universal", None, None, None, None)],
                "links": [("fw.tum.forward_filter_accept", "probe.tum.1", False)]}
    json.dump(topology, open(os.path.join(OUT, "topology.json"), 'w'), indent=2)
    json.dump(sources, open(os.path.join(OUT, "sources.json"), 'w'), indent=2)
    with open(os.path.join(OUT, "policies.json"), 'w') as of:
        of.write(json.dumps(policies, indent=2) + "\n")
    with open(os.path.join(OUT, "routes.json"), 'w') as of:
        of.write(json.dumps([], indent=2) + "\n")


if __name__ == '__main__':
    _main(sys.argv)
