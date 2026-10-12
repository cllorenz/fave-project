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

import copy
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


def run(test, make, prefix, stream_of, every, refusals=False, from_zero=True):
    """ Drive `stream_of(rules, links)` on a build of `prefix` by the engine
    `make()` returns, asserting the oracle: after EVERY update the selective
    re-verification leaves the cache equal to a full one; at every `every`-th
    update and the last, the full verdicts equal a from-zero build of the
    current model. With `refusals`, an update the engine refuses is counted in
    `stats['refused']` and leaves the model as it was. The stream must change a verdict (else the oracle is
    vacuous) and must ask fewer checks than a full re-check every time.

    `from_zero=False` keeps the first half and drops the second: for a run
    that varies only what the engine REPORTS as affected (a footprint mode),
    whose engine state another run already holds to a from-zero build.
    Returns the run's counts. """
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    engine = make()
    stats = {'updates': 0, 'verdict_changes': 0, 'rechecked': 0, 'refused': []}
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
            # `refusals`: an engine that refuses what it cannot take in place
            # (APKeep) goes on with the model unchanged, and is counted.
            inc.apply(engine, update, deleted, down,
                      stats['refused'] if refusals else None)
            stats['rechecked'] += len(cache.selective(engine.take_affected()))
            full = cache.ask(checks)
            test.assertEqual(
                cache.verdict, full,
                "%s, update %d %s: selective re-verification missed a change"
                % (prefix, n, update[:2]))
            stats['verdict_changes'] += sum(
                1 for line in full if full[line] != previous[line])
            previous = full
            if from_zero and (n % every == 0 or n == len(stream)):
                test.assertEqual(
                    full, inc.from_zero(make, prefix, checks, deleted, down,
                                        like=engine),
                    "%s, update %d %s: the incremental engine disagrees with "
                    "a from-zero build of the same model" % (prefix, n, update[:2]))
        stats['updates'] = len(stream)
    test.assertGreater(stats['verdict_changes'], 0,
                       "no update changed a verdict: the oracle was not tested")
    test.assertLess(stats['rechecked'], stats['updates'] * len(checks),
                    "the selective re-check asked every check every time")
    test.assertLess(len(stats['refused']), stats['updates'],
                    "every update was refused: the stream tested nothing")
    return stats


def _misordered_routes(rules, declared, table=None, pairs=None):
    """ The routes of declared-LPM tables that file order puts on the wrong
    side of a covering route: a longer prefix inside a shorter one with a
    different action, but LATER in the table. Prefix bands keep the longer
    one winning; an index that ignores them lets the shorter win. """
    import ipaddress
    from devices.abstract_device import lpm_prefix_len
    by_table = {}
    for (node, tid, idx), rule in rules:
        if tid not in declared or (table is not None and tid != table):
            continue
        dst = [f for f in rule.match or [] if 'destination' in f.name]
        net = ipaddress.ip_network(str(dst[0].value) if dst else '0.0.0.0/0')
        by_table.setdefault(tid, []).append(((node, tid, idx), rule, net))
    picked = {}
    for routes in by_table.values():
        nets = {net: (key, rule) for key, rule, net in routes}
        for key, rule, net in routes:
            # Down to /1: under the default route every route is "covered",
            # and moving them all is the slow test this replaces.
            for plen in range(net.prefixlen - 1, 0, -1):
                outer = nets.get(net.supernet(new_prefix=plen))
                if outer is None:
                    continue
                if str(outer[1].actions) != str(rule.actions) and outer[0][2] < key[2]:
                    if pairs is not None and len(picked) >= 2 * pairs:
                        break
                    picked[key] = rule
                    picked[outer[0]] = outer[1]
                break
    assert all(lpm_prefix_len(r) >= -1 for r in picked.values())
    return sorted(picked.items())


def moved_routes(test, make, prefix, checks_path, files=None, source=None,
                 table=None, pairs=None):
    """ O1 (INCREMENTAL_PLAN.md): delete routes of declared-LPM tables and
    insert each again under an index the build never saw. A declared-LPM
    priority is a function of prefix length and index, banded so that any
    index lands where its prefix says, so every verdict must stay as it was.
    Dense priorities refused this.

    The routes moved are the MISORDERED ones (`_misordered_routes`): an
    insert that forgets the band and ranks them by index alone ABOVE the rest
    lets each covering route win over the longer one inside it, and this
    fails -- measured by mutating each engine's insert path (wl_stanford,
    40 pairs of mid.bbra_rtr.1, the 15 checks from bbra_rtr). Ranked BELOW
    the rest instead, the same mutation passed on VeriFlow-FR: reachability
    is existential, and other routes still carried the traffic. `source`
    restricts the checks, `table` the routes, `pairs` how many misordered
    pairs are moved. """
    from util.in_process_driver import InProcessFaVe
    if not os.path.exists(checks_path):
        test.skipTest("%s not generated" % checks_path)
    checks = [c for c in inc.load_checks(checks_path)
              if source is None or c.source == source]
    engine = make()
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix, files=files)
        cache = inc.VerdictCache(fave, engine, checks)
        before = cache.full()
        declared = engine._lpm_tables if hasattr(engine, '_lpm_tables') \
            else engine.lpm_declared
        routes = _misordered_routes(inc.model_rules(fave), declared, table, pairs)
        test.assertGreater(len(routes), 0, "no misordered route to move")
        for (node, tid, idx), _rule in routes:
            engine.delete_rule(node, tid, idx)
        for (node, tid, idx), rule in routes:
            late = copy.copy(rule)
            late.idx = 10**5 + idx               # never seen at build
            engine.insert_rule(late)
        test.assertEqual(cache.ask(checks), before)
        return len(routes)
