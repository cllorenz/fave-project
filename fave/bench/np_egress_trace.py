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

""" NetPlumber egress trace (APKEEP_FAITHFUL_PLAN.md Phase 0c evidence tool).

Drives wl_stanford (optionally a router subset) through NetPlumber and attaches an
observation probe to a SINGLE chosen egress port, so you can see whether a given
source's flow reaches that exact port -- the bisection used to localise where a
flow dies inside the pipeline (an egress-only tap: NP probes observe traffic
leaving a source port, so only egress ports are observable). Optionally restrict a
source's injected traffic to one dst prefix to remove priority-slicing noise.

This is the tool behind APKEEP_STANFORD_NP_SPEC.md steps 3-4: it shows that on
the {bbra_rtr, rozb_rtr} subset, source.bbra restricted to dst=172.28.0.0/14 --
which has an explicit specific route toward rozb -- leaves bbra only via the /0
DEFAULT egress (mid.bbra_rtr.110004), never the specific rozb egress
(mid.bbra_rtr.110001): NP resolves priority by rule index, not longest prefix.

Usage:
  PYTHONPATH=. python bench/np_egress_trace.py \
      --routers bbra_rtr,rozb_rtr \
      --tap mid.bbra_rtr.110001 --tap mid.bbra_rtr.110004 \
      --src source.bbra_rtr --src-dst 172.28.0.0/14

Prints, per (source, probe), REACHES/blocked -- including the tap probes.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)             # bench/ for apkeep_convergence
import apkeep_convergence as C       # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--routers", help="comma-separated router bases (default: all)")
    ap.add_argument("--tap", action="append", default=[],
                    help="egress port to attach an observation probe to (repeatable)")
    ap.add_argument("--src", help="restrict this generator's injected dst (with --src-dst)")
    ap.add_argument("--src-dst", help="dst prefix to restrict --src to, e.g. 172.28.0.0/14")
    args = ap.parse_args(argv)

    logging.disable(logging.CRITICAL)
    from netplumber.lib_adapter import NetPlumberLibAdapter
    from util.in_process_driver import InProcessFaVe

    routers = set(args.routers.split(",")) if args.routers else None
    model = C._load_model()
    if routers is not None:
        model = C._filter_model(model, routers)

    if args.src and args.src_dst:
        for d in model["sources"]["devices"]:
            if d[0] == args.src:
                d[2] = ["ipv4_dst=%s" % args.src_dst]

    for i, port in enumerate(args.tap):
        name = "probe.tap%d" % i
        model["policies"]["devices"].append(
            [name, "probe", "existential", None, None, ["vlan=0"], None])
        model["policies"]["links"].append([port, "%s.1" % name, False])

    engine = NetPlumberLibAdapter(logging.getLogger("np_egress_trace"))
    with tempfile.TemporaryDirectory(prefix="np_trace_") as tmp:
        C._write_model(model, tmp)
        with InProcessFaVe(engine) as fave:
            fave.replay(tmp, files=C._FILES)
            sources = sorted(engine.generators)
            probes = sorted(engine.probes)
            rules = {p: [[s, False, []] for s in sources] for p in probes}
            fave.check_compliance(rules)

    sid = {info[1]: name for name, info in engine.generators.items()}
    pid = {info[1]: name for name, info in engine.probes.items()}
    not_reached = {(sid[s], pid[d]) for (s, d, _v, _c) in engine.get_compliance_results()
                   if s in sid and d in pid}

    tap_names = {"probe.tap%d" % i: port for i, port in enumerate(args.tap)}
    scope = args.routers or "full"
    inj = " (%s restricted to %s)" % (args.src, args.src_dst) if args.src and args.src_dst else ""
    print("== NP egress trace: routers=%s%s ==" % (scope, inj))
    for s in sources:
        for p in probes:
            label = "%s [%s]" % (p, tap_names[p]) if p in tap_names else p
            reaches = (s, p) not in not_reached
            print("  %-20s -> %-40s : %s" % (s, label, "REACHES" if reaches else "blocked"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
