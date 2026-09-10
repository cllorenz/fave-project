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

""" AD6_PLAN.md §5.5 "ROOT-CAUSING PLAN" step (c): drive wl_i2 through
NetPlumber in-process and dump its REDUCED flow trees, so the nodes where
NetPlumber's flows actually DIE can be compared against ad6's witness paths.

Why this exists as its own script, and why it only dumps. The NetPlumber i2
build costs ~552 s and ~1 GB, while parsing the dump is iterated on -- so the
expensive half writes raw output to disk once and `np_i2_flow_leaves.py` reads
it as many times as needed. Coupling them would mean re-running a 9-minute
build to fix a parsing bug.

WHAT THE DUMP CONTAINS. `dump_flow_trees(odir, keep_simple=True)` writes one
`<source_node_id>.flow_tree.json` per source node, shaped
`{"flows": [{"node": <source id>, "children": [{"node": <leaf id>}, ...]}]}`.
In simple mode `_traverse_flow_tree` (net_plumber.cc:1694) recurses and appends
ONLY leaves, into one FLAT array -- no hierarchy and NO header space. Absent
`children` means the flow died at the source itself.

TWO PROPERTIES OF THAT OUTPUT THAT DECIDE HOW IT MAY BE READ:

  * A leaf is any node with no onward flow, so it conflates "delivered to a
    probe" with "dropped". Only the id tells them apart, hence the id maps
    below. Without that split, "ad6 forwarded past an NP leaf" is trivially
    true at every probe.
  * Simple mode carries no header space at all. That is DELIBERATE here, not a
    limitation to work around: the wl_stanford investigation that pioneered this
    technique (APKEEP_BACKEND.md, "Baseline validation") could not decode NP's
    packed header vectors reliably and ended with "do not assert a specific VLAN
    value until this is decoded". So NP's flow STRUCTURE is the oracle and NP's
    header VALUES are untrusted. See §5.5 for the deferred option of changing
    that.

THE ID MAPS. Leaves are bare numeric `node_id`s, so the dump is useless without
`fave.json`. That file is normally written by `aggregator_service._dump_aggregator`,
which is not in play here (`InProcessFaVe` runs no aggregator), so this script
writes it from the engine's own id tables using the same construction --
including `id_to_rule`'s `key >> 12`, which is how a rule id maps to its table.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/np_i2_flow_dump.py --out-dir /path/to/dump
"""

import argparse
import json
import logging
import os
import resource
import sys
import time

sys.setrecursionlimit(10 ** 6)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)
_I2_PREFIX = os.path.join("bench", "wl_i2", "i2-json")


def _peak_rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _write_fave_json(engine, odir):
    """ The id -> identity maps, in the same shape
    `aggregator_service._dump_aggregator` writes and
    `test/check_flows.py::_get_inverse_fave` reads. Written here because
    `InProcessFaVe` runs no aggregator, so nothing else would produce it --
    and without it the dump's numeric leaves cannot be resolved at all. """
    payload = {
        "mapping": engine.mapping.to_json(),
        "id_to_table": {engine.tables[k]: k for k in engine.tables},
        "id_to_generator": {engine.generators[k][1]: k for k in engine.generators},
        "id_to_probe": {engine.probes[k][1]: k for k in engine.probes},
        "id_to_port": {engine.ports[k]: k for k in engine.ports},
    }
    # `rule_ids` is keyed by a packed (table << 12 | index) value; the aggregator
    # stores rule -> TABLE id, and >> 12 is what recovers the table.
    id_to_rule = {}
    for key in engine.rule_ids:
        for elem in engine.rule_ids[key]:
            id_to_rule[elem] = key >> 12
    payload["id_to_rule"] = id_to_rule
    with open(os.path.join(odir, "fave.json"), "w") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
    return {"tables": len(payload["id_to_table"]), "rules": len(id_to_rule),
            "generators": len(payload["id_to_generator"]),
            "probes": len(payload["id_to_probe"]),
            "ports": len(payload["id_to_port"])}


def dump(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    result = {"bench": "i2", "engine": "netplumber", "out_dir": out_dir}
    wall0 = time.time()

    from netplumber.lib_adapter import NetPlumberLibAdapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("np_i2_flow_dump")
    log.setLevel(logging.WARNING)
    engine = NetPlumberLibAdapter(log)

    files = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}
    with InProcessFaVe(engine) as fave:
        t0 = time.time()
        fave.replay(_I2_PREFIX, files=files)
        result["build_s"] = round(time.time() - t0, 3)
        result["peak_rss_after_build_mb"] = _peak_rss_mb()
        print("[np] built in %.1fs, peak %s MB" % (
            result["build_s"], result["peak_rss_after_build_mb"]), file=sys.stderr, flush=True)

        t0 = time.time()
        result["id_maps"] = _write_fave_json(engine, out_dir)
        engine.dump_flow_trees(out_dir, keep_simple=True)
        result["dump_s"] = round(time.time() - t0, 3)

    trees = sorted(f for f in os.listdir(out_dir) if f.endswith(".flow_tree.json"))
    result["flow_tree_files"] = len(trees)
    result["wall_s"] = round(time.time() - wall0, 3)
    result["peak_rss_mb"] = _peak_rss_mb()
    print(json.dumps(result, indent=2))
    with open(os.path.join(out_dir, "dump_meta.json"), "w") as handle:
        json.dump(result, handle, indent=2)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True,
                        help="directory to write fave.json + the flow-tree dump into")
    args = parser.parse_args(argv)
    dump(args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
