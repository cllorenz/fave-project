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

""" Read NetPlumber's reduced flow-tree dump (`np_i2_flow_dump.py`) and report,
per source, WHERE its flows die -- in FaVe identities.

AD6_PLAN.md §5.5 "ROOT-CAUSING PLAN" step (c). Split from the dump because the
NetPlumber i2 build costs ~552 s and this half gets iterated on.

The reading this tool exists to support: ad6's witness walk for `chic->salt`
passes through `in.chic -> out.chic -> in.kans -> ...`, and NetPlumber calls
that pair unreachable. If NetPlumber's `source.chic` flows all DIE at one of
those devices, the divergence is localized to that (device, rule) -- the same
shape the wl_stanford investigation found (APKEEP_BACKEND.md, "Baseline
validation": 868 of 869 branches dying at `mid.bbra -> out.bbra`, where the
downstream in-port had a matching rule yet no pipe formed).

DELIVERED vs DEAD END is the distinction everything rests on. NetPlumber emits
a leaf for any node with no onward flow, so a leaf is either a probe arrival or
a dropped branch, undistinguished in the dump -- only the node id says which.
Conflating them would make "ad6 forwarded past an NP leaf" trivially true at
every probe.

Branch MULTIPLICITY is kept, not deduplicated: NetPlumber emits one leaf per
dying branch, and "868 branches die here, 1 reaches the probe" was exactly the
signal that localized wl_stanford.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/np_i2_flow_leaves.py --dump-dir /path/to/dump
  python3 bench/np_i2_flow_leaves.py --dump-dir /path/to/dump --source source.chic
"""

import argparse
import collections
import json
import os
import sys


def load_inverse_maps(fave):
    """ `fave.json` indexed for lookup by node id, accepting str or int ids.

    Probes and generators are kept SEPARATE from tables and rules because
    `resolve_node` must check them first -- see its own note on id-space
    overlap. """
    def _keyed(mapping):
        out = {}
        for key, value in (mapping or {}).items():
            out[str(key)] = value
        return out

    return {
        "probe": _keyed(fave.get("id_to_probe")),
        "generator": _keyed(fave.get("id_to_generator")),
        "rule": _keyed(fave.get("id_to_rule")),
        "table": _keyed(fave.get("id_to_table")),
        "port": _keyed(fave.get("id_to_port")),
    }


def leaf_ids(tree):
    """ Every leaf node id in one `<source>.flow_tree.json`, WITH duplicates.

    Simple-mode `children` is already flat, but this walks nested children
    too so a dump taken without `keep_simple` still yields leaves rather than
    silence. A node with no `children` key, or an empty one, IS a leaf; a
    source flow with no `children` contributes nothing (its flow died at the
    source itself, which is an empty leaf set and not an error). """
    leaves = []

    def _walk(node):
        children = node.get("children")
        if not children:
            leaves.append(node["node"])
            return
        for child in children:
            _walk(child)

    for flow in (tree.get("flows") or []):
        children = flow.get("children")
        if not children:
            continue
        for child in children:
            _walk(child)
    return leaves


# A NetPlumber RULE node id packs its table into the high bits:
# (table_id << 32) | index. Verified against the real i2 dump -- 775 of 775
# distinct non-probe leaf ids resolve this way, and none resolve at any
# smaller shift.
_TABLE_SHIFT = 32


def resolve_node(node_id, inv):
    """ (kind, FaVe name) for a NetPlumber node id, or ("unknown", "<id>").

    ORDER MATTERS. Probes and generators are checked FIRST: their ids are
    small integers (i2: probes 92-100, generators 101-109) which would also
    survive the shift below as table id 0, and a probe misreported as a table
    would turn a DELIVERY into a dead end -- inverting the very finding this
    tool exists to produce.

    NOTE WHAT IS *NOT* USED: `fave.json`'s `id_to_rule`. An earlier version of
    this function looked leaves up in it, which is wrong twice over.
    `aggregator_service._dump_aggregator` builds it as
    `id_to_rule[fave_rule_id] = np_node_id >> 12`, so it is keyed by FAVE rule
    ids while flow-tree leaves are NETPLUMBER node ids -- two different id
    spaces that overlap numerically, so the lookup SUCCEEDED on the real dump
    and returned nonsense (`table#20971559`). The shift below derives the
    table from the node id itself and needs no map beyond `id_to_table`. """
    key = str(node_id)
    if key in inv["probe"]:
        return ("probe", inv["probe"][key])
    if key in inv["generator"]:
        return ("generator", inv["generator"][key])
    try:
        table_id = int(node_id) >> _TABLE_SHIFT
    except (TypeError, ValueError):
        return ("unknown", key)
    if table_id and str(table_id) in inv["table"]:
        return ("rule", inv["table"][str(table_id)])
    if key in inv["table"]:
        return ("table", inv["table"][key])
    if key in inv["port"]:
        return ("port", inv["port"][key])
    return ("unknown", key)


def classify_leaves(ids, inv):
    """ Split a leaf multiset into deliveries, dead ends, and unresolvable.

    `unknown_total` is reported separately rather than folded into the dead
    ends: an unresolvable leaf means the dump and the id maps disagree, which
    invalidates the comparison, so it has to be visible instead of quietly
    inflating the interesting number. """
    delivered = collections.Counter()
    dead_end = collections.Counter()
    unknown = collections.Counter()
    for node_id in ids:
        kind, name = resolve_node(node_id, inv)
        if kind == "probe":
            delivered[name] += 1
        elif kind == "unknown":
            unknown[name] += 1
        else:
            dead_end[name] += 1
    return {
        "leaves_total": len(ids),
        "delivered": dict(delivered),
        "delivered_total": sum(delivered.values()),
        "dead_end": dict(dead_end),
        "dead_end_total": sum(dead_end.values()),
        "dead_end_tables": sorted(dead_end),
        "unknown": dict(unknown),
        "unknown_total": sum(unknown.values()),
    }


def analyse(dump_dir, only_source=None):
    with open(os.path.join(dump_dir, "fave.json")) as handle:
        fave = json.load(handle)
    inv = load_inverse_maps(fave)

    report = {}
    for name in sorted(os.listdir(dump_dir)):
        if not name.endswith(".flow_tree.json"):
            continue
        node_id = name.split(".", 1)[0]
        kind, source = resolve_node(node_id, inv)
        if only_source is not None and source != only_source:
            continue
        with open(os.path.join(dump_dir, name)) as handle:
            tree = json.load(handle)
        summary = classify_leaves(leaf_ids(tree), inv)
        summary["source_node_id"] = node_id
        summary["source_kind"] = kind
        report[source] = summary
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump-dir", required=True, help="directory np_i2_flow_dump.py wrote")
    parser.add_argument("--source", default=None, help="restrict to one source, e.g. source.chic")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv)

    report = analyse(args.dump_dir, only_source=args.source)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for source in sorted(report):
        s = report[source]
        print("%s  (node %s, %s)" % (source, s["source_node_id"], s["source_kind"]))
        print("   leaves %d = delivered %d + dead-end %d + unknown %d" % (
            s["leaves_total"], s["delivered_total"], s["dead_end_total"], s["unknown_total"]))
        if s["delivered"]:
            print("   delivered to : %s" % ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(s["delivered"].items())))
        if s["dead_end"]:
            print("   dies at      : %s" % ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(
                    s["dead_end"].items(), key=lambda kv: -kv[1])))
        if s["unknown"]:
            print("   UNRESOLVED   : %s" % ", ".join(sorted(s["unknown"])))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
