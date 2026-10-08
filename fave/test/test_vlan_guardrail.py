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

""" The VLAN guardrail's DENOMINATOR -- what `--no-vlan` actually relaxed.

`MEASUREMENT_RUN_PLAN.md` §5.4's guardrail asks whether a workload's CHECK SET
can see a dimension at all, by running a second arm that relaxes it. For VLAN
that arm is `--no-vlan`, and relaxing can only ADD reachability, so an
unchanged verdict reads as "this check set is blind to VLAN".

**That reading is only valid against a denominator.** `faithful_vlan: false`
alone cannot distinguish a run that relaxed 77,451 egress rewrites from one on
a workload that never had a VLAN stage -- and the second would read as a
passing guard. The LPM arm learned this on `wl_cloud`, which declares no LPM
table: its verdict could not move, and only the per-table rule count made that
visible rather than mistakable for a result.

So the count is taken in BOTH arms, scoped to the HSA stages where
`faithful_vlan` actually changes the model, and is read by neither build.

Pure Python: builds no engine and starts no JVM (`__new__`, since
`APKeepAdapter.__init__` constructs a LibNDD).
"""

import logging
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..'))

from apkeep.adapter import APKeepAdapter                     # noqa: E402
from bench.cell_run import _VLAN_DENOM                       # noqa: E402
from rule.rule_model import Forward, Match, Rewrite, Rule, RuleField  # noqa: E402

_VLAN = 'packet.ether.vlan'
_DST = 'packet.ipv4.destination'


def _counter(faithful=True):
    """ An adapter far enough constructed to count, and no further. """
    engine = APKeepAdapter.__new__(APKeepAdapter)
    engine._faithful_vlan = faithful
    engine._vlan_rewrite_rules = 0
    engine._vlan_admission_rules = 0
    engine._vlan_stage_devices = set()
    engine.logger = logging.getLogger('test_vlan_guardrail')
    return engine


def _rule(node, match=(), actions=()):
    return Rule(node, node + '.1', 0,
                match=Match([RuleField(n, v) for n, v in match]),
                actions=list(actions))


class TestTheDenominatorCountsWhatFaithfulModeWouldModel(unittest.TestCase):

    def test_an_egress_vlan_rewrite_counts(self):
        engine = _counter()
        engine._count_vlan_facts('out.chic', _rule(
            'out.chic', match=[(_DST, '140.112.0.0/14')],
            actions=[Rewrite([RuleField(_VLAN, '10')]),
                     Forward(['out.chic.220045'])]))
        self.assertEqual(engine._vlan_rewrite_rules, 1)
        self.assertEqual(engine._vlan_admission_rules, 0)

    def test_an_ingress_vlan_admission_counts(self):
        engine = _counter()
        engine._count_vlan_facts('in.kans', _rule(
            'in.kans', match=[(_VLAN, '10')],
            actions=[Forward(['in.kans.400022'])]))
        self.assertEqual(engine._vlan_admission_rules, 1)
        self.assertEqual(engine._vlan_rewrite_rules, 0)

    def test_an_ingress_vlan_rule_that_DROPS_is_not_an_admission(self):
        # A rule with no forward denies; counting it would inflate the
        # denominator with exactly the rules the faithful path does not model
        # as admission gates.
        engine = _counter()
        engine._count_vlan_facts('in.kans', _rule(
            'in.kans', match=[(_VLAN, '99')], actions=[]))
        self.assertEqual(engine._vlan_admission_rules, 0)

    def test_a_rewrite_of_something_else_is_not_a_vlan_fact(self):
        engine = _counter()
        engine._count_vlan_facts('out.chic', _rule(
            'out.chic', actions=[Rewrite([RuleField(_DST, '10.0.0.1')]),
                                 Forward(['out.chic.1'])]))
        self.assertEqual(
            (engine._vlan_rewrite_rules, engine._vlan_admission_rules), (0, 0))

    def test_only_the_HSA_STAGES_count(self):
        """ Outside `in.`/`mid.`/`out.` a VLAN match is carried by the
        first-match table whatever the flag says, so counting it would inflate
        a denominator that means "what this run relaxed". """
        engine = _counter()
        for node in ('tum_switch', 'pgf.uni-potsdam.de', 'in_but_not_a_stage'):
            engine._count_vlan_facts(node, _rule(
                node, match=[(_VLAN, '10')], actions=[Forward(['p1'])]))
        self.assertEqual(
            (engine._vlan_rewrite_rules, engine._vlan_admission_rules), (0, 0))
        self.assertEqual(engine._vlan_stage_devices, set())

    def test_the_tables_are_counted_not_just_the_rules(self):
        engine = _counter()
        for node in ('in.kans', 'in.kans', 'in.chic'):
            engine._count_vlan_facts(node, _rule(
                node, match=[(_VLAN, '10')], actions=[Forward(['p'])]))
        self.assertEqual(engine._vlan_admission_rules, 3)
        self.assertEqual(engine._vlan_stage_devices, {'in.kans', 'in.chic'})

    def test_THE_SAME_COUNT_IN_BOTH_ARMS(self):
        """ The whole point. The relaxed arm must report what it relaxed, so
        the two arms' denominators are comparable -- a count only the faithful
        arm produced would leave `--no-vlan` with nothing to be read against,
        which is the state this guardrail was in until 2026-10-08. """
        counts = []
        for faithful in (True, False):
            engine = _counter(faithful=faithful)
            engine._count_vlan_facts('out.chic', _rule(
                'out.chic', actions=[Rewrite([RuleField(_VLAN, '10')]),
                                     Forward(['p'])]))
            engine._count_vlan_facts('in.kans', _rule(
                'in.kans', match=[(_VLAN, '10')], actions=[Forward(['p'])]))
            counts.append((engine._vlan_rewrite_rules,
                           engine._vlan_admission_rules))
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(counts[0], (1, 1))


class TestTheDenominatorReachesTheCell(unittest.TestCase):
    """ Logged, then parsed into the result -- a recorded field, not something
    a reader has to grep an aggregator log for. """

    def _emit(self, faithful, rewrites=77451, admissions=596, tables=18):
        engine = _counter(faithful=faithful)
        engine._vlan_rewrite_rules = rewrites
        engine._vlan_admission_rules = admissions
        engine._vlan_stage_devices = set('d%d' % i for i in range(tables))
        with self.assertLogs('test_vlan_guardrail', level='INFO') as caught:
            engine._log_vlan_denominator()
        return caught.output[0]

    def test_the_logged_line_is_the_one_cell_run_parses(self):
        # The regex and the format string are in different files; a change to
        # either that did not change the other would silently stop recording
        # the denominator, and a missing field reads as `None` -- "this backend
        # logged none" -- which is exactly the wrong fact.
        for faithful in (True, False):
            with self.subTest(faithful_vlan=faithful):
                found = _VLAN_DENOM.search(self._emit(faithful))
                self.assertIsNotNone(found, 'cell_run cannot parse its own '
                                            'adapter log line')
                self.assertEqual(found.groups(), ('77451', '596', '18'))

    def test_the_relaxed_arm_says_so_in_the_line(self):
        self.assertIn('RELAXED', self._emit(False))
        self.assertIn('faithful_vlan=False', self._emit(False))
        self.assertNotIn('RELAXED', self._emit(True))

    def test_zero_is_logged_rather_than_omitted(self):
        """ A workload with no VLAN stage must SAY nothing was relaxed. The
        absent line and the zero line are different facts: `cell_run` records
        the first as `None` (this backend has no such log) and the second as
        `0` (it counted, and there was nothing there) -- and only the second
        tells a reader that an unchanged verdict means nothing. """
        found = _VLAN_DENOM.search(
            self._emit(False, rewrites=0, admissions=0, tables=0))
        self.assertEqual(found.groups(), ('0', '0', '0'))


if __name__ == '__main__':
    unittest.main()
