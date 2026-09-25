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

""" Longest-prefix match, on BOTH Delta-net traces (CLOUD_BENCH_PLAN.md §3, D7).

Split out of `test_deltanet_model.py` and moved to the INTEGRATION tier
2026-09-25 (owner's call), on cost: the guard builds a 39,500-rule model per
trace and then walks packets through it. Moving these six tests out took the
fast tier from 105s to 74s, measured minutes apart; it added 19s to the
integration tier, which already runs in minutes. Nothing about it needs a
backend or a generated input -- it is
pure Python over the vendored CSVs -- so the tier choice is about runtime and
nothing else, which is why it says so here rather than leaving a reader to infer
a dependency that does not exist.

What it guards is §3's standing rule: **a FIB workload must prove its evidence
can see LPM.** `wl_airtel1` failed the mechanical version of that check --
inverted so the shortest prefix wins, it still reported 256 checks and 0
violations, because a switch-granularity reachability matrix asks an existential
question per pair and a misrouted prefix still leaves its 99 siblings arriving.
So the guard is here instead of in the compliance run, and it is a real one.
"""

import collections
import ipaddress
import unittest

from bench.deltanet.preparation import (
    build_model, device_name, in_port, out_port)
from bench.deltanet.topology import EXTERNAL_PORT
from test.test_deltanet_model import _load


class TestDeltanetLPM(unittest.TestCase):
    """ Longest-prefix-match, which the compliance run CANNOT check.

    FaVe does not reorder a table on its own. Priority is the rule index --
    `netplumber/adapter._calc_rule_index` shifts it and hands it to NetPlumber,
    where the lower index wins -- so `build_model` emitting longest-prefix-first
    IS the FIB semantics, and nothing downstream will repair it.

    **Measured 2026-09-22: the reachability matrix cannot catch that going
    wrong.** Inverting the ordering so the SHORTEST prefix wins still yields 256
    checks and 0 violations, because the matrix asks an existential question per
    switch pair and a misrouted prefix still leaves its 99 siblings arriving.
    That is the same shape as the wl_i2 defect AD6_PLAN.md 5.5 records,
    where 3,731 rules sat shadowed behind a containing prefix and every number
    computed on them looked fine.

    So the guard is here instead, and it is a real one: it resolves the model's
    own rules the way NetPlumber does -- lowest matching index wins, per
    in-port -- and follows the packet. Invert the ordering and it fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.inserts, cls.topology, cls.homed = _load()
        cls.model = build_model(cls.inserts, cls.topology, cls.homed)
        cls.nested = cls._nested_pairs(cls.homed)

    @staticmethod
    def _nested_pairs(homed):
        """ (specific, container) prefixes where one contains the other. """
        nets = {p: ipaddress.ip_network(p) for p in homed}
        return [(a, b) for a, na in nets.items() for b, nb in nets.items()
                if a != b and na.subnet_of(nb)]

    def _walk(self, routes, address, start, resolve='lpm'):
        """ Forward one address from a switch's external port.

        Resolves the way the BACKENDS now do. The table DECLARES
        longest-prefix-match (TABLE_SEMANTICS_PLAN.md S3b), and each positional
        backend orders it at translation time -- NetPlumber when it assigns the
        index it sends, ad6 when it emits the document -- so the winning rule is
        the one with the LONGEST matching prefix, ties broken by the emitted
        index. This used to sort by the index alone, because the generator
        re-prioritised the table so that the index carried the prefix rank; that
        repair is gone, and sorting by the index now would resolve the table the
        way nothing does.

        `resolve='shortest'` inverts it, which is what makes the guard a guard.
        """
        if resolve == 'lpm':
            key = lambda row: (-row[1].prefixlen, row[0])
        elif resolve == 'shortest':
            key = lambda row: (row[1].prefixlen, row[0])
        else:
            raise ValueError("unknown resolution %r" % resolve)
        table = collections.defaultdict(list)
        for device, _tid, index, match, actions, in_ports in routes:
            table[device].append((
                index,
                ipaddress.ip_network(match[0].split('=')[1]),
                actions[0].split('=')[1],
                set(in_ports),
            ))
        for device in table:
            table[device].sort(key=key)

        links = {link[0]: link[1] for link in self.model['topology']['links']}
        ip = ipaddress.ip_address(address)
        device = device_name(start)
        port = in_port(start, EXTERNAL_PORT)

        for _hop in range(2 * len(self.topology.switches) + 2):
            hit = next(
                (row for row in table[device]
                 if ip in row[1] and '%s.%d' % (device, port) in row[3]), None)
            if hit is None:
                return None                                    # no rule: dropped
            egress = hit[2]
            egress_device, egress_port = egress.rsplit('.', 1)
            switch = int(egress_device.split('.s')[1])
            if int(egress_port) == out_port(switch, EXTERNAL_PORT):
                return switch                                  # delivered
            if egress not in links:
                return None
            next_device, next_port = links[egress].rsplit('.', 1)
            device, port = next_device, int(next_port)
        return None

    def test_the_data_contains_a_pair_this_can_discriminate(self):
        """ Without one, the test below would pass on any ordering at all. """
        self.assertTrue(self.nested)
        self.assertTrue(
            [(a, b) for a, b in self.nested if self.homed[a] != self.homed[b]],
            "no nested pair is homed at two different switches, so LPM has no "
            "observable consequence in this snapshot and this guard is vacuous")

    def test_a_contained_prefix_is_delivered_to_its_own_home(self):
        for specific, container in self.nested:
            if self.homed[specific] == self.homed[container]:
                continue                     # same egress either way: no witness
            address = str(
                ipaddress.ip_network(specific).network_address + 1)
            for start in self.topology.switches:
                if start == self.homed[specific]:
                    continue
                self.assertEqual(
                    self._walk(self.model['routes'], address, start),
                    self.homed[specific],
                    "%s (inside %s) must be delivered where IT homes, not "
                    "where its container does" % (specific, container))

    def test_inverting_the_resolution_breaks_it(self):
        """ The guard guards: shortest-prefix-first must change the answer.

        It used to invert the INDEX, because the index was what carried the
        prefix rank. Now the declaration carries it and the walk resolves on
        prefix length, so inverting the index would change nothing and this
        would silently stop guarding anything. Inverting the RESOLUTION is the
        equivalent, and it is what proves the longest-prefix rule is
        load-bearing rather than incidental.
        """
        witnesses = [(a, b) for a, b in self.nested
                     if self.homed[a] != self.homed[b]]
        specific, container = witnesses[0]
        address = str(ipaddress.ip_network(specific).network_address + 1)
        start = next(s for s in self.topology.switches
                     if s != self.homed[specific])

        self.assertEqual(
            self._walk(self.model['routes'], address, start),
            self.homed[specific])
        self.assertEqual(
            self._walk(self.model['routes'], address, start, resolve='shortest'),
            self.homed[container])


class TestDeltanetLPMAirtel2(TestDeltanetLPM):
    """ The same guard on the second trace (CLOUD_BENCH_PLAN.md D7).

    **This is the only check in the suite that can tell the two traces apart.**
    The reachability matrix cannot: it is derived from the homing, the homing is
    identical, and `test_both_traces_state_the_same_matrix` asserts so. The LPM
    guard follows a packet, so it reads the 1,800 `(switch, prefix)` pairs that
    forward somewhere different -- which makes it the one place where airtel2
    could have failed where airtel1 passes.

    Measured 2026-09-25: it does not. Both nested prefix pairs are present in
    airtel2 and the same single one witnesses anything -- `117.53.131.0/24`
    inside `117.53.128.0/20`, homed apart -- so the guard is non-vacuous on this
    trace for the same reason it is on the first.
    """

    @classmethod
    def setUpClass(cls):
        cls.inserts, cls.topology, cls.homed = _load(1)
        cls.model = build_model(cls.inserts, cls.topology, cls.homed)
        cls.nested = cls._nested_pairs(cls.homed)


if __name__ == '__main__':
    unittest.main()
