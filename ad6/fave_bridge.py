#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

""" Subprocess bridge driven by fave/ad6/adapter.py (AD6_PLAN.md §4.2/§4.4).

Reads a JSON payload {"ir": <Ad6Adapter._build_ir() output>, "queries": [...]},
builds the ad6 Kripke/SAT model via src.parser.favemodel, answers every query
(source->probe existential reachability, src-IP seeded when the source has one),
and writes back [{"source","probe","reachable","negated","cond"}, ...].

Usage: python3 fave_bridge.py --in payload.json --out results.json
(run with cwd=ad6/, exactly like main.py -- see fave/ad6/adapter.py).
"""

import argparse
import json
import sys

sys.setrecursionlimit(10 ** 6)

import lxml.etree as et  # noqa: E402  (after recursionlimit, matches main.py's ordering)

from src.core.instantiator import Instantiator  # noqa: E402
from src.parser import favemodel  # noqa: E402
from src.solver.pycosat import PycoSATAdapter  # noqa: E402
from src.xml.xmlutils import XMLUtils  # noqa: E402


def _seed_conjunct(cidr):
    """ An extra conjunct asserting the packet's src-IPv4 lies in `cidr`,
    appended to an InstantiateEndToEnd instance exactly like DisjSrc/DisjDst
    (verified pattern, AD6_PLAN.md §4.4's synthetic forwarding test). """
    elem = et.fromstring(
        '<ip xmlns="http://config" version="4" direction="src">'
        '<address>%s</address></ip>' % cidr
    )
    XMLUtils.deannotate(elem)
    return XMLUtils.ConvertToVariables(elem)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infile', required=True)
    parser.add_argument('--out', dest='outfile', required=True)
    args = parser.parse_args(argv)

    with open(args.infile) as raw:
        payload = json.load(raw)
    ir = payload['ir']
    queries = payload['queries']

    config = favemodel.build_config(ir)
    XMLUtils.deannotate(config)
    kripke, encoding = favemodel.instantiate_base(config, ir)
    # Mutual exclusion between generators (at most one of favemodel.init_keys()
    # fires per query) is enforced by KripkeUtils._CreateInitConstraints on
    # the base model itself -- no per-query exclusivity assertion needed here
    # (there used to be one; removed once the ad6-core off-by-one it was
    # working around was fixed and verified sufficient on its own, see
    # ad6/FAVE_CHANGES.md §8).

    solver = PycoSATAdapter()
    results = []
    for q in queries:
        dst_dev, dst_port = favemodel._attachment(q['probe'], ir)
        source = favemodel.gen_entry_key(q['source'])
        destination = favemodel.iface_key(dst_dev, dst_port) + "_out"
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, destination)
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            instance[0].append(_seed_conjunct(q['src_cidr']))
        reachable = bool(solver.Solve(instance))
        results.append({
            "source": q['source'], "probe": q['probe'],
            "reachable": reachable, "negated": q['negated'], "cond": q['cond'],
        })

    with open(args.outfile, 'w') as raw:
        json.dump(results, raw)
    return 0


if __name__ == '__main__':
    sys.exit(main())
