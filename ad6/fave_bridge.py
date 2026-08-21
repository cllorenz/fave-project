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
    """ An extra conjunct asserting the packet's src-IP lies in `cidr`,
    appended to an InstantiateEndToEnd instance exactly like DisjSrc/DisjDst
    (verified pattern, AD6_PLAN.md §4.4's synthetic forwarding test). Version
    is sniffed from the CIDR text (wl_ifi's generators are IPv4; wl_up's are
    IPv6 -- AD6_PLAN.md §5.1). """
    version = '6' if ':' in cidr else '4'
    elem = et.fromstring(
        '<ip xmlns="http://config" version="%s" direction="src">'
        '<address>%s</address></ip>' % (version, cidr)
    )
    XMLUtils.deannotate(elem)
    return XMLUtils.ConvertToVariables(elem)


# AD6_PLAN.md §4.2/§1.2/§1.4: FaVe's compliance-check semantics carry the
# stateful `<->>` query's third dimension as a `RuleField`-shaped condition
# in `cond` -- {"name": "related", "value": "0"|"1", ...} once it has
# travelled through the aggregator's real dispatch (RuleField.from_json,
# then Ad6Adapter._cond_to_json's JSON-safe echo of RuleField.to_json()).
# "0"=NEW / "1"=ESTABLISHED, matching fave/ad6/adapter.py:_RELATED and
# fave/iptables/generator.py's state-shell, which only ever emits these two
# values -- never a compound state. ad6 already carries the matching <state>
# vocabulary end to end (favemodel.py emits it on the ACL rule whose ctstate
# condition FaVe's model recorded); what's missing was the
# query-orchestration to force it here.
_RELATED_STATE = {"0": "NEW", "1": "ESTABLISHED"}


def _state_literals(cond):
    """ The individual (already-canonical) state-bit literals to force onto
    a query instance for a `{"name": "related", "value": "0"|"1"}` entry in
    `cond`, or [] if `cond` carries no state condition.

    MUST use XMLUtils.ConvertStateToVariables(value) directly (a flat
    conjunction of "state_<i>=<bit>" literals for the canonical STATES
    bit-vector) rather than a raw <state>value</state> element run through
    ConvertToVariables -- the latter produces ONE variable literally named
    "state_<value>", which only gets canonicalised into the shared bit-vector
    space by Instantiator._HandleOthers's build-time pass over the BASE
    model's own variables; a value that never appears in any rule (e.g.
    "NEW", when every ACL rule here only ever matches ctstate ESTABLISHED)
    would stay an unconnected, unconstrained atom and silently fail to
    conflict with an ESTABLISHED-only permit path. Calling
    ConvertStateToVariables ourselves reuses the exact same canonical
    "state_<i>=<bit>" names ad6 already assigns to ESTABLISHED via that same
    function, so forcing NEW here correctly conflicts with an
    ESTABLISHED-only branch regardless of whether "NEW" is otherwise used
    anywhere in the model. (Verified empirically before relying on it --
    appending the WHOLE <conjunction> XMLUtils.ConvertStateToVariables
    returns as one nested child of instance[0] does NOT work, because
    instance[0] is the already-CNF'd clause list from InstantiateBase: each
    top-level child must be its own flat literal/clause, so this flattens
    the conjunction's children before appending. See
    ad6/FAVE_CHANGES.md and AD6_PLAN.md §4.2 for the fixture that pinned
    this down.) """
    literals = []
    for c in (cond or []):
        if not isinstance(c, dict) or c.get("name") != "related":
            continue
        state = _RELATED_STATE.get(str(c.get("value")))
        if state is not None:
            literals.extend(list(XMLUtils.ConvertStateToVariables(state)))
    return literals


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
        destination = favemodel.query_destination_key(dst_dev, dst_port, ir)
        instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source, destination)
        if q.get('src_cidr') and favemodel._is_constrained(q['src_cidr']):
            instance[0].append(_seed_conjunct(q['src_cidr']))
        for literal in _state_literals(q.get('cond')):
            instance[0].append(literal)
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
