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

""" Negated field conditions on a compliance check.

`_create_compliance_rules` built its condition with `_build_vector`, which
writes each field's value into one vector and IGNORES `RuleField.negated`. So a
check reading "considering only flows whose destination port is NOT 331" was
sent to NetPlumber as "flows whose destination port IS 331" -- the exact
opposite question, with nothing said about it.

That is the swallowed-sub-step pattern of TODO.md items 1i/1n/1p in its most
expensive form: the check RAN, produced a verdict, and the verdict answered a
different question. It surfaced on the cloud dataset's query 04
(CLOUD_BENCH_PLAN.md §1.4), where the reported violating flow carried
`packet.upper.dport=331` -- the very value the check was supposed to exclude.

The adapter already had the machinery (`_expand_negations`, used on rule
matches); the compliance path simply never reached for it.
"""

import logging
import unittest

from unittest import mock

from netplumber.adapter import NetPlumberAdapter
from rule.rule_model import RuleField


class TestNegatedComplianceConditions(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch('netplumber.adapter.jsonrpc')
        self.jsonrpc = patcher.start()
        self.addCleanup(patcher.stop)
        log = logging.getLogger('test_adapter_compliance')
        log.setLevel(logging.WARNING)
        self.adapter = NetPlumberAdapter(['SOCK'], log)
        self.adapter.generators['gen'] = ('gen', 101, None)
        self.adapter.probes['prb'] = ('prb', 202, None)

    def _rules(self, negated_check, fields):
        return self.adapter._create_compliance_rules(
            {'prb': [('gen', negated_check, fields)]})

    def test_a_plain_condition_yields_one_entry(self):
        res = self._rules(False, [RuleField('packet.upper.dport', '331')])

        self.assertEqual(len(res[202]), 1)
        src_id, must_reach, vector = res[202][0]
        self.assertEqual(src_id, 101)
        self.assertTrue(must_reach)
        self.assertIsNotNone(vector)

    def test_no_condition_yields_a_single_unconstrained_entry(self):
        res = self._rules(True, [])

        self.assertEqual(res[202], [(101, False, None)])

    def test_a_negated_condition_expands_into_the_complement(self):
        """ "must NOT reach, on any port other than 331" becomes one
        must-not-reach entry per vector of the complement, and every one of
        them has to hold. A 16-bit port field yields 16 vectors. """
        res = self._rules(True, [RuleField('packet.upper.dport', '331', negated=True)])

        self.assertEqual(len(res[202]), 16)
        self.assertTrue(all(src == 101 for src, _m, _v in res[202]))
        self.assertTrue(all(not must_reach for _s, must_reach, _v in res[202]))
        self.assertEqual(len(set(v for _s, _m, v in res[202])), 16)

    def test_the_complement_never_contains_the_excluded_value(self):
        """ The property the old code got backwards: not one expanded vector
        may still describe port 331. """
        excluded = self.adapter._build_vector(
            [RuleField('packet.upper.dport', '331')]).vector
        res = self._rules(True, [RuleField('packet.upper.dport', '331', negated=True)])

        for _src, _must_reach, vector in res[202]:
            self.assertNotEqual(vector, excluded)

    def test_a_negated_condition_on_a_must_reach_check_is_refused(self):
        """ Deliberately unsupported rather than quietly approximated.

        "must reach on some port other than 331" is an existential over the
        complement, but each expanded entry is checked independently, so
        emitting them all would demand reachability under EVERY complement
        vector -- a strictly stronger claim than the one asked for. Refusing is
        the only answer that cannot silently mean something else.
        """
        with self.assertRaises(ValueError) as ctx:
            self._rules(False, [RuleField('packet.upper.dport', '331', negated=True)])

        self.assertIn('negated', str(ctx.exception).lower())


if __name__ == '__main__':
    unittest.main()
