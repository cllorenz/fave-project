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

""" Incremental re-verification on NetPlumber, held to its oracle
(INCREMENTAL_PLAN.md §5, §6.3).

Each test builds a workload through the real aggregator path, then drives an
update stream (S1-S3, §7) directly at the adapter. After EVERY update:

* the selective re-verification -- only the checks on a (source, probe) the
  engine reported as affected -- must leave the cache equal to a FULL
  re-verification of every check on the same engine state;

and at checkpoints:

* the full verdicts must equal a FROM-ZERO build of the current model on a
  fresh engine, which never calls an incremental update.

A stream that never changed a verdict would pass all of that vacuously, so each
test also requires that verdicts changed; and one whose selective re-check asked
as many checks as a full one would prove nothing about selectivity.

wl_cloud's S2 stream is also a regression test: its 130th deletion crashed
NetPlumber (an uninitialised `processed_hs` on a flow created by
re-propagation, node.cc) until 2026-10-09.
"""

import logging
import os
import unittest

from aggregator.abstract_engine import UpdateRefused
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from util import incremental as inc


def _logger():
    log = logging.getLogger("test_incremental_netplumber")
    log.setLevel(logging.WARNING)
    return log


def _make():
    return lib_adapter.NetPlumberLibAdapter(_logger())


def _inputs_present(prefix):
    return all(os.path.exists(os.path.join(prefix, name)) for name in (
        'topology.json', 'routes.json', 'policies.json', 'sources.json',
        'checks.json'))


def _run(test, prefix, stream_of, every):
    """ Drive `stream_of(rules, links)` on a NetPlumber build of `prefix`,
    asserting the oracle as described above. Returns the run's counts. """
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    engine = _make()
    stats = {'updates': 0, 'verdict_changes': 0, 'rechecked': 0}
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        cache = inc.VerdictCache(fave, engine, checks)
        previous = cache.full()
        stream = list(stream_of(inc.model_rules(fave), inc.model_links(fave)))
        test.assertTrue(stream, "an empty stream tests nothing")
        engine.track_affected(True)
        engine.take_affected()
        deleted, down = set(), set()
        for n, update in enumerate(stream, start=1):
            inc.apply(engine, update, deleted, down)
            stats['rechecked'] += len(cache.selective(engine.take_affected()))
            full = cache.ask(checks)
            test.assertEqual(
                cache.verdict, full,
                "%s, update %d %s: selective re-verification missed a change"
                % (prefix, n, update[:2]))
            stats['verdict_changes'] += sum(
                1 for line in full if full[line] != previous[line])
            previous = full
            if n % every == 0 or n == len(stream):
                test.assertEqual(
                    full, inc.from_zero(_make, prefix, checks, deleted, down),
                    "%s, update %d %s: the incremental engine disagrees with "
                    "a from-zero build of the same model" % (prefix, n, update[:2]))
        stats['updates'] = len(stream)
    test.assertGreater(stats['verdict_changes'], 0,
                       "no update changed a verdict: the oracle was not tested")
    test.assertLess(stats['rechecked'], stats['updates'] * len(checks),
                    "the selective re-check asked every check every time")
    return stats


def _s2_and_s3(rules, links):
    return list(inc.stream_s2(rules, 0.2, seed=1)) + list(inc.stream_s3(links))


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestIncrementalNetPlumber(unittest.TestCase):

    def _workload(self, prefix):
        if not _inputs_present(prefix):
            require_or_skip(False, "%s inputs not generated" % prefix)(
                lambda: None)()
            self.skipTest("%s inputs not generated" % prefix)
        return prefix

    def test_wl_example_s1_oracle_at_every_update(self):
        _run(self, self._workload('bench/wl_example'),
             lambda rules, _links: inc.stream_s1(rules), every=1)

    def test_wl_example_s2_s3(self):
        _run(self, self._workload('bench/wl_example'), _s2_and_s3, every=5)

    def test_wl_ifi_s1(self):
        _run(self, self._workload('bench/wl_ifi'),
             lambda rules, _links: inc.stream_s1(rules), every=20)

    def test_wl_ifi_s2_s3(self):
        # Includes routes deleted from and re-inserted into wl_ifi's two
        # declared-LPM tables, each back into the slot it had.
        _run(self, self._workload('bench/wl_ifi'), _s2_and_s3, every=10)

    def test_wl_cloud_s2_s3(self):
        _run(self, self._workload('bench/wl_cloud'), _s2_and_s3, every=50)


@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestRefusals(unittest.TestCase):
    """ What the NetPlumber adapter does not do yet, it refuses. """

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe
        if not _inputs_present('bench/wl_ifi'):
            raise unittest.SkipTest("bench/wl_ifi inputs not generated")
        cls.engine = _make()
        cls.fave = InProcessFaVe(cls.engine)
        cls.fave.replay('bench/wl_ifi')
        cls.models = cls.fave._agg.models

    @classmethod
    def tearDownClass(cls):
        cls.fave.stop()

    def test_an_unknown_rule_cannot_be_deleted(self):
        key, _rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.delete_rule(key[0], key[1], 10**6)

    def test_a_present_rule_cannot_be_inserted_again(self):
        _key, rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.insert_rule(rule)

    def test_pre_and_post_routing_are_refused(self):
        for model in self.models.values():
            for tid in model.tables:
                if tid.endswith(('.pre_routing', '.post_routing')):
                    with self.assertRaises(UpdateRefused):
                        self.engine.delete_rule(model.node, tid, 0)
                    return
        self.skipTest("wl_ifi has no pre/post-routing table")

    def test_a_new_route_in_a_declared_lpm_table_is_refused(self):
        # O1: priorities there are dense; only a rule's own slot is known.
        import copy
        for tid in sorted(self.engine._lpm_tables):
            node = tid.rsplit('.', 1)[0]
            rule = copy.copy(self.models[node].tables[tid][0])
            rule.idx = 10**5
            with self.assertRaises(UpdateRefused) as ctx:
                self.engine.insert_rule(rule)
            self.assertIn('O1', str(ctx.exception))
            return
        self.skipTest("wl_ifi declares no LPM table")


if __name__ == '__main__':
    unittest.main()
