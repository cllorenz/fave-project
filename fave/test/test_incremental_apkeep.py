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

""" Incremental re-verification on BDD-APKeep and NDD-APKeep, held to the oracle
(INCREMENTAL_PLAN.md §5, §6.3; APKEEP_INCREMENTAL_SCOPE.md steps 1-3) -- the
same streams and assertions as the NetPlumber and VeriFlow-FR tests, through
test/incremental_oracle.py.

An update re-translates the model on a shadow adapter and applies the
difference through APKeep's own `updateRule`; what would need a new element is
REFUSED and counted, so these streams run with `refusals=True` and assert how
many were refused -- a count that only grows when the translation gains a
whole-model decision an update can flip. The affected checks come from query
footprints: per element, the packets that arrived there.

NDD-APKeep is the same APKeep -- network, elements, change tuples, adapter --
with NDD's per-field atoms (APKEEP_INCREMENTAL_SCOPE.md §4, owner decision B),
so every test here runs on both engines (`*Ndd*` classes) and asserts the same
counts: a refusal is the adapter's, not the atom layer's.
"""

import logging
import os
import unittest

from aggregator.abstract_engine import UpdateRefused
from apkeep.adapter import APKeepAdapter
from apkeep.lib_apkeep import _NDD_JAR, available
from netplumber import lib_adapter
from test.backend_gate import require_or_skip
from test.incremental_oracle import inputs_present, run, s1, s2_and_s3
from util import incremental as inc


def _maker(engine, footprint=None):
    def make():
        log = logging.getLogger("test_incremental_apkeep")
        log.setLevel(logging.ERROR)
        return APKeepAdapter(log, engine=engine, footprint=footprint)
    return make


_make = _maker('bdd')


class _ReleasesEngines:
    """ Every engine a test makes is released when the test ends. An
    NDD-APKeep network registers with the NDD atoms every network in the JVM
    shares, and each later atom split rewrites every registered one, so an
    engine never released makes every later build in the process slower: on
    wl_airtel1, ~13 s more per network left behind, and up to 1,441 s for a
    61 s test late in this module (TODO item 44). Nothing to do for BDD. """

    def setUp(self):
        super().setUp()
        make = type(self).make

        def made():
            engine = make()
            self.addCleanup(engine.release)
            return engine
        self.make = made

#: NDD-APKeep also needs the NDD jar (fave/test/ndd_build.sh)
ndd_available = available() and os.path.isfile(_NDD_JAR)


def _workload(test, prefix):
    if not inputs_present(prefix):
        require_or_skip(False, "%s inputs not generated" % prefix)(lambda: None)()
        test.skipTest("%s inputs not generated" % prefix)
    return prefix


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestIncrementalAPKeep(_ReleasesEngines, unittest.TestCase):

    #: the engine under test; the *Ndd* subclass runs every test on NDD-APKeep
    make = staticmethod(_make)

    #: whether the streams also compare against a from-zero build. On here, the
    #: default footprint; off in the footprint ablations below (TODO item 44).
    from_zero = True

    def test_wl_example_s1_oracle_at_every_update(self):
        stats = run(self, self.make, _workload(self, 'bench/wl_example'), s1,
                    every=1, refusals=True, from_zero=self.from_zero)
        # S1 deletes in reverse model order, so each of pgf's three routes
        # loses its drop before its forwarding rule: a forwarding rule without
        # its drop, which APKeep's FIB cannot express and REFUSES (the model
        # makes every route two rules, AbstractFirewallModel.add_rules) --
        # three deletions, hence three re-insertions. An engine-level stream
        # edits derived rules one at a time; route-level updates are M2's.
        self.assertEqual(len(stats['refused']), 6, stats['refused'])
        self.assertTrue(all('pgf.routing' in reason for _u, reason in stats['refused']))

    def test_wl_example_s2_s3(self):
        # Split per ingress port for updates, the demultiplexed switches dmz
        # and office refuse nothing; they refused 10 of these 30 updates while
        # their elements were named by classes of ports.
        stats = run(self, self.make, _workload(self, 'bench/wl_example'),
                    s2_and_s3(), every=5, refusals=True,
                    from_zero=self.from_zero)
        self.assertEqual(stats['refused'], [])

    def test_wl_ifi_s1(self):
        stats = run(self, self.make, _workload(self, 'bench/wl_ifi'), s1, every=20,
                    refusals=True, from_zero=self.from_zero)
        self.assertEqual(stats['refused'], [])

    def test_wl_ifi_s2_s3(self):
        stats = run(self, self.make, _workload(self, 'bench/wl_ifi'), s2_and_s3(),
                    every=10, refusals=True, from_zero=self.from_zero)
        self.assertEqual(stats['refused'], [])

    def test_wl_airtel1_fib_path(self):
        # Tier A: ingress-qualified destination FIBs, split one element per
        # ingress port at build so no update renames an element. Every update
        # takes the per-device FIB path, and each is checked against the full
        # re-translation as it happens (`verify_fib_path`); the oracle at the
        # end, as a full re-check every update would take long here.
        from util.in_process_driver import InProcessFaVe
        prefix = _workload(self, 'bench/wl_airtel1')
        checks = inc.load_checks(prefix + '/checks.json')
        engine = self.make()
        engine.verify_fib_path = True
        with InProcessFaVe(engine) as fave:
            fave.replay(prefix)
            engine.track_affected(True)
            cache = inc.VerdictCache(fave, engine, checks)
            cache.full()
            stream = list(inc.stream_s2(inc.model_rules(fave), 0.001, 1))
            engine.take_affected()
            deleted, down = set(), set()
            for update in stream:
                inc.apply(engine, update, deleted, down)
                cache.selective(engine.take_affected())
            self.assertEqual(dict(engine.update_paths), {'fib': len(stream)})
            full = cache.ask(checks)
            self.assertEqual(cache.verdict, full)
        if self.from_zero:
            self.assertEqual(full, inc.from_zero(self.make, prefix, checks, deleted,
                                                 down, like=engine))

    # No wl_cloud stream: BDD-APKeep takes 3.24 h to BUILD it (V5,
    # bench/campaigns/RESULTS.md). Its rewrites -- NAT under updates -- are
    # tested on a small network in test_apkeep_incremental_core.py.


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestIncrementalNddAPKeep(TestIncrementalAPKeep):
    """ The same streams, refusals and oracle on NDD-APKeep. """
    make = staticmethod(_maker('ndd-apkeep'))

    def test_wl_cloud_s2_s3(self):
        # NATs rewriting addresses under updates, on the workload BDD-APKeep
        # takes 3.24 h to build (V5); NDD-APKeep builds it in seconds.
        stats = run(self, self.make, _workload(self, 'bench/wl_cloud'),
                    s2_and_s3(fraction=0.05), every=25, refusals=True,
                    from_zero=self.from_zero)
        print("wl_cloud S2+S3 on NDD-APKeep:", {k: (len(v) if isinstance(v, list) else v)
                                                for k, v in stats.items()})


# The footprints (APKEEP_INCREMENTAL_SCOPE.md §9) change which checks an update
# reports, never an answer. The classes above run the default, witness with
# dead-ends; here every stream, under the oracle, with the coarse footprint of
# §4 -- the ablation's reference -- on both engines, and with 'dead-ends' alone
# on NDD-APKeep, because it keeps a reachable query's explored footprint apart
# from an unreachable one's, a path the pair never takes.
#
# What they vary is what the engine REPORTS, not the state it holds, so they
# keep the oracle's footprint half -- selective equals full after every
# update, the soundness of the reported checks -- and leave the from-zero half
# to the default classes, which hold the same engines' state to a rebuild on
# the same streams. That half was most of these classes' cost: a fresh engine
# and a full check every `every` updates, on 17 of the module's 28 streams,
# three of them wl_cloud (TODO item 44, lever 2, owner 2026-10-12). Not
# caught here any more: footprint RECORDING that corrupts engine state in a
# non-default mode only.

@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestIncrementalAPKeepCoarseFootprints(TestIncrementalAPKeep):
    make = staticmethod(_maker('bdd', ()))
    from_zero = False


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestIncrementalNddAPKeepCoarseFootprints(TestIncrementalNddAPKeep):
    make = staticmethod(_maker('ndd-apkeep', ()))
    from_zero = False


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestIncrementalNddAPKeepDeadEnds(TestIncrementalNddAPKeep):
    make = staticmethod(_maker('ndd-apkeep', ('dead-ends',)))
    from_zero = False


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestAgreesWithNetPlumber(_ReleasesEngines, unittest.TestCase):
    """ O3.2 in miniature: on a stream neither engine refuses, every update
    changes the same verdicts on both. """

    make = staticmethod(_make)

    def test_wl_ifi_s2_s3(self):
        from util.in_process_driver import InProcessFaVe
        prefix = _workload(self, 'bench/wl_ifi')
        checks = inc.load_checks(prefix + '/checks.json')
        changes = []
        for make in (self.make, lambda: lib_adapter.NetPlumberLibAdapter(
                logging.getLogger("test_incremental_apkeep"))):
            engine = make()
            per_update = []
            with InProcessFaVe(engine) as fave:
                fave.replay(prefix)
                engine.track_affected(True)
                cache = inc.VerdictCache(fave, engine, checks)
                cache.full()
                stream = s2_and_s3()(inc.model_rules(fave), inc.model_links(fave))
                engine.take_affected()
                deleted, down = set(), set()
                for update in stream:
                    inc.apply(engine, update, deleted, down)
                    cache.selective(engine.take_affected())
                    per_update.append(sorted(cache.last_changes))
            changes.append(per_update)
        self.assertGreater(sum(map(len, changes[0])), 0)
        self.assertEqual(changes[0], changes[1])


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
@require_or_skip(lib_adapter.libnetplumber is not None, "libnetplumber is not built")
class TestNddAgreesWithNetPlumber(TestAgreesWithNetPlumber):
    make = staticmethod(_maker('ndd-apkeep'))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestRefusals(unittest.TestCase):
    """ What the APKeep adapter cannot take in place, it refuses -- before
    changing anything, and counted by reason. """

    make = staticmethod(_make)

    @classmethod
    def setUpClass(cls):
        from util.in_process_driver import InProcessFaVe
        if not inputs_present('bench/wl_example'):
            # Through the gate, so FAVE_REQUIRE_BACKENDS fails it (item 49).
            require_or_skip(False, "bench/wl_example inputs not generated")(
                lambda: None)()
            raise unittest.SkipTest("bench/wl_example inputs not generated")
        cls.engine = cls.make()
        cls.fave = InProcessFaVe(cls.engine)
        cls.fave.replay('bench/wl_example')
        cls.engine.check_compliance({})       # builds

    @classmethod
    def tearDownClass(cls):
        cls.fave.stop()
        cls.engine.release()

    def test_an_unknown_rule_cannot_be_deleted(self):
        key, _rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.delete_rule(key[0], key[1], 10**6)
        self.assertGreater(self.engine.refused_updates['unknown'], 0)

    def test_a_present_rule_cannot_be_inserted_again(self):
        _key, rule = inc.model_rules(self.fave)[0]
        with self.assertRaises(UpdateRefused):
            self.engine.insert_rule(rule)

    def test_a_new_element_is_refused_and_nothing_changes(self):
        # Taking dmz's uplink down changes its ingress classes, hence its
        # elements' names.
        live = dict(self.engine._live) if self.engine._live else None
        link = next(l for l in inc.model_links(self.fave) if l[1] == 'dmz.1')
        with self.assertRaises(UpdateRefused) as ctx:
            self.engine.set_link(link[0], link[1], False)
        self.assertIn('element structure', str(ctx.exception))
        self.assertEqual(self.engine._down, set())
        if live is not None:
            self.assertEqual(self.engine._live['rules'], live['rules'])

    def test_the_ndd_engine_takes_no_updates(self):
        from util.in_process_driver import InProcessFaVe
        log = logging.getLogger("test_incremental_apkeep")
        engine = APKeepAdapter(log, engine='ndd')
        self.addCleanup(engine.release)
        with InProcessFaVe(engine) as fave:
            fave.replay('bench/wl_example')
            engine.check_compliance({})
            key, _rule = inc.model_rules(fave)[0]
            with self.assertRaises(UpdateRefused):
                engine.delete_rule(*key)


@require_or_skip(ndd_available, "JPype, the APKeep jar or the NDD jar is unavailable")
class TestNddRefusals(TestRefusals):
    make = staticmethod(_maker('ndd-apkeep'))


if __name__ == '__main__':
    unittest.main()
