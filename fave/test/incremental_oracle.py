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

""" The oracle-driven stream check shared by the per-engine incremental tests
(test_incremental_<engine>.py; INCREMENTAL_PLAN.md §5, §6). Not a test module. """

import os

from util import incremental as inc


def inputs_present(prefix):
    return all(os.path.exists(os.path.join(prefix, name)) for name in (
        'topology.json', 'routes.json', 'policies.json', 'sources.json',
        'checks.json'))


def s2_and_s3(fraction=0.2, seed=1):
    """ S2 (a seeded `fraction` of the rules deleted and re-added), then S3. """
    def stream(rules, links):
        return list(inc.stream_s2(rules, fraction, seed)) + list(inc.stream_s3(links))
    return stream


def s1(rules, _links):
    return inc.stream_s1(rules)


def run(test, make, prefix, stream_of, every):
    """ Drive `stream_of(rules, links)` on a build of `prefix` by the engine
    `make()` returns, asserting the oracle: after EVERY update the selective
    re-verification leaves the cache equal to a full one; at every `every`-th
    update and the last, the full verdicts equal a from-zero build of the
    current model. The stream must change a verdict (else the oracle is
    vacuous) and must ask fewer checks than a full re-check every time.
    Returns the run's counts. """
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    engine = make()
    stats = {'updates': 0, 'verdict_changes': 0, 'rechecked': 0}
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        # Tracking on BEFORE the first answers, so an engine that records
        # what its answers depended on (VeriFlow-FR's walk footprints) has it.
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        previous = cache.full()
        stream = list(stream_of(inc.model_rules(fave), inc.model_links(fave)))
        test.assertTrue(stream, "an empty stream tests nothing")
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
                    full, inc.from_zero(make, prefix, checks, deleted, down),
                    "%s, update %d %s: the incremental engine disagrees with "
                    "a from-zero build of the same model" % (prefix, n, update[:2]))
        stats['updates'] = len(stream)
    test.assertGreater(stats['verdict_changes'], 0,
                       "no update changed a verdict: the oracle was not tested")
    test.assertLess(stats['rechecked'], stats['updates'] * len(checks),
                    "the selective re-check asked every check every time")
    return stats
