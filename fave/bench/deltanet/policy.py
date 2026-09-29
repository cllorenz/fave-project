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

""" A Delta-net workload's FPL inventory and policy: the reachability
    matrix (§2.5).

**The data set ships no policy, and this one is therefore ours.** `wl_cloud`
could compile the dataset's own 26x26 ACL matrix because `README.txt` states
one; nothing here states any intent at all. So the matrix below is an
expectation WE wrote, over an inventory derived from the traces, and every
result from it is a consistency property rather than an oracle. §2.5 says so at
length, and `benchmark.py` stamps it with every run.

**And the paper's own verification goals were different ones** -- forwarding
loops (§4.3.1) and "what is the fate of packets using a link that fails"
(§4.3.2), one query per link. Neither is a reachability matrix. Reproducing
those would be reproducing the EXPERIMENT; this reproduces the DATA under a
property of our choosing, which is the weaker claim and is recorded as such in
CLOUD_BENCH_PLAN.md §2.5.

The inventory is one role per switch -- the network reachable behind that
switch's border router -- and one endpoint per role. Both are forced:

  * a role per PREFIX would be 1,400 roles and, since checks expand over pairs
    of endpoints, about two million checks;
  * `ipv4` is omitted rather than guessed. A homing switch stands for 100
    prefixes and the attribute carries one, so `wl_cloud`'s rule applies -- the
    attribute is emitted only when it is the whole truth, and the description
    carries the count instead. It also decides `_abstracts_a_subnet`, and a
    self-check here would ask whether a border network reaches itself, which
    this data plane says nothing about.

**Two switches are sources but never destinations.** s8 and s9 home no prefix
(§2.3), so nothing is addressed to them and the matrix cannot authorise a cell
that ends there. They keep their roles, because traffic does ENTER at both --
each has a rule for all 1,400 prefixes at its external port -- and the default
deny then turns those 30 cells into must-NOT-reach checks. That is what stops
the matrix being an all-reachable mesh, which `AD6_PLAN.md` §5.5 records as
evidence any over-approximating engine satisfies for free.
"""

from __future__ import annotations

import itertools

from typing import Dict, List, Set, Tuple

from bench.deltanet.preparation import endpoint_name
from bench.deltanet.topology import Topology


def role_name(switch: int) -> str:
    return 's%d' % switch


def homing_switches(homed: Dict[str, int]) -> List[int]:
    """ The switches a packet can be addressed to, ascending. """
    return sorted(set(homed.values()))


def role_endpoints(topology: Topology) -> Dict[str, List[str]]:
    """ {role: [model endpoint]} -- the `--inventory-mapping`. """
    return {role_name(s): [endpoint_name(s)] for s in topology.switches}


def emit_inventory(topology: Topology, homed: Dict[str, int]) -> str:
    """ `roles_and_services.txt`: one role per switch, and no services.

    There are NO services because there are no transport fields anywhere in the
    data (§2.1) -- the whole model matches `ipv4_dst` and nothing else. A
    service declared here would be a match condition the data plane cannot
    express, and every check carrying it would pass or fail for a reason the
    data set never states.

    `def` and not `describe`: `inventorygen.py` matches only `def` when it
    extends a role with its `hosts`, which `wl_cloud`'s inventory records as a
    coincidence worth not relying on.
    """
    counts: Dict[int, int] = {}
    for switch in homed.values():
        counts[switch] = counts.get(switch, 0) + 1

    blocks = [
        '\n'.join([
            '# %s' % (
                'homes %d prefixes' % counts[switch] if switch in counts
                else 'homes NO prefix: a source only, never a destination'),
            'def role %s' % role_name(switch),
            "    description = 'Networks behind the border router of switch "
            "%d, %d prefixes'" % (switch, counts.get(switch, 0)),
            '    hosts       = [%r]' % endpoint_name(switch),
            'end',
        ]) for switch in topology.switches
    ]

    return _HEADER + '\n\n'.join(blocks) + '\n'


def emit_policy(topology: Topology, homed: Dict[str, int]) -> str:
    """ `reach.txt`: every border network reaches every ADDRESSABLE other one.

    **`<-->` wherever the permission really is symmetric, `--->` only where it
    is not.** Between two addressable switches the matrix permits both
    directions, so one bidirectional rule states exactly what two unidirectional
    ones would -- `policy_builder` expands a serviceless `<-->` into the two
    unconditional permissions, and the compiled matrix is byte-identical.

    What the shorter form buys is not brevity. The 28 rules that CANNOT be
    written `<-->` are the whole s8/s9 finding, and stating everything
    unidirectionally hides them among 210 identical-looking lines.

    A first version did write all 210 as `--->`, reasoning that "the two
    directions are different facts and stating them as one would assert a
    symmetry nothing here guarantees". That was borrowed from `wl_cloud`, where
    it is sound for two reasons that do not hold here: its ACLs are stateless,
    so a symmetric operator would have claimed something about conntrack, and
    its matrix is genuinely asymmetric cell by cell. This matrix is symmetric
    wherever both ends are addressable -- by construction, since this policy is
    what asserts it -- and it carries no services at all.

    `<->>` stays wrong for a third reason, and that one does hold: it makes the
    return direction conditional on RELATED,ESTABLISHED, which is a claim about
    connection tracking in a data plane that matches nothing but a destination
    prefix.
    """
    targets = homing_switches(homed)

    rules = [
        '    %s <--> %s' % (role_name(left), role_name(right))
        for left, right in itertools.combinations(targets, 2)
    ]
    rules.extend(
        '    %s ---> %s' % (role_name(source), role_name(target))
        for source in topology.switches if source not in targets
        for target in targets
    )

    return _POLICY_HEADER + '\n'.join(rules) + '\nend\n'


def emit_walked_policy(topology: Topology,
                       reached: Set[Tuple[str, str]]) -> str:
    """ `reach.txt` for a matrix the homing cannot state: exactly the
    `(source, probe)` endpoint pairs `fib_walk` found reached (§2.15).

    `<-->` where both directions are reached, `--->` where one is, the same
    mix as `emit_policy` and for the same reason: the one-way cells are the
    finding. A role reaching ITSELF -- a hairpin through a neighbour, which
    longest-prefix fallback produces -- is `R <--> R`, and that emits no check
    at all: `reach_csv_to_checks` keeps a self-pair only for a role that
    abstracts a subnet, and these declare no address. So a reached diagonal is
    UNCHECKED, and only an unreached one is asserted, as must-NOT-reach. Said
    here because a count of checks that silently omits nine cells is the kind
    of denominator §3 asks to be stated.
    """
    names = {endpoint_name(s): role_name(s) for s in topology.switches}
    unknown = sorted({e for pair in reached for e in pair} - set(names))
    if unknown:
        raise ValueError("reached endpoints %s are not switches of this "
                         "topology" % unknown)
    roles = [names[endpoint_name(s)] for s in topology.switches]
    pairs = {(names[a], names[b]) for a, b in reached}

    rules = ['    %s <--> %s' % (r, r) for r in roles if (r, r) in pairs]
    for left, right in itertools.combinations(roles, 2):
        there, back = (left, right) in pairs, (right, left) in pairs
        if there and back:
            rules.append('    %s <--> %s' % (left, right))
        elif there:
            rules.append('    %s ---> %s' % (left, right))
        elif back:
            rules.append('    %s ---> %s' % (right, left))

    return _WALKED_POLICY_HEADER + '\n'.join(rules) + '\nend\n'


def directed_pairs(policy: str) -> Set[Tuple[str, str]]:
    """ Every ordered `(from, to)` a policy permits, its operators expanded.

    The equivalence that lets `emit_policy` mix the two operators, checked
    rather than trusted: `<-->` contributes both directions and `--->` one.
    """
    pairs: Set[Tuple[str, str]] = set()
    for line in policy.splitlines():
        line = line.strip()
        if line.startswith('#') or not line:
            continue
        for operator in ('<-->', '--->'):
            if ' %s ' % operator not in line:
                continue
            left, _, right = line.partition(' %s ' % operator)
            pairs.add((left.strip(), right.strip()))
            if operator == '<-->':
                pairs.add((right.strip(), left.strip()))
            break
    return pairs

_HEADER = """\
# FPL inventory for a Delta-net workload (CLOUD_BENCH_PLAN.md §2.5) -- GENERATED
# by bench/deltanet/policy.py, do not edit.
#
# One role per Delta-net switch: the networks reachable behind that switch's
# Quagga border router. The role's endpoint is the generator/probe pair the
# model attaches to the switch's external port (port 1), so a check about two
# roles asks exactly "does traffic entering the network at i leave it at j".
#
# NO SERVICES. The data set carries no transport fields at all -- every rule in
# it matches a destination prefix and nothing else -- so a service here would be
# a condition the data plane cannot express.
#
# `ipv4` is not declared. A homing switch stands for 100 prefixes and the
# attribute carries one; wl_cloud's rule is that it is emitted only when it is
# the whole truth. The prefix count is in the description instead.

"""

_POLICY_HEADER = """\
# FPL policy for a Delta-net workload (CLOUD_BENCH_PLAN.md §2.5) -- GENERATED
# by bench/deltanet/policy.py, do not edit.
#
# THIS POLICY IS OURS, NOT THE DATA SET'S. Delta-net ships no statement of
# intent, and its paper's own verification goals were different ones:
# forwarding loops, and "what is the fate of packets that are using a link that
# fails". So this matrix is an expectation we wrote, and agreement with it is a
# consistency property -- it catches a converter bug or an engine disagreement,
# never a shared misreading of the trace.
#
# The intent: a transit AS in which every border network can reach every other
# border network.
#
# `<-->` between two ADDRESSABLE switches, because there the permission really
# is symmetric and one rule says what two would. `--->` only from s8 and s9,
# which home no prefix and can therefore send but never receive, so the 30
# cells ending at them fall to the default deny and become must-NOT-reach
# checks. The mix is the point: the rules that CANNOT be written `<-->` are
# exactly the finding, and 210 identical-looking unidirectional lines bury it.
#
# NOT `<->>`, which would make the return direction conditional on
# RELATED,ESTABLISHED -- a claim about connection tracking in a data plane that
# matches nothing but a destination prefix.

describe policies (default: deny)
"""

_WALKED_POLICY_HEADER = """\
# FPL policy for a port-free Delta-net workload (CLOUD_BENCH_PLAN.md §2.15) --
# GENERATED by bench/deltanet/policy.py from bench/deltanet/fib_walk.py, do not
# edit.
#
# THIS POLICY IS OURS, NOT THE DATA SET'S, and it is not even an intent: it is
# the matrix a reference walk of the MODEL predicts, one walk per address region
# and source, longest prefix first. Agreement with it says two implementations
# of the forwarding semantics agree; it cannot catch a misreading of the trace
# that the model and the walk share.
#
# Why not the homing, as airtel's is: here a router with no rule for a prefix
# falls back to the longest containing prefix it DOES carry, and that reaches
# cells the homing cannot state -- one-way reachability between two routers
# with no link, and a border network reaching itself through a neighbour.
#
# `R <--> R` below is such a hairpin. It compiles to NO check (these roles
# declare no address), so a reached diagonal is unchecked; an unreached one is a
# must-NOT-reach check, as is every cell not stated here.

describe policies (default: deny)
"""
