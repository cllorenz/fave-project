#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" Enriched wl_up model dump for the NDD reachability engine (§2.5c): rules, parsed
topology edges, and per-source/probe attachment (dev, port) + source src CIDR --
exactly the inputs the BDD reachability query uses (adapter.check_compliance).
Run from fave/ with PYTHONPATH=.:  python3 wl_up_dump2.py <out.json>
"""
import json
import os
import sys

import apkeep.lib_apkeep as libmod

CAP = {"rules": None, "edges": None}


def _fake_init(self, name, l1_links, fwd_devices=None, device_acls=None,
               device_nats=None, device_filters=None, bdd_table_size=1_000_000):
    CAP["edges"] = list(l1_links)
    return None


def _fake_run(self, rules):
    CAP["rules"] = list(rules)
    return None


def _fake_metrics(self):
    return {"ACLElement": 0, "NATElement": 0}


libmod.LibAPKeep.init_in_memory = _fake_init
libmod.LibAPKeep.run = _fake_run
libmod.LibAPKeep.element_metrics = _fake_metrics


def main(out_path):
    import logging
    log = logging.getLogger("d"); log.setLevel(logging.ERROR)
    from apkeep.adapter import APKeepAdapter, available, _split_port
    if not available():
        print("APKeep unavailable"); return 1
    from util.in_process_driver import InProcessFaVe

    engine = APKeepAdapter(log)
    with InProcessFaVe(engine) as fave:
        fave.replay("bench/wl_up")
        engine._build()

    def resolve(name_to_port):
        out = {}
        for name, port in name_to_port.items():
            dev, prt = _split_port(port)
            out[name] = [dev, prt]
        return out

    sources = {}
    for name, port in engine._generators.items():
        dev, prt = _split_port(port)
        sources[name] = {"dev": dev, "port": prt,
                         "cidr": engine._gen_src.get(name)}
    probes = {}
    for name, port in engine._probes.items():
        dev, prt = _split_port(port)
        probes[name] = {"dev": dev, "port": prt}

    edges = [e.split() for e in CAP["edges"]]

    dump = {"rules": CAP["rules"], "edges": edges,
            "sources": sources, "probes": probes}
    with open(out_path, "w") as fh:
        json.dump(dump, fh)
    print("rules=%d edges=%d sources=%d probes=%d -> %s" % (
        len(CAP["rules"]), len(edges), len(sources), len(probes), out_path))
    # sanity: a couple of source cidrs
    ex = list(sources.items())[:3]
    for n, v in ex:
        print("  src %-40s dev=%s port=%s cidr=%s" % (n, v["dev"], v["port"], v["cidr"]))
    return 0


if __name__ == "__main__":
    rc = main(sys.argv[1] if len(sys.argv) > 1 else "wl_up_model2.json")
    sys.stdout.flush()
    os._exit(rc)
