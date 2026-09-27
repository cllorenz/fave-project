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

""" Dump a workload's engine-level rule IR, then replay it -- optionally on a
subset of the devices -- on either APKeep engine.

WHY THIS EXISTS. When the two engines behind `apkeep/adapter.py` disagree, the
question is always "is it the translation or the engine?", and then "which
rule?". `APKeepAdapter._build()` hands BOTH engines the SAME `all_rules` and
`edges`, so dumping that IR settles the first question outright, and replaying a
PRUNED copy of it settles the second cheaply.

It was built to diagnose TODO item 29's third defect: BDD answered 53 of
wl_cloud's 64 reachable pairs where NDD and NetPlumber answer 59, and a BDD
build of that model takes 2.8 hours. Replaying the IR for ONE datacentre
reproduced the disagreement in 9.4 s and, pruned to one leaf and one NAT rule,
in 0.4 s -- at which point the engine's internals could simply be read.

DISCIPLINE. Pruning changes the model, so a pruned answer is evidence only if
the cheap engine still answers the pruned model the way it answers the whole
one. Always run `--engine ndd` on the same prune first and compare it with the
full-model NDD matrix; `--engine ndd` costs about a second at any size.

Usage, from fave/ with PYTHONPATH=. and the venv active:

    # 1. dump the IR once (the adapter's own translation, engine-neutral)
    python3 bench/apkeep_ir_replay.py dump --bench wl_cloud --out ir.json

    # 2. replay it, whole or pruned, on either engine
    python3 bench/apkeep_ir_replay.py replay --ir ir.json --engine ndd
    python3 bench/apkeep_ir_replay.py replay --ir ir.json --engine bdd \
        --keep dc0 --out dc0-bdd.json

`--keep` takes comma-separated substrings; a device is kept if it contains one
of them, or if it is an `internet`/`gw.` device (the gateway and the outside are
what every datacentre subset still needs). An edge survives only if BOTH of its
endpoints do, so a route out of the kept region dies at an unwired port -- which
is the intended semantics for a subset, and the reason for the discipline above.

FAVE_APKEEP_JAR, if set, selects the APKeep jar for `--engine bdd`, so a patched
build somewhere else can be compared against the tree's own without rebuilding
it (and without disturbing a measurement already holding `apkeep/target`).

SCOPE. `dump` handles the workloads FaVe replays from `bench/<name>/` with a
`mapping.json` (wl_cloud, wl_ifi, wl_up, ...). The faithful HSA models read
their own prefixes and set `faithful_vlan` themselves (`bench/faithful_bdd_
measure.py`), so they would need that construction passed through here; `replay`
is independent of all of it and works on any IR of this shape.
"""

import argparse
import json
import logging
import os
import sys
import time


class _Captured(Exception):
    """ Raised once the IR is in hand, to stop before the engine builds. """


def _dump(bench, out_path):
    """ Run the adapter's translation for `bench` and capture exactly what it
    would hand the engine: the element structure from `init_in_memory` and the
    rule list from `run`. Aborts at `run` -- the point is the IR, and for BDD
    the build that follows is the thing we are trying not to run. """
    prefix = "bench/%s" % bench
    captured = {}

    from apkeep.lib_apkeep import LibAPKeep
    _init = LibAPKeep.init_in_memory

    def init(self, name, l1_links, fwd_devices=None, device_acls=None,
             device_nats=None, device_filters=None, bdd_table_size=1_000_000):
        captured.update(
            name=name, edges=list(l1_links), fwd_devices=list(fwd_devices or []),
            device_acls=device_acls,
            device_nats={k: list(v) for k, v in (device_nats or {}).items()} or None,
            device_filters=list(device_filters or []),
            bdd_table_size=bdd_table_size)
        return _init(self, name, l1_links, fwd_devices, device_acls,
                     device_nats, device_filters, bdd_table_size)

    def run(self, rules):
        captured["rules"] = [str(r) for r in rules]
        raise _Captured()

    LibAPKeep.init_in_memory = init
    LibAPKeep.run = run

    from apkeep.adapter import APKeepAdapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("apkeep_ir_replay")
    log.setLevel(logging.ERROR)
    mapping = json.load(open(os.path.join(prefix, "mapping.json")))
    # The BDD path is the one that states the element structure (which devices
    # are forwarding elements, which are filters, where the NATs sit). The rule
    # list is assembled BEFORE the engine branch, so it is also exactly what the
    # NDD engine would have received.
    eng = APKeepAdapter(log, mapping=mapping, engine="bdd")
    try:
        with InProcessFaVe(eng) as fave:
            fave.replay(prefix)
            eng.single_universe()          # forces _build()
    except _Captured:
        pass
    if "rules" not in captured:
        raise SystemExit("the adapter never reached the engine for %s" % bench)
    captured["bench"] = bench
    captured["generators"] = dict(eng._generators)
    captured["probes"] = dict(eng._probes)
    with open(out_path, "w") as fh:
        fh.write(json.dumps(captured, indent=1, sort_keys=True) + "\n")
    return captured


def _edge_devices(edge):
    src, _sp, dst, _dp = edge.split()
    return src, dst


def _rule_device(rule):
    return rule.split()[2]


def devices(ir):
    out = set()
    for edge in ir["edges"]:
        out.update(_edge_devices(edge))
    out.update(ir["fwd_devices"])
    out.update(ir["device_filters"])
    out.update(ir["device_nats"] or {})
    out.update(_rule_device(r) for r in ir["rules"])
    return out


def prune(ir, keep):
    """ Keep only `keep`. An edge survives iff BOTH endpoints do. """
    out = dict(ir)
    out["edges"] = [e for e in ir["edges"]
                    if all(d in keep for d in _edge_devices(e))]
    out["rules"] = [r for r in ir["rules"] if _rule_device(r) in keep]
    out["fwd_devices"] = [d for d in ir["fwd_devices"] if d in keep]
    out["device_filters"] = [d for d in ir["device_filters"] if d in keep]
    out["device_nats"] = {d: list(p) for d, p in (ir["device_nats"] or {}).items()
                          if d in keep} or None
    out["generators"] = {k: v for k, v in ir["generators"].items() if k in keep}
    out["probes"] = {k: v for k, v in ir["probes"].items() if k in keep}
    return out


def _split_port(port):
    device, port_id = port.rsplit(".", 1)
    return device, port_id


def build(ir, engine, profile=None):
    if engine == "bdd":
        import apkeep.lib_apkeep as lib_apkeep
        jar = os.environ.get("FAVE_APKEEP_JAR")
        if jar:
            lib_apkeep._APKEEP_JAR = jar
        lib = lib_apkeep.LibAPKeep()
        lib.init_in_memory(ir["name"], ir["edges"], ir["fwd_devices"],
                           ir["device_acls"], ir["device_nats"],
                           device_filters=ir["device_filters"] or None,
                           bdd_table_size=ir["bdd_table_size"])
        if profile:
            os.environ["APKEEP_BUILD_PROFILE"] = profile
        lib.run(ir["rules"])
    else:
        from apkeep.lib_ndd import LibNDD
        lib = LibNDD()
        lib.build(ir["rules"], ir["edges"])
    return lib


def matrix(lib, ir):
    """ The source x probe reachability matrix, keyed "<source>|<probe>". """
    out = {}
    for probe, pport in sorted(ir["probes"].items()):
        pdev, pid = _split_port(pport)
        for source, sport in sorted(ir["generators"].items()):
            sdev, sid = _split_port(sport)
            out["%s|%s" % (source, probe)] = bool(
                lib.is_reachable(sdev, sid, pdev, pid))
    return out


def render(res, ir):
    sources = sorted(ir["generators"])
    probes = sorted(ir["probes"])
    lines = ["%-26s" % "src\\probe"
             + "".join("%-11s" % p.split(".", 1)[-1][:10] for p in probes)]
    for source in sources:
        lines.append(
            "%-26s" % source.split(".", 1)[-1][:25]
            + "".join("%-11s" % ("R" if res["%s|%s" % (source, p)] else ".")
                      for p in probes))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    dumper = sub.add_parser("dump", help="capture the engine-level IR")
    dumper.add_argument("--bench", default="wl_cloud")
    dumper.add_argument("--out", required=True)

    replay = sub.add_parser("replay", help="build the IR on one engine and query it")
    replay.add_argument("--ir", required=True)
    replay.add_argument("--engine", default="ndd", choices=("bdd", "ndd"))
    replay.add_argument("--keep", default=None,
                        help="comma-separated device substrings to keep")
    replay.add_argument("--profile", default=None,
                        help="APKEEP_BUILD_PROFILE path (bdd only)")
    replay.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if args.cmd == "dump":
        ir = _dump(args.bench, args.out)
        print("%s: %d rules, %d edges, %d sources, %d probes -> %s"
              % (args.bench, len(ir["rules"]), len(ir["edges"]),
                 len(ir["generators"]), len(ir["probes"]), args.out))
        return 0

    with open(args.ir) as fh:
        ir = json.load(fh)
    if args.keep:
        tags = args.keep.split(",")
        ir = prune(ir, {d for d in devices(ir)
                        if any(t in d for t in tags)
                        or "internet" in d or d.startswith("gw.")})
    label = "%s/%s" % (args.keep or "full", args.engine)
    print("%s  rules=%d edges=%d" % (label, len(ir["rules"]), len(ir["edges"])))
    sys.stdout.flush()

    started = time.time()
    lib = build(ir, args.engine, profile=args.profile)
    build_s = time.time() - started
    extra = {}
    if args.engine == "bdd":
        extra = {"ap_num": int(lib.ap_num()),
                 "elements": dict(lib.element_metrics())}
    started = time.time()
    res = matrix(lib, ir)
    query_s = time.time() - started

    print("build %.2f s   query %.2f s   %s"
          % (build_s, query_s, extra.get("ap_num", "")))
    print("reachable %d / %d" % (sum(res.values()), len(res)))
    print(render(res, ir))
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(json.dumps(
                dict(label=label, engine=args.engine, keep=args.keep,
                     build_s=round(build_s, 3), query_s=round(query_s, 3),
                     rules=len(ir["rules"]), edges=len(ir["edges"]),
                     reachable=sum(res.values()), cells=len(res),
                     matrix=res, **extra), indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
