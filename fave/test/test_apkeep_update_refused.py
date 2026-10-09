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

""" APKeepAdapter refuses a model change once its engine is built.

The adapter buffers the model and builds the engine ONCE, on the first
check_compliance, then releases the buffers. What a change after that did,
measured on the adapter as of 2026-10-08:

* a forwarding RULE crashed with `AttributeError: 'NoneType' object has no
  attribute 'setdefault'` -- loud, because `_release_build_buffers` sets the
  buffers to None for exactly that reason, but naming nothing about updates;
* a link, generator, probe, table or deletion was ACCEPTED and never reached
  the engine, so every later check answered from the model as it had been.
  The first test below is that, measured: a link that makes probe.C reachable
  -- as the same model built from zero confirms -- left it unreachable.

Both now raise `UpdateRefused`, which says what happened. `remove_link` never
removed anything, before the build or after, and is refused at any time (TODO
item 31's incremental axis).

The guard is the `_built` flag `_build` sets on both engines, so the BDD engine
drives it here: it is the one that starts in a shared JVM next to the other
integration tests.
"""

import logging
import unittest

from types import SimpleNamespace

from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from aggregator.abstract_engine import UpdateRefused
from apkeep.adapter import APKeepAdapter, available
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'


def _logger():
    log = logging.getLogger("test_apkeep_update_refused")
    log.setLevel(logging.WARNING)
    return log


def _switch_rule(idx, out_port):
    return Rule('sw', 'sw.1', idx, ['sw.1', 'sw.2'],
                Match([RuleField(_DST, '10.0.0.0/8')]), [Forward([out_port])])


def _network():
    """ source.A -> r -> sw -> probe.B; probe.C hangs off sw.2, which no rule
    forwards to, so source.A cannot reach it. """
    adapter = APKeepAdapter(_logger(), faithful_vlan=False, engine='bdd')
    router = SimpleNamespace(node='r', tables={'r.routing': [
        Rule('r', 'r.routing', 0, ['r.routing_in'],
             Match([RuleField(_DST, '10.0.0.0/8')]),
             [Rewrite([RuleField('out_port', 'r.2_egress')]),
              Forward(['r.routing_out'])])
    ]})
    switch = SimpleNamespace(node='sw', tables={'sw.1': [_switch_rule(0, 'sw.3')]})
    for model in (router, switch):
        adapter.add_tables(model)
        adapter.add_rules(model)
    for sport, dport in [("source.A.1", "r.1"), ("r.2", "sw.1"),
                         ("sw.3", "probe.B.1"), ("sw.2", "probe.C.1")]:
        adapter.add_link(sport, dport)
    adapter.add_generator(SimpleNamespace(node='source.A'))
    adapter.add_probe(SimpleNamespace(node='probe.B'))
    adapter.add_probe(SimpleNamespace(node='probe.C'))
    return adapter


_C_MUST_BE_REACHED = {"probe.C": [("source.A", False, None)]}


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestAPKeepUpdateRefused(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.adapter = _network()
        cls.adapter.check_compliance(_C_MUST_BE_REACHED)   # builds the engine
        cls.before = cls.adapter.get_compliance_results()

    def test_the_update_that_would_change_a_verdict_is_refused(self):
        # Wiring sw.3 to probe.C makes probe.C reachable: built from zero, this
        # model reports no violation. Accepted after the build, the link never
        # reached the engine and the check kept reporting probe.C unreachable.
        self.assertEqual(self.before, [("source.A", "probe.C", True, "")])
        with self.assertRaises(UpdateRefused) as ctx:
            self.adapter.add_link("sw.3", "probe.C.1")
        self.assertIn('add_link(sw.3, probe.C.1)', str(ctx.exception))

        # The refusal leaves the built model answering as it did.
        self.adapter.clear_results()
        self.adapter.check_compliance(_C_MUST_BE_REACHED)
        self.assertEqual(self.adapter.get_compliance_results(), self.before)

    def test_the_link_does_change_the_verdict_when_built_from_zero(self):
        # The control for the test above: without it, "refused" could be
        # protecting a verdict the update would not have changed anyway.
        adapter = _network()
        adapter.add_link("sw.3", "probe.C.1")
        adapter.check_compliance(_C_MUST_BE_REACHED)
        self.assertEqual(adapter.get_compliance_results(), [])

    def test_a_rule_update_is_refused_by_name(self):
        # It used to fail as an AttributeError on a released buffer.
        update = SimpleNamespace(node='sw', tables={'sw.1': [_switch_rule(1, 'sw.2')]})
        with self.assertRaises(UpdateRefused) as ctx:
            self.adapter.add_rules(update)
        self.assertIn('add_rules(sw)', str(ctx.exception))

    def test_every_model_change_after_the_build_is_refused(self):
        new = SimpleNamespace(node='x', tables={})
        changes = [
            ('add_tables', lambda: self.adapter.add_tables(new)),
            ('add_links_bulk',
             lambda: self.adapter.add_links_bulk([("sw.4", "probe.C.1")])),
            ('add_generator',
             lambda: self.adapter.add_generator(SimpleNamespace(node='source.Z'))),
            ('add_generators_bulk', lambda: self.adapter.add_generators_bulk(
                [SimpleNamespace(node='source.Z')])),
            ('add_probe',
             lambda: self.adapter.add_probe(SimpleNamespace(node='probe.Z'))),
            ('delete_generator', lambda: self.adapter.delete_generator('source.A')),
            ('delete_probe', lambda: self.adapter.delete_probe('probe.B')),
            ('remove_link', lambda: self.adapter.remove_link("sw.2", "probe.C.1")),
        ]
        for name, change in changes:
            with self.subTest(op=name):
                with self.assertRaises(UpdateRefused):
                    change()
        # And none of them half-applied: both endpoints are still named.
        self.assertIn('source.A', self.adapter._generators)
        self.assertIn('probe.B', self.adapter._probes)


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestAPKeepRemoveLinkBeforeBuild(unittest.TestCase):

    def test_remove_link_is_refused_before_the_build_too(self):
        # It edited the aggregator's adjacency, never `_edges`, which the model
        # is built from -- so even before the build the link stayed.
        adapter = _network()
        with self.assertRaises(UpdateRefused):
            adapter.remove_link("sw.2", "probe.C.1")
        self.assertIn("sw 2 probe.C 1", adapter._edges)


if __name__ == '__main__':
    unittest.main()
