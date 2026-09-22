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

""" wl_deltanet's FPL inventory and policy: the reachability matrix (§2.5).

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

from typing import Dict, List

from bench.wl_deltanet.deltanet_preparation import endpoint_name
from bench.wl_deltanet.deltanet_topology import Topology


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

    One rule per ordered pair whose destination homes at least one prefix.
    Unidirectional `--->` rather than `<-->`: the two directions are different
    facts about a destination-routed data plane, and stating them as one would
    assert a symmetry nothing here guarantees. Each direction gets its own rule,
    so the matrix is stated twice over rather than half as often.
    """
    targets = homing_switches(homed)
    rules = [
        '    %s ---> %s' % (role_name(source), role_name(target))
        for target in targets
        for source in topology.switches
        if source != target
    ]

    return _POLICY_HEADER + '\n'.join(rules) + '\nend\n'


_HEADER = """\
# FPL inventory for wl_deltanet (CLOUD_BENCH_PLAN.md §2.5) -- GENERATED by
# bench/wl_deltanet/deltanet_policy.py, do not edit.
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
# FPL policy for wl_deltanet (CLOUD_BENCH_PLAN.md §2.5) -- GENERATED by
# bench/wl_deltanet/deltanet_policy.py, do not edit.
#
# THIS POLICY IS OURS, NOT THE DATA SET'S. Delta-net ships no statement of
# intent, and its paper's own verification goals were different ones:
# forwarding loops, and "what is the fate of packets that are using a link that
# fails". So this matrix is an expectation we wrote, and agreement with it is a
# consistency property -- it catches a converter bug or an engine disagreement,
# never a shared misreading of the trace.
#
# The intent: a transit AS in which every border network can reach every other
# border network. One rule per ordered pair whose destination homes at least
# one prefix; s8 and s9 home none, so the 30 cells ending there are left to the
# default deny and become must-NOT-reach checks.

describe policies (default: deny)
"""
