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

""" Which generated check carries which third-party verdict.

THE DEFECT THIS EXISTS TO CLOSE. wl_cloud's previous check set was hand-built,
one generator per query, and a check that went missing still counted as
agreement -- nothing had violated it, so the stamp reported the verdict as
reproduced. A dropped check that reads as a pass is the most expensive shape of
bug this repository has produced (AD6_PLAN.md §9.23 is a post-mortem of one),
and it is exactly what an FPL policy makes easier: 71 checks, of which six are
the verdicts and 65 are expectations we wrote.

So `pair_oracle_to_checks` refuses rather than returning a partial answer, and
the tests below drive the refusal as hard as the success.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from bench.wl_cloud.cloud_endpoints import derive_endpoints, role_members
from bench.wl_cloud.cloud_oracle import derive_oracle
from bench.wl_cloud.cloud_provenance import (
    UnmatchedQuery, check_key, pair_oracle_to_checks, parse_violations,
    query_constraints)
from bench.wl_cloud.cloud_tf import classify_nodes, parse_tf

_RAW_DIR = 'bench/wl_cloud/cloud-tf'
_RAW = '%s/network.tf' % _RAW_DIR
_INVENTORY = 'bench/wl_cloud/roles_and_services.txt'
_POLICY = 'bench/wl_cloud/reach.txt'


def _generate_checks(tmpdir, complement=True):
    """ The real 71, through the real two-step pipeline.

    Generated rather than committed: a check set transcribed into a test is a
    second copy of the thing under test, and the first edit to the policy makes
    it a lie that still passes.
    """
    roles = os.path.join(tmpdir, 'roles.json')
    csv = os.path.join(tmpdir, 'reach.csv')
    inventory = os.path.join(tmpdir, 'inventory.json')
    checks = os.path.join(tmpdir, 'checks.json')

    subprocess.run(
        [sys.executable, '../policy_translator/policy_translator.py',
         '--strict', '--roles', roles, '--csv', '--out', csv,
         _INVENTORY, _POLICY],
        check=True)

    endpoints = derive_endpoints(classify_nodes(parse_tf(open(_RAW, 'r'))))
    members = role_members(roles, endpoints)
    with open(inventory, 'w') as out:
        out.write(json.dumps(
            dict((role, [member.name]) for role, member in members.items())))

    subprocess.run(
        [sys.executable, 'bench/reach_csv_to_checks.py', '--strict']
        + (['--complement'] if complement else []) +
        ['-p', csv, '-m', inventory,
         '--roles', roles, '-c', checks,
         '--cchecks', os.path.join(tmpdir, 'cchecks.json'),
         '-j', os.path.join(tmpdir, 'reachable.json')],
        check=True)

    endpoint_of = {}
    for member in members.values():
        endpoint_of[member.tx] = member.name
        endpoint_of[member.rx] = member.name

    return json.load(open(checks, 'r')), endpoint_of


@unittest.skipUnless(os.path.isfile(_RAW), 'raw scenario not present')
class TestTheRealCheckSet(unittest.TestCase):
    """ The committed policy, compiled, against the derived oracle. """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.checks, cls.endpoint_of = _generate_checks(cls._tmp)
        cls.queries = derive_oracle(_RAW_DIR)['queries']

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, True)

    def test_every_oracle_verdict_is_carried_by_exactly_one_check(self):
        """ The property the whole stamp rests on. Six queries in, six records
        out, and the pairing raises rather than dropping any. """
        records = pair_oracle_to_checks(
            self.queries, self.checks, self.endpoint_of)

        self.assertEqual(len(records), 6)
        self.assertEqual(
            [r['name'] for r in records],
            ['q01', 'q02', 'q03', 'q04', 'q05', 'q06'])

    def test_query_06_is_reproduced_BY_a_violation(self):
        """ A policy is an intent. q06 asserts a permission this network does
        not grant, so the check generated for it is expected to FAIL, and that
        failure is the reproduction (see the workload README). It is the only
        one of the six written that way. """
        records = dict(
            (r['name'], r)
            for r in pair_oracle_to_checks(
                self.queries, self.checks, self.endpoint_of))

        self.assertTrue(records['q06']['expected_violated'])
        self.assertTrue(records['q06']['must_reach'])
        self.assertEqual(
            [n for n, r in records.items() if r['expected_violated']], ['q06'])

    def test_query_04_takes_the_complement_and_not_its_sibling(self):
        """ `Internet ---> host22.S331` yields TWO must-not-reach complement
        terms over the same pair -- one contradicting the port, one the
        protocol. Only the first is what the dataset asked. """
        records = dict(
            (r['name'], r)
            for r in pair_oracle_to_checks(
                self.queries, self.checks, self.endpoint_of))

        check = records['q04']['check']
        self.assertTrue(check.startswith('! '))
        self.assertIn('f=!port:331', check)
        self.assertNotIn('protocol', check)

    def test_every_generated_check_has_a_distinct_report_key(self):
        """ What violation attribution rests on. A report states a violation as
        (source, probe, direction, condition FIELDS) -- not values, since a
        complement expands to several vectors and each renders as its own bit
        pattern. If two checks ever shared that key, one's violation would be
        attributed to the other, silently. """
        keys = [check_key(c) for c in self.checks]
        self.assertEqual(len(set(keys)), len(self.checks))

    def test_without_the_complement_query_04_is_carried_by_NOTHING(self):
        """ Why `use_complement=True` is not optional for this workload.

        q04 asks whether anything OUTSIDE port 331 arrives. That is the
        complement half of `Internet ---> host22.S331`, and without
        `--complement` the cell is only checked in the direction that confirms
        it -- §1.9.3's "q04 would have degraded from 'nothing outside 331
        enters' to '331 enters'".

        The point is not that the check is missing; it is that the run REFUSES
        instead of reporting six verdicts reproduced on the strength of five.
        The hand-built check set this replaces had no such guard, and a stamp
        recording `agrees: true` for a check that was not run is the exact
        vacuity this module exists to close.
        """
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, tmp, True)
        checks, endpoint_of = _generate_checks(tmp, complement=False)

        with self.assertRaises(UnmatchedQuery) as ctx:
            pair_oracle_to_checks(self.queries, checks, endpoint_of)
        self.assertIn('q04', str(ctx.exception))
        self.assertIn('matches 0', str(ctx.exception))

    def test_the_six_are_a_minority_of_the_checks(self):
        """ Not a number to pin, but a property: most of what this workload
        reports is OUR expectation, which is why the stamp keeps the two apart
        and never sums them (CLOUD_BENCH_PLAN.md §1.9.0). """
        records = pair_oracle_to_checks(
            self.queries, self.checks, self.endpoint_of)
        self.assertLess(len(records), len(self.checks) / 2)


class TestThePairingRefuses(unittest.TestCase):
    """ The failure modes, driven directly. """

    ENDPOINTS = {1: 'alice', 2: 'bob'}

    def _query(self, **kwargs):
        query = {
            'name': 'q01', 'smt2': '01.sat.smt2', 'sha256': 'deadbeef',
            'source': 1, 'target': 2, 'fields': [], 'conditions': [],
            'expect': 'sat',
        }
        query.update(kwargs)
        return query

    def test_a_query_no_check_carries_is_refused(self):
        """ The vacuity defect itself: without this the verdict would be
        reported as reproduced because nothing violated a check that was never
        generated. """
        with self.assertRaises(UnmatchedQuery) as ctx:
            pair_oracle_to_checks([self._query()], [], self.ENDPOINTS)
        self.assertIn('q01', str(ctx.exception))

    def test_a_query_matching_several_checks_is_refused(self):
        """ Ambiguity is not resolved by picking one: which question the
        dataset answered cannot be decided here, and guessing would attach a
        third-party verdict to a check we chose. """
        checks = [
            's=source.alice && EF p=probe.bob && f=port:80',
            's=source.alice && EF p=probe.bob && f=port:443',
        ]
        with self.assertRaises(UnmatchedQuery) as ctx:
            pair_oracle_to_checks([self._query()], checks, self.ENDPOINTS)
        self.assertIn('matches 2', str(ctx.exception))

    def test_a_query_naming_an_endpoint_the_model_lacks_is_refused(self):
        with self.assertRaises(UnmatchedQuery) as ctx:
            pair_oracle_to_checks(
                [self._query(target=99)],
                ['s=source.alice && EF p=probe.bob'], self.ENDPOINTS)
        self.assertIn('the target', str(ctx.exception))


class TestTheNarrowingRule(unittest.TestCase):
    """ When a check asks more than the query, and when that is still it. """

    ENDPOINTS = {1: 'alice', 2: 'bob'}
    QUERY = {
        'name': 'q05', 'smt2': '05.sat.smt2', 'sha256': 'beef',
        'source': 1, 'target': 2, 'fields': ['tcp_dst=350'], 'conditions': [],
        'expect': 'sat',
    }

    def _pair(self, checks):
        return pair_oracle_to_checks([self.QUERY], checks, self.ENDPOINTS)

    def test_a_service_protocol_the_query_omits_is_still_the_query(self):
        """ `S350` compiles to `protocol:tcp;port:350`; query 05 constrains only
        the port. The check is NARROWER, which is sound in both directions -- a
        narrower must-reach check that passes proves the broader question
        satisfiable, and a narrower must-not-reach one is implied by the broader
        unreachability. """
        records = self._pair([
            's=source.alice && EF p=probe.bob '
            '&& f=related:0 && f=protocol:tcp && f=port:350'])
        self.assertEqual(records[0]['name'], 'q05')

    def test_a_surplus_NEGATION_is_not_a_narrowing(self):
        """ The other half of the rule, and the reason it is not plain subset:
        a check that also demands "and not udp" describes neither a subset nor
        a superset of the query in the direction that would make the
        implication hold. """
        with self.assertRaises(UnmatchedQuery):
            self._pair([
                's=source.alice && EF p=probe.bob '
                '&& f=port:350 && f=!protocol:udp'])

    def test_a_check_missing_the_querys_own_constraint_is_not_a_match(self):
        """ The unconditioned check asks a strictly broader question, which is
        the direction §9.23.2a refuses: answering it looks like a result. """
        with self.assertRaises(UnmatchedQuery):
            self._pair(['s=source.alice && EF p=probe.bob'])

    def test_related_is_dropped_from_both_sides(self):
        """ Every conditional check carries `f=related:0` and the cloud model
        has no conntrack at all, so the field constrains nothing here and
        corresponds to nothing in any `.smt2`. Keeping it would make every
        conditional check unmatchable. """
        self.assertEqual(
            query_constraints({'fields': ['related=0', 'tcp_dst=350'],
                               'conditions': []}),
            query_constraints({'fields': ['tcp_dst=350'], 'conditions': []}))


class TestTheExpectedOutcome(unittest.TestCase):
    """ `expected_violated` over all four combinations. """

    ENDPOINTS = {1: 'alice', 2: 'bob'}

    def _expected(self, expect, check):
        query = {
            'name': 'q', 'smt2': 'x.smt2', 'sha256': 'f00d',
            'source': 1, 'target': 2, 'fields': [], 'conditions': [],
            'expect': expect,
        }
        return pair_oracle_to_checks(
            [query], [check], self.ENDPOINTS)[0]['expected_violated']

    REACH = 's=source.alice && EF p=probe.bob'
    DENY = '! s=source.alice && EF p=probe.bob'

    def test_a_permission_the_dataset_grants_is_expected_to_hold(self):
        self.assertFalse(self._expected('sat', self.REACH))

    def test_a_denial_the_dataset_confirms_is_expected_to_hold(self):
        self.assertFalse(self._expected('unsat', self.DENY))

    def test_a_permission_the_dataset_denies_is_expected_to_be_violated(self):
        """ Query 06's shape. """
        self.assertTrue(self._expected('unsat', self.REACH))

    def test_a_denial_the_dataset_contradicts_is_expected_to_be_violated(self):
        self.assertTrue(self._expected('sat', self.DENY))


class TestReadingAViolationBack(unittest.TestCase):
    """ The report is the only per-check verdict a NetPlumber run produces. """

    def test_a_reported_violation_matches_its_own_check(self):
        """ End to end over the two representations: a check line, rendered as
        a report would render its violation, read back to the same key. """
        check = ('! s=source.internet && EF p=probe.dc4_leaf3_host22 '
                 '&& f=related:0 && f=!port:331')
        report = (
            '- `source.internet` reaches `probe.dc4_leaf3_host22` with \n'
            '    - related=0\n'
            '    - packet.upper.dport=0000000101001011\n')
        self.assertIn(check_key(check), parse_violations(report))

    def test_a_violation_of_the_opposite_polarity_is_a_different_check(self):
        """ "reaches" and "does not reach" are violations of opposite checks,
        so the direction must be part of the key or a satisfied must-reach
        check could read as a violated must-not-reach one. """
        check = 's=source.internet && EF p=probe.dc1_leaf5_host5'
        report = ('- `source.internet` reaches `probe.dc1_leaf5_host5`\n')
        self.assertNotIn(check_key(check), parse_violations(report))


if __name__ == '__main__':
    unittest.main()
