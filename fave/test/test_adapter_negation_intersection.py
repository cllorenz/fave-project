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

""" Several negated constraints on ONE field.

`_expand_negations` keyed its per-field vectors by field NAME
(`field_vectors[field.name] = ...`), so two negated fields of the same name
left only the last one standing: `[!dport:80, !dport:22]` produced exactly the
vectors of `[!dport:22]`, and the `!80` vanished.

THE ERROR DIRECTION IS A FALSE VIOLATION, not a silent weakening. The survivor
`¬22` is a strict SUPERSET of the intended `¬80 ∧ ¬22` -- it contains 80. Used
as a must-not-reach condition it therefore forbids more than the policy does,
and port 80, which the policy PERMITS, makes the check fire.

WHERE IT COMES FROM. "Only HTTP and SSH may reach this host" is checked as
"nothing outside {80, 22} reaches it", and the complement of a union is the
INTERSECTION of complements. Multiple check entries OR together (overlap
distributes over union), so that intersection has to be materialised as a union
of vectors before it can be sent. A firewall rule never carries two negated
matches on one field, which is why the case sat unexercised -- but a policy cell
permitting two services does, and `wl_example` has one today:
`Office <->> WebServer.HTTP` and `Office <->> WebServer.SSH` meet in the cell
`(protocol:tcp;port:80|protocol:tcp;port:22)`, whose complement is this shape.
That is a claim about a workload rather than about this module, so it is
asserted in test_wl_example_policy_artifacts.py -- without it these fixtures
could outlive the only thing in the tree that produces what they describe.
"""

import logging
import unittest

from unittest import mock

from netplumber.adapter import NetPlumberAdapter
from netplumber.vector import Vector, set_field_in_vector
from rule.rule_model import Match, RuleField


_DPORT = 'packet.upper.dport'
_PROTO = 'packet.ipv6.proto'


def _overlaps(one, other):
    return all(
        a == 'x' or b == 'x' or a == b for a, b in zip(one, other))


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch('netplumber.adapter.jsonrpc')
        self.jsonrpc = patcher.start()
        self.addCleanup(patcher.stop)
        log = logging.getLogger('test_negation_intersection')
        log.setLevel(logging.WARNING)
        self.adapter = NetPlumberAdapter(['SOCK'], log)

    def _port(self, value):
        """A full-width vector pinning the destination port to `value`."""
        vector = Vector(self.adapter.mapping.length, preset='x')
        set_field_in_vector(
            self.adapter.mapping, vector, _DPORT, '{:016b}'.format(value))
        return vector.vector

    def _hits(self, vectors, value):
        return any(_overlaps(v.vector, self._port(value)) for v in vectors)


class TestTwoNegationsOnOneField(_Base):

    def setUp(self):
        super().setUp()
        self.both = self.adapter._expand_negations(Match([
            RuleField(_DPORT, '80', negated=True),
            RuleField(_DPORT, '22', negated=True),
        ]))

    def test_neither_permitted_value_is_admitted(self):
        """ The property that was broken: 80 used to overlap the result. """
        self.assertFalse(self._hits(self.both, 80))
        self.assertFalse(self._hits(self.both, 22))

    def test_a_third_value_is_still_admitted(self):
        """ ...and the complement must not collapse to nothing either. """
        self.assertTrue(self._hits(self.both, 443))
        self.assertTrue(self._hits(self.both, 0))
        self.assertTrue(self._hits(self.both, 65535))

    def test_the_result_differs_from_either_negation_alone(self):
        one = self.adapter._expand_negations(
            Match([RuleField(_DPORT, '22', negated=True)]))

        self.assertNotEqual(
            sorted(v.vector for v in self.both), sorted(v.vector for v in one))

    def test_every_emitted_vector_is_satisfiable(self):
        """ Pairs that contradict each other are dropped rather than emitted as
        vectors nothing can match. """
        for vector in self.both:
            self.assertNotIn(None, [vector.vector])
            self.assertTrue(set(vector.vector) <= set('01x'))


class TestTheUnaffectedCases(_Base):
    """ The shapes that worked before and must keep working. """

    def test_one_negation_on_one_field_is_unchanged(self):
        vectors = self.adapter._expand_negations(
            Match([RuleField(_DPORT, '22', negated=True)]))

        self.assertFalse(self._hits(vectors, 22))
        self.assertTrue(self._hits(vectors, 80))

    def test_negations_on_DIFFERENT_fields_still_cross_product(self):
        vectors = self.adapter._expand_negations(Match([
            RuleField(_DPORT, '22', negated=True),
            RuleField(_PROTO, '6', negated=True),
        ]))

        self.assertTrue(vectors)
        self.assertFalse(self._hits(vectors, 22))

    def test_a_positive_field_mixed_with_a_negated_one(self):
        """ The complement check's real shape: `related:0 AND NOT tcp/22`. """
        vectors = self.adapter._expand_negations(Match([
            RuleField(_PROTO, '6'),
            RuleField(_DPORT, '22', negated=True),
        ]))

        self.assertTrue(vectors)
        self.assertFalse(self._hits(vectors, 22))

    def test_an_unsatisfiable_intersection_yields_no_vectors(self):
        """ A field required to differ from a value AND to equal it describes
        nothing, so it must contribute nothing rather than a vector that
        matches everything. """
        vectors = self.adapter._expand_negations(Match([
            RuleField(_DPORT, '22'),
            RuleField(_DPORT, '22', negated=True),
        ]))

        self.assertEqual(vectors, [])


class TestManyNegationsOnOneField(_Base):

    def test_three_values_are_all_excluded(self):
        vectors = self.adapter._expand_negations(Match([
            RuleField(_DPORT, str(v), negated=True) for v in (80, 22, 443)
        ]))

        for excluded in (80, 22, 443):
            self.assertFalse(self._hits(vectors, excluded), excluded)
        self.assertTrue(self._hits(vectors, 8080))


if __name__ == '__main__':
    unittest.main()
