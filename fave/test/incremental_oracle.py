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
import json
import os
import tempfile

from test.backend_gate import require_or_skip
from util import incremental as inc


def inputs_present(prefix, checks=True):
    return all(os.path.exists(os.path.join(prefix, name)) for name in (
        'topology.json', 'routes.json', 'policies.json', 'sources.json')
        + (('checks.json',) if checks else ()))


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


def _route_arg(route, delete=False):
    """ A routes.json entry [node, table, idx, fields, commands, in_ports] as
    one rule of `switch.py -r`, as `util.bench_utils._add_rules` writes it;
    a delete names node, table and index only. """
    node, table, idx, fields, commands, in_ports = route
    if delete:
        return '$'.join((node, str(table), str(idx)))
    return '$'.join((node, str(table), str(idx), ','.join(in_ports),
                     ';'.join(fields), ','.join(commands)))


def _held_keys(fave):
    """ (node, table, index) of every rule the aggregator holds. """
    return {(node, table, rule.idx) for node, model in fave._agg.models.items()
            for table, rules in model.tables.items() for rule in rules}


def route_commands(test, make, prefix, fraction, seed, batch, every,
                   refusals=False):
    """ INCREMENTAL_PLAN.md D14: S2 through FaVe. A seeded `fraction` of the
    workload's routes is deleted with `switch.py -d -r` commands, then added
    again with `switch.py -a -r`, up to `batch` routes of one node per
    command. The oracle as in `run`: after every command the selective
    re-verification equals a full one; every `every`-th command and the last,
    the full verdicts equal a from-zero build of the model the aggregator
    then holds. The rules withheld from that build are read off the
    aggregator, so a command the engine refused in part (with `refusals`,
    counted) is compared with what was really applied. """
    import random
    from util.barrier import BarrierError
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    with open(os.path.join(prefix, 'routes.json')) as raw:
        routes = json.load(raw)
    drawn = random.Random(seed).sample(routes, max(1, int(round(fraction * len(routes)))))
    if batch > 1:   # a command holds the routes of one node
        drawn.sort(key=lambda r: r[0])
    groups = []
    for route in drawn:
        if groups and groups[-1][0][0] == route[0] and len(groups[-1]) < batch:
            groups[-1].append(route)
        else:
            groups.append([route])
    commands = [('-d', g) for g in groups] + [('-a', g) for g in groups]
    stats = {'commands': 0, 'routes': len(drawn), 'verdict_changes': 0,
             'rechecked': 0, 'refused': []}
    engine = make()
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        previous = cache.full()
        engine.take_affected()
        built = _held_keys(fave)
        for n, (verb, group) in enumerate(commands, start=1):
            try:
                fave.switch([verb, '-r', '#'.join(_route_arg(r, verb == '-d') for r in group)])
            except BarrierError as err:
                if not refusals or 'UpdateRefused' not in str(err):
                    raise
                stats['refused'].append((verb, [r[2] for r in group], str(err)))
            stats['rechecked'] += len(cache.selective(engine.take_affected()))
            full = cache.ask(checks)
            test.assertEqual(cache.verdict, full,
                             "%s, command %d (%s %d routes of %s): selective "
                             "re-verification missed a change"
                             % (prefix, n, verb, len(group), group[0][0]))
            stats['verdict_changes'] += sum(1 for c in full if full[c] != previous[c])
            previous = full
            if n % every == 0 or n == len(commands):
                deleted = built - _held_keys(fave)
                test.assertEqual(
                    full, inc.from_zero(make, prefix, checks, deleted, set(), like=engine),
                    "%s, command %d (%s %d routes of %s): the engine disagrees with "
                    "a from-zero build of the model the aggregator holds"
                    % (prefix, n, verb, len(group), group[0][0]))
        stats['commands'] = len(commands)
        if not stats['refused']:
            test.assertEqual(_held_keys(fave), built,
                             "%s: every route was added again, but the model differs" % prefix)
    test.assertGreater(stats['verdict_changes'], 0,
                       "no command changed a verdict: the oracle was not tested")
    test.assertLess(len(stats['refused']), stats['commands'],
                    "every command was refused: the stream tested nothing")
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
        # Through the gate, so FAVE_REQUIRE_BACKENDS fails it (item 49).
        require_or_skip(False, "%s not generated" % checks_path)(lambda: None)()
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


def run_s4(test, make, prefix, n, seed, every):
    """ S4 under the oracle (INCREMENTAL_PLAN.md §8.1): `n` seeded one-line
    configuration edits, each re-sending its device through the aggregator
    with stable indices, so the engine gets the rules that changed. After
    EVERY edit the selective re-verification must equal a full one; at every
    `every`-th edit and the last, the full verdicts must equal a from-zero
    build of the edited configurations (stable indices off -- the oracle
    shares no code path with what it checks but the generators). Returns the
    run's counts, including the engine-rule changes the edits caused. """
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    engine = make()
    stats = {'edits': 0, 'verdict_changes': 0, 'rechecked': 0,
             'engine_rules': 0, 'windows': 0}
    with tempfile.TemporaryDirectory(prefix='s4_') as work, \
            InProcessFaVe(engine, stable_indices=True) as fave:
        configs = inc.S4Configs(prefix, work)
        fave.replay(configs.zero_prefix())
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        previous = cache.full()
        engine.take_affected()
        for k, edit in enumerate(inc.stream_s4(configs, n, seed), start=1):
            configs.resend(fave, configs.apply(edit))
            got = fave._agg.update_stats
            stats['engine_rules'] += got['deleted'] + got['inserted']
            stats['windows'] += got['windows']
            stats['rechecked'] += len(cache.selective(engine.take_affected()))
            full = cache.ask(checks)
            test.assertEqual(cache.verdict, full,
                             "%s, edit %d %s: selective re-verification missed "
                             "a change" % (prefix, k, edit[:3]))
            stats['verdict_changes'] += sum(
                1 for line in full if full[line] != previous[line])
            previous = full
            if k % every == 0 or k == n:
                zero_engine = make()
                zero_engine.track_affected(True)
                with InProcessFaVe(zero_engine) as zero:
                    zero.replay(configs.zero_prefix())
                    expected = inc.VerdictCache(zero, zero_engine, checks).full()
                if hasattr(zero_engine, 'release'):
                    zero_engine.release()
                test.assertEqual(full, expected,
                                 "%s, edit %d %s: the incremental engine disagrees "
                                 "with a from-zero build of the edited "
                                 "configurations" % (prefix, k, edit[:3]))
            stats['edits'] = k
    return stats


# --- removing a device (INCREMENTAL_PLAN.md §8.2) ---------------------------

_INPUTS = ('topology.json', 'routes.json', 'policies.json', 'sources.json')


_PATH_PORTS = r'\(p in \(([^()]*)\)\)'


def _strip_path_ports(policies, ports):
    """ `policies` with the `ports` dropped from every probe test path's
    `(p in (...))` list, or None when that leaves a list empty: the probe
    could not be written without the device. NetPlumber never consults a
    test path (the legacy probe condition is compiled out; `devices/probe.py`
    warns), but the aggregator resolves one at build, so a build without the
    device needs it gone. """
    import re
    emptied = []

    def keep(match):
        names = [n.strip() for n in match.group(1).split(',')]
        left = [n for n in names if n not in ports]
        if not left:
            emptied.append(match.group(0))
        return '(p in (%s))' % ','.join(left)

    policies = copy.deepcopy(policies)
    for probe in policies['devices']:
        if len(probe) > 6 and probe[6]:
            probe[6] = [re.sub(_PATH_PORTS, keep, text) for text in probe[6]]
    return None if emptied else policies


def _without(prefix, work, names, ports):
    """ Write `prefix`'s inputs to `work` WITHOUT the devices `names`: their
    entries, their routes, every link one of their `ports` ends and their
    ports in probe test paths. Config paths in the entries are relative to
    the working directory, so the copy needs no other file. None when a
    probe's test path names nothing but their ports. """
    for fname in _INPUTS:
        with open(os.path.join(prefix, fname)) as raw:
            data = json.load(raw)
        if fname == 'routes.json':
            data = [r for r in data if r[0] not in names]
        else:
            if fname == 'policies.json':
                data = _strip_path_ports(data, ports)
                if data is None:
                    return None
            data['devices'] = [d for d in data['devices'] if d[0] not in names]
            data['links'] = [l for l in data['links']
                             if l[0] not in ports and l[1] not in ports]
        with open(os.path.join(work, fname), 'w') as out:
            json.dump(data, out)
    return work


def _readd(fave, prefix, entry, ports):
    """ Send device `entry` again as `replay` sends it: the device, its
    routes, then every link one of its `ports` ends. """
    from util import bench_utils as bu
    loaded = {}
    for fname in _INPUTS:
        with open(os.path.join(prefix, fname)) as raw:
            loaded[fname] = json.load(raw)
    bu.create_topology([entry], [], use_unix=False, interweave=True)
    bu.add_routes([r for r in loaded['routes.json'] if r[0] == entry[0]],
                  use_unix=False)
    for fname in ('topology.json', 'policies.json', 'sources.json'):
        links = [l for l in loaded[fname]['links'] if l[0] in ports or l[1] in ports]
        if links:
            bu._add_links(links, use_unix=False)
    fave._agg.queue.join()


def remove_each(test, make, prefix, names=None, residue=None, readd=True,
                refusals=False):
    """ §8.2's oracle: remove each device of `prefix` (all, or `names`) from
    a built engine with its links, as ONE update, then re-verify the checks
    the engine reports as affected. The selective re-verification must
    leave the cache equal to a full one, and the full verdicts must equal a
    from-zero build of the workload WITHOUT the device. With `readd`, the
    device is then added again, as `replay` adds it, and every verdict must
    be back. Without it (an engine that removes by emptying, and so cannot
    take the name again), removals ACCUMULATE: each is compared with a
    from-zero build without every device removed so far.

    Verdicts cannot see what the engine leaks: a device whose links are cut
    answers like an absent one with its tables still held. `residue(engine,
    model)`, called before the removal, returns a callable listing what the
    engine still holds of the device after it; that list must be empty.

    With `refusals`, a removal the engine refuses is counted in
    `stats['refused']`, and must leave every verdict and the aggregator's
    model as they were. A device whose ports are ALL a probe's test path
    names is skipped (`_without`): there is no from-zero build to compare
    against. Returns the run's counts. """
    from util.barrier import BarrierError
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    with open(os.path.join(prefix, 'topology.json')) as raw:
        entries = json.load(raw)['devices']
    stats = {'removed': 0, 'skipped': [], 'refused': [], 'verdict_changes': 0,
             'rechecked': 0}
    gone, gone_ports = set(), set()
    engine = make()
    with InProcessFaVe(engine) as fave:
        fave.replay(prefix)
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        before = previous = cache.full()
        engine.take_affected()
        for entry in entries:
            name = entry[0]
            if names is not None and name not in names:
                continue
            model = fave._agg.models[name]
            ports = {p for p, m in fave._agg.port_to_model.items() if m is model}
            work = tempfile.TemporaryDirectory(prefix='removal_')
            if _without(prefix, work.name, gone | {name}, gone_ports | ports) is None:
                work.cleanup()
                stats['skipped'].append(name)
                continue
            left = residue(engine, model) if residue is not None else list
            try:
                fave.delete_device(name, model.type)
            except BarrierError as err:
                work.cleanup()
                if not refusals or 'UpdateRefused' not in str(err):
                    raise
                stats['refused'].append((name, str(err)))
                cache.selective(engine.take_affected())
                test.assertEqual(cache.ask(checks), previous,
                                 "%s, removing %s: a refused removal changed a "
                                 "verdict" % (prefix, name))
                test.assertIs(fave._agg.models.get(name), model)
                continue
            test.assertEqual(left(), [], "%s, removing %s: the engine still "
                             "holds part of it" % (prefix, name))
            stats['rechecked'] += len(cache.selective(engine.take_affected()))
            full = cache.ask(checks)
            test.assertEqual(cache.verdict, full,
                             "%s, removing %s: selective re-verification "
                             "missed a change" % (prefix, name))
            stats['verdict_changes'] += sum(
                1 for line in full if full[line] != previous[line])
            with work:
                zero = inc.from_zero(make, work.name, checks, set(), set(),
                                     like=engine)
            test.assertEqual(full, zero,
                             "%s, removing %s: the incremental engine disagrees "
                             "with a from-zero build without it" % (prefix, name))
            stats['removed'] += 1
            if not readd:
                gone.add(name)
                gone_ports |= ports
                previous = full
                continue

            _readd(fave, prefix, entry, ports)
            cache.selective(engine.take_affected())
            test.assertEqual(cache.verdict, before,
                             "%s, re-adding %s: a verdict did not come back"
                             % (prefix, name))
            test.assertEqual(cache.ask(checks), before,
                             "%s, re-adding %s: the engine did not come back"
                             % (prefix, name))
    test.assertGreater(stats['removed'], 0, "no device was removed")
    return stats


# --- replacing a device whose structure changed (§8.2, D-R6) ----------------

def _with_extra_port(entry):
    """ Topology `entry` with one port more: a count grows by one, a list
    of numeric names gets the next free one. """
    entry = copy.deepcopy(entry)
    if isinstance(entry[2], int):
        entry[2] += 1
    else:
        entry[2] = list(entry[2]) + [str(max(int(p) for p in entry[2]) + 1)]
    return entry


def _with_entry(prefix, work, entry):
    """ Write `prefix`'s inputs to `work` with `entry` replacing the
    topology entry of its name. """
    for fname in _INPUTS:
        with open(os.path.join(prefix, fname)) as raw:
            data = json.load(raw)
        if fname == 'topology.json':
            data['devices'] = [entry if d[0] == entry[0] else d
                               for d in data['devices']]
        with open(os.path.join(work, fname), 'w') as out:
            json.dump(data, out)
    return work


def replace_each(test, make, prefix, names=None, leaks=None):
    """ D-R6's oracle: re-send each device of `prefix` (all, or `names`)
    with one port more, unlinked -- a structural change, so the aggregator
    REPLACES the device (§8.2's removal, the new model added, its links
    added again) as one update. The selective re-verification must equal a
    full one, and the full verdicts a from-zero build of the edited inputs.
    Then the original is re-sent, a replacement again (it drops the extra
    port, which no link uses), and every verdict must be back. A dropped
    link or a lost rule shows up as a verdict that differs from the build;
    an old device left in the engine beside the new one does not, so
    `leaks(engine)`, after each re-send, must list nothing. Returns the
    run's counts. """
    from util.in_process_driver import InProcessFaVe
    checks = inc.load_checks(os.path.join(prefix, 'checks.json'))
    with open(os.path.join(prefix, 'topology.json')) as raw:
        entries = json.load(raw)['devices']
    stats = {'replaced': 0, 'verdict_changes': 0, 'rechecked': 0}
    engine = make()
    with InProcessFaVe(engine, stable_indices=True) as fave:
        fave.replay(prefix)
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        before = cache.full()
        engine.take_affected()
        for entry in entries:
            name = entry[0]
            if names is not None and name not in names:
                continue
            for sent, label in ((_with_extra_port(entry), 'with a port more'),
                                (entry, 'as it was')):
                fave.resend_device(sent)
                test.assertIn('replaced', fave._agg.update_stats,
                              "%s, %s %s: not replaced" % (prefix, name, label))
                if leaks is not None:
                    test.assertEqual(leaks(engine), [], "%s, re-sending %s %s: "
                                     "the engine holds what no device has"
                                     % (prefix, name, label))
                stats['rechecked'] += len(cache.selective(engine.take_affected()))
                full = cache.ask(checks)
                test.assertEqual(cache.verdict, full,
                                 "%s, re-sending %s %s: selective re-verification "
                                 "missed a change" % (prefix, name, label))
                with tempfile.TemporaryDirectory(prefix='replace_') as work:
                    zero = inc.from_zero(make, _with_entry(prefix, work, sent),
                                         checks, set(), set(), like=engine)
                test.assertEqual(full, zero,
                                 "%s, re-sending %s %s: the incremental engine "
                                 "disagrees with a from-zero build" % (prefix, name, label))
                stats['verdict_changes'] += sum(
                    1 for line in full if full[line] != before[line])
            test.assertEqual(full, before, "%s, %s: a verdict did not come back"
                             % (prefix, name))
            stats['replaced'] += 1
    test.assertGreater(stats['replaced'], 0, "no device was replaced")
    return stats
