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

""" `bench/compliance_checker.py`'s check syntax.

The syntax had no test at all, and the field-condition branch built every
`RuleField` with `negated=False` hardcoded -- so a check could negate its
REACHABILITY (`!`) but never a field VALUE, even though `RuleField` carries the
flag and `NetPlumberAdapter._expand_negated_field` already expands one into a
set of vectors.

That gap is what made the cloud dataset's query 04 inexpressible: *"from the
internet, on any port OTHER than 331, can anything reach this host?"*
(CLOUD_BENCH_PLAN.md §1.4). `f=!tcp_dst:331` closes it. The syntax is additive:
nothing that generates checks today emits a `!` inside `f=`.
"""

import unittest

from bench.compliance_checker import _parse_check


class TestCheckSyntax(unittest.TestCase):

    def test_a_plain_check_is_a_must_reach(self):
        src, dst, negated, cond = _parse_check('s=source.a p=probe.b')

        self.assertEqual(src, 'source.a')
        self.assertEqual(dst, 'probe.b')
        self.assertFalse(negated)
        self.assertEqual(cond, [])

    def test_a_leading_bang_negates_the_reachability(self):
        _src, _dst, negated, _cond = _parse_check('! s=source.a p=probe.b')

        self.assertTrue(negated)

    def test_a_field_condition_is_translated_to_its_match_field(self):
        _src, _dst, _negated, cond = _parse_check(
            's=source.a p=probe.b f=tcp_dst:331')

        self.assertEqual(cond, [{
            'name': 'packet.upper.dport', 'value': '331', 'negated': False,
        }])

    def test_a_field_condition_can_itself_be_negated(self):
        _src, _dst, _negated, cond = _parse_check(
            's=source.a p=probe.b f=!tcp_dst:331')

        self.assertEqual(cond, [{
            'name': 'packet.upper.dport', 'value': '331', 'negated': True,
        }])

    def test_the_two_negations_are_independent(self):
        """ Query 04's shape: the pair must NOT reach, considering only flows
        whose destination port is NOT 331. """
        _src, _dst, negated, cond = _parse_check(
            '! s=source.a p=probe.b f=!tcp_dst:331')

        self.assertTrue(negated)
        self.assertTrue(cond[0]['negated'])

    def test_several_conditions_keep_their_individual_polarity(self):
        _src, _dst, _negated, cond = _parse_check(
            's=source.a p=probe.b f=ip_proto:6 f=!tcp_dst:331')

        self.assertEqual([c['negated'] for c in cond], [False, True])

    def test_the_reverse_direction_port_resolves_to_the_source_port(self):
        """ A service-scoped permission in its RETURN direction is spelled
        `sport` by the policy matrix (Policy._condition_to_csv), against `port`
        for the forward one. Both must land on the right header field, or a
        bidirectional rule silently checks the same direction twice. """
        _src, _dst, _negated, cond = _parse_check(
            's=source.a p=probe.b f=sport:350')

        self.assertEqual(cond[0]['name'], 'packet.upper.sport')

    def test_the_forward_direction_port_is_unchanged(self):
        _src, _dst, _negated, cond = _parse_check(
            's=source.a p=probe.b f=port:350')

        self.assertEqual(cond[0]['name'], 'packet.upper.dport')

    def test_a_check_without_both_endpoints_is_refused(self):
        with self.assertRaises(AssertionError):
            _parse_check('s=source.a')


if __name__ == '__main__':
    unittest.main()
