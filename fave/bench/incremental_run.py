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

""" ONE incremental stream on one engine, as raw records -- INCREMENTAL_PLAN.md
§5, §7 and O3–O5.

Builds a workload from zero through the real aggregator path, answers every
check once, then drives an update stream (S1, S2, S3) at the adapter in batches
of `--batch` updates, and writes what happened into `--cell-dir`:

* `head.json`      -- the arguments, stamps, the check set's hash, the initial
                      verdict of every check, the stream's hash;
* `stream.jsonl`   -- the stream, one update per line: position, op, rule key
                      or link;
* `updates.jsonl`  -- one line per batch, flushed as it completes: the
                      positions, `t_update_s` (the engine applying the batch,
                      including its default invariant checks, D1) and each
                      update's share of it, `t_recheck_s` (re-verifying the
                      checks the engine reported affected), the affected
                      (source, probe) pairs AS REPORTED (None: unknown, so every
                      check was re-verified), the checks whose verdict changed
                      with old and new verdict, RSS after the batch, and a
                      monotonic timestamp;
* `oracle.jsonl`   -- only in an oracle run (below);
* refusals         -- an update the engine refuses before changing anything
                      (APKeep: one that would need a new element) is recorded
                      in its batch's line with the reason, and the stream goes
                      on with the model as it was;
* `end.json`       -- written when the stream ends on its own.

Nothing is summarised here: every statistic is generated from these files by
`bench/incremental_report.py` (owner, 2026-10-09: keep the raw data). Lines are
flushed per batch, so a run stopped by a limit leaves its completed prefix, and
`updates.jsonl` doubles as the per-update stall clock of
`bench/incremental_cell.py`, which runs this under the limits.

**Timed runs carry no oracle** (O3.1): `precision` comes from the selective
re-check itself. **An oracle run** (`--oracle-sample k`, O3.3) is untimed in
spirit -- its timings are recorded but never reported -- and after each batch
asks a seeded random sample of k checks in full and compares them with the
cache (half (a) on a sample); every `--oracle-every` updates and at the end it
asks every check (half (a)) and builds the current model from zero on a fresh
engine (half (b)). A mismatch is a defect: it is recorded and stops the stream
with exit status 1.

Usage (from fave/, venv active):

    python3 bench/incremental_run.py bench/wl_ifi --engine netplumber \\
        --stream s2 --fraction 0.2 --seed 1 --batch 1 --cell-dir /tmp/cell
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import random
import resource
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

# pylint: disable=wrong-import-position
from bench.cell_run import engine_commit
from util import incremental as inc

#: 'apkeep' is BDD-APKeep (the name the first records carry); 'ndd-apkeep' is
#: NDD-APKeep, the same APKeep with NDD's atoms (APKEEP_INCREMENTAL_SCOPE.md §4)
ENGINES = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep', 'ad6')
#: `z`: the from-zero measurement alone -- the shared initialization without
#: the footprint pass, and no stream (INCREMENTAL_PLAN.md D17.10)
STREAMS = ('s1', 's2', 's3', 's4', 'z')

#: the engine's source tree, for `engine_commit`
_TREES = {'netplumber': ('net_plumber',), 'veriflow': ('veriflow_fr',),
          'apkeep': ('apkeep',), 'ndd-apkeep': ('apkeep', 'ndd'), 'ad6': ('ad6',)}

_PAGE_MB = resource.getpagesize() / (1024.0 * 1024.0)


def parse_footprint(text):
    """ "witness,dead-ends" -> ('witness', 'dead-ends'); "coarse" -> () (the
    coarse footprint); unknown modes refused. """
    from apkeep.lib_apkeep import FOOTPRINT_MODES
    if text == 'coarse':
        return ()
    modes = tuple(m for m in text.split(',') if m)
    unknown = [m for m in modes if m not in FOOTPRINT_MODES]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown footprint mode(s) %s; known: %s" % (unknown, ', '.join(FOOTPRINT_MODES)))
    return modes


def effective_footprint(engine, footprint):
    """ The footprint modes an engine runs with, as a list; [] when coarse or
    NetPlumber. The default is both modes on APKeep (owner, 2026-10-11) and
    on VeriFlow-FR (owner, 2026-10-15; VERIFLOW_FOOTPRINT_SCOPE.md §4.5). """
    from apkeep.lib_apkeep import DEFAULT_FOOTPRINT
    if engine == 'veriflow':
        from veriflow.adapter import DEFAULT_FOOTPRINT as VF_DEFAULT
        modes = VF_DEFAULT if footprint is None else footprint
        # in the adapter's order, which is what its stamp records
        return [m for m in ('witness', 'dead-ends') if m in modes]
    if engine not in ('apkeep', 'ndd-apkeep'):
        return []
    return list(DEFAULT_FOOTPRINT if footprint is None else footprint)


def _ndd_options(args):
    """ NDD-APKeep's library option for a record's head: whether atom
    collection visits each node once (ndd/FAVE_CHANGES.md §15). """
    if args.engine != 'ndd-apkeep':
        return {}
    return {'ndd_collect_visited': args.ndd_collect_visited}


def _engine_maker(args):
    """ `make_engine` with only the options a run set: a test stands in for
    `make_engine` with one taking the name alone. """
    options = {}
    if args.footprint is not None:
        options['footprint'] = args.footprint
    if args.ndd_collect_visited:
        options['ndd_collect_visited'] = True
    if args.engine == 'ad6':
        options['ad6'] = {'grounding': args.ad6_grounding, 'solver': args.ad6_solver,
                          'lite_acyclic': args.ad6_lite_acyclic}
    return make_engine(args.engine, **options)


def make_engine(name, footprint=None, ndd_collect_visited=False, ad6=None):
    log = logging.getLogger("incremental_run")
    log.setLevel(logging.WARNING)
    if name == 'ad6':
        # from zero only (D17.10); grounding and solver are NOT
        # interchangeable settings of one encoding, so they are always named
        # (cell_run.py, TODO item 0a)
        from ad6.adapter import Ad6Adapter
        return lambda: Ad6Adapter(log, **(ad6 or {}))
    if name == 'netplumber':
        from netplumber.lib_adapter import NetPlumberLibAdapter
        return lambda: NetPlumberLibAdapter(log)
    if name in ('apkeep', 'ndd-apkeep'):
        # BDD-APKeep, or NDD-APKeep -- APKeep's own network with NDD's atoms;
        # both take updates (APKEEP_INCREMENTAL_SCOPE.md). NDD-Flood builds from
        # zero only.
        from apkeep.adapter import APKeepAdapter
        apkeep_engine = 'bdd' if name == 'apkeep' else 'ndd-apkeep'
        # footprint None: the adapter's default (both modes)
        # ndd_collect_visited: NDD-APKeep only, off by default (ndd/FAVE_CHANGES.md §15)
        return lambda: APKeepAdapter(log, engine=apkeep_engine, footprint=footprint,
                                     ndd_collect_visited=ndd_collect_visited)
    from veriflow.adapter import VeriFlowAdapter
    # footprint None: the adapter's default (both modes)
    return lambda: VeriFlowAdapter(
        log, footprint=None if footprint is None else tuple(footprint))


def build_stream(kind, rules, links, fraction, seed):
    if kind == 's1':
        return list(inc.stream_s1(rules))
    if kind == 's2':
        return list(inc.stream_s2(rules, fraction, seed))
    return list(inc.stream_s3(links))


def rss_mb():
    """ This process's resident set -- every engine runs in-process (the
    NetPlumber and VeriFlow-FR libraries, the JVM through JPype). One read of
    `/proc/self/statm`, cheap enough for every batch. """
    with open('/proc/self/statm') as handle:
        return round(int(handle.read().split()[1]) * _PAGE_MB, 1)


def sha256_file(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def parse_files(spec):
    """ `topology=device_topology.json,policies=probes.json` -> a dict. """
    if not spec:
        return None
    return dict(item.split('=', 1) for item in spec.split(','))


class _Lines:
    """ A JSON-lines file, one flushed line per record. """

    def __init__(self, path):
        self.handle = open(path, 'w')

    def write(self, record):
        self.handle.write(json.dumps(record, separators=(',', ':'),
                                     sort_keys=True) + '\n')
        self.handle.flush()

    def close(self):
        self.handle.close()


def _write_json(path, record):
    with open(path, 'w') as handle:
        json.dump(record, handle, indent=1, sort_keys=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _oracle_sample(cache, checks, k, rng):
    """ Half (a) on a sample: ask `k` checks drawn now and return those whose
    full answer differs from the cache. """
    sample = checks if k >= len(checks) else rng.sample(checks, k)
    full = cache.ask(sample)
    return sorted(line for line in full if full[line] != cache.verdict[line])


def _start(make):
    """ The engine's construction, timed as `t_start_s` (D17.3); returns the
    engine and the phases recorder the rest of the initialization fills. """
    phases = inc.Phases()
    with phases.record('t_start_s'):
        engine = make()
    phases.live_heap = engine.live_heap_mb
    phases.memory['t_start_s']['live_heap_mb'] = engine.live_heap_mb()
    return engine, phases


def _verdict_stamps(head, cache, checks, expected):
    """ D17.6: the count is DISTINCT violated checks; valid when every check
    was answered (a failed build message has raised in `replay` already);
    `verdict_outcome` against a declared count, as V5's `correct`. """
    violations = sum(1 for v in cache.verdict.values() if v)
    head.update({'violations': violations, 'check_rounds': inc.count_rounds(checks),
                 'verdict_valid': len(cache.verdict) == len(checks),
                 'expected_violations': expected,
                 'verdict_outcome': (None if expected is None else
                                     'correct' if violations == expected else 'wrong_verdict')})


def _provenance(head, engine, workload, files, checks_path):
    """ D17.7: the artifacts and inputs by sha256, V5's engine stamps, the
    engine's build metrics. Outside every timer. """
    from util import provenance
    from util.in_process_driver import _BENCH_FILES
    names = dict(_BENCH_FILES, **(files or {}))
    head['artifacts'] = provenance.artifacts()
    head['inputs'] = provenance.inputs(
        workload, names, checks_path if os.path.exists(checks_path) else None)
    head.update(provenance.engine_stamps(head.get('configuration') or {}))
    head['build_metrics'] = engine.build_metrics()
    # D17.8: the cores this cell may use, and a JVM's view of them
    head['cpus'] = sorted(os.sched_getaffinity(0))
    try:
        from apkeep.lib_apkeep import jvm_stamps
        head['jvm'] = jvm_stamps()
    except ImportError:
        head['jvm'] = None


def _initialize(fave, engine, prefix, checks, head, phases, files=None, expected=None,
                footprint_pass=True):
    """ The shared initialization (INCREMENTAL_PLAN.md D17.2-3, D17.5): the
    phases, their memory and their wall-clock marks into `head`; returns the
    verdict cache, holding the first check's verdicts.
    `build_and_first_check_s` stays the sum of the phases after the
    engine's construction, so earlier analyses read alike. """
    cache, phases = inc.initialize(fave, engine, prefix, checks, files=files,
                                   phases=phases, footprint_pass=footprint_pass)
    head['phases'] = dict(phases.seconds)
    head['phase_memory'] = dict(phases.memory)
    head['phase_marks'] = list(phases.marks)
    head['build_and_first_check_s'] = sum(
        s for name, s in phases.seconds.items() if name != 't_start_s')
    _verdict_stamps(head, cache, checks, expected)
    head['rss_after_build_mb'] = rss_mb()
    head['configuration'] = engine.configuration_stamp()
    head['initial_verdicts'] = dict(cache.verdict)
    _provenance(head, engine, head['workload'], head.get('files'),
                head.get('checks_file') or '')
    return cache


def run_at_adapter(args):
    """ S1-S3 applied at the ADAPTER, bypassing the aggregator: M1's path,
    kept for development only (`--at-adapter`); measurements go through FaVe
    (`run`, INCREMENTAL_PLAN.md D14). """
    make = _engine_maker(args)
    files = parse_files(args.files)
    checks_path = os.path.join(args.workload, args.checks)
    # a workload without checks (wl_tum, D13) measures the updates alone
    checks = inc.load_checks(checks_path) if os.path.exists(checks_path) else []
    oracle = args.oracle_sample > 0 and bool(checks)
    os.makedirs(args.cell_dir, exist_ok=True)
    path = lambda name: os.path.join(args.cell_dir, name)

    head = {
        'what': 'incremental stream, raw records (INCREMENTAL_PLAN.md §5, §7)',
        'driven': 'adapter',
        'workload': args.workload, 'engine': args.engine, 'files': files,
        'stream': args.stream, 'fraction': args.fraction, 'seed': args.seed,
        'batch': args.batch, 'limit_updates': args.limit_updates,
        # the footprint modes in effect (APKEEP_INCREMENTAL_SCOPE.md §9,
        # VERIFLOW_FOOTPRINT_SCOPE.md §4); [] = the coarse footprint, the
        # default on APKeep before 2026-10-11 and on VeriFlow-FR before
        # 2026-10-15; NetPlumber has none
        'footprint': effective_footprint(args.engine, args.footprint),
        **_ndd_options(args),
        'oracle': ({'sample': args.oracle_sample, 'every': args.oracle_every,
                    'seed': args.oracle_seed} if oracle else None),
        'checks_file': checks_path if checks else None,
        'checks_sha256': sha256_file(checks_path) if checks else None,
        'started': _now(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True,
                                   check=False).stdout.strip(),
        # NDD-APKeep is two trees, the fork and the NDD library it runs on
        'engine_commit': (engine_commit(_TREES[args.engine][0])
                          if len(_TREES[args.engine]) == 1 else
                          ' + '.join(str(engine_commit(tree))
                                     for tree in _TREES[args.engine])),
    }
    engine, phases = _start(make)
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        # the footprint pass turns tracking on after the first check, so an
        # engine that records what its answers depended on (VeriFlow-FR's
        # walk footprints) has it before the first update
        cache = _initialize(fave, engine, args.workload, checks, head, phases,
                            files=files, expected=args.expect_violations)
        rules, links = inc.model_rules(fave), inc.model_links(fave)
        stream = build_stream(args.stream, rules, links, args.fraction, args.seed)
        if args.limit_updates:
            stream = stream[:args.limit_updates]

        out = _Lines(path('stream.jsonl'))
        for pos, (op, what, _rule) in enumerate(stream):
            out.write({'pos': pos, 'op': op, 'what': list(what)})
        out.close()
        head.update({'checks': len(checks), 'rules': len(rules),
                     'links': len(links), 'updates': len(stream),
                     'stream_sha256': sha256_file(path('stream.jsonl'))})
        _write_json(path('head.json'), head)
        engine.take_affected()

        updates = _Lines(path('updates.jsonl'))
        oracles = _Lines(path('oracle.jsonl')) if oracle else None
        rng = random.Random(args.oracle_seed)
        deleted, down = set(), set()
        failed = None
        done = n_refused = 0
        for b, start in enumerate(range(0, len(stream), args.batch)):
            batch = stream[start:start + args.batch]
            each = []
            refused = []
            t_a = time.perf_counter()
            for update in batch:
                t_u = time.perf_counter()
                inc.apply(engine, update, deleted, down, refused)
                each.append(time.perf_counter() - t_u)
            t_b = time.perf_counter()
            n_refused += len(refused)
            affected = engine.take_affected()
            rechecked = cache.selective(affected) if checks else []
            t_c = time.perf_counter()
            done = start + len(batch)
            updates.write({
                'b': b, 'pos': start, 'n': len(batch),
                'ops': [u[0] for u in batch],
                't_update_s': t_b - t_a, 't_each_s': each,
                't_recheck_s': t_c - t_b,
                'affected': (None if affected is None
                             else sorted([s, p] for s, p in affected)),
                'rechecked': len(rechecked),
                'changed': [list(c) for c in cache.last_changes] if checks else [],
                'refused': [[start + batch.index(u), reason]
                            for u, reason in refused],
                'rss_mb': rss_mb(), 'mono': time.monotonic(),
            })
            if not oracle:
                continue
            record = {'b': b, 'done': done,
                      'sample_mismatch': _oracle_sample(
                          cache, checks, args.oracle_sample, rng)}
            if (args.oracle_every and done // args.oracle_every
                    > start // args.oracle_every) or done == len(stream):
                t_o = time.perf_counter()
                full = cache.ask(checks)
                zero = inc.from_zero(make, args.workload, checks, deleted, down,
                                     files=files, like=engine)
                record.update({
                    'full': True,
                    'selective_vs_full': sorted(
                        l for l in full if full[l] != cache.verdict[l]),
                    'full_vs_zero': sorted(
                        l for l in full if full[l] != zero.get(l)),
                    't_full_and_zero_s': time.perf_counter() - t_o})
            oracles.write(record)
            if (record['sample_mismatch'] or record.get('selective_vs_full')
                    or record.get('full_vs_zero')):
                failed = record
                break
        updates.close()
        if oracles:
            oracles.close()

    # A stream whose every update the engine refused measured nothing: it is
    # `refused`, as S4 is when an edit is refused, not `completed` (the D11
    # run's wl_tum cells, FINDINGS.md finding 2)
    every_refused = bool(done) and n_refused == done
    _write_json(path('end.json'), {
        'finished': _now(), 'completed_updates': done,
        'status': ('oracle_failed' if failed else
                   'refused' if every_refused else 'completed')})
    if every_refused:
        print("REFUSED: the engine refused all %d updates; see updates.jsonl in %s"
              % (done, args.cell_dir), file=sys.stderr)
    return 1 if failed else 0


def _head(args, what, **extra):
    """ The stamps every cell carries. """
    checks_path = os.path.join(args.workload, args.checks)
    has_checks = os.path.exists(checks_path)
    oracle = args.oracle_sample > 0 and has_checks
    return {
        'what': what, **extra,
        'workload': args.workload, 'engine': args.engine,
        'stream': args.stream, 'fraction': args.fraction, 'seed': args.seed,
        'batch': args.batch, 'limit_updates': args.limit_updates,
        'footprint': effective_footprint(args.engine, args.footprint),
        **_ndd_options(args),
        'oracle': ({'sample': args.oracle_sample, 'every': args.oracle_every,
                    'seed': args.oracle_seed} if oracle else None),
        'checks_file': checks_path if has_checks else None,
        'checks_sha256': sha256_file(checks_path) if has_checks else None,
        'started': _now(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True,
                                   check=False).stdout.strip(),
        'engine_commit': (engine_commit(_TREES[args.engine][0])
                          if len(_TREES[args.engine]) == 1 else
                          ' + '.join(str(engine_commit(tree))
                                     for tree in _TREES[args.engine])),
    }


def run(args):
    """ S1-S3 driven THROUGH FaVe (INCREMENTAL_PLAN.md D14, owner: every
    measurement is driven through FaVe): configuration rule lines by
    re-sending the device, routes by `switch.py` commands, links by
    `topology.py` commands (`util.fave_streams`). A batch is sent as the
    fewest messages that keep its order, then re-checked once.

    Per batch, besides the fields of `run_at_adapter`: `messages`, one entry
    per message (its kind, how many updates, its time and, for a re-send,
    the aggregator's diff and engine times); `t_model_s` and `t_diff_s`, the
    re-sends' device regeneration and align+diff, summed; `t_update_s` is the
    rest of the messages' time -- FaVe taking a command or a diff to the
    engine and the engine applying it -- so `t_total` (the report's) is the
    whole time from the first message to the updated verdicts. A refused
    message changes nothing (the aggregator undoes it) and is recorded for
    each of its updates. """
    import tempfile
    from util import fave_streams as fs
    from util.barrier import BarrierError
    from util.in_process_driver import InProcessFaVe
    make = _engine_maker(args)
    files = parse_files(args.files)
    checks_path = os.path.join(args.workload, args.checks)
    checks = inc.load_checks(checks_path) if os.path.exists(checks_path) else []
    oracle = args.oracle_sample > 0 and bool(checks)
    os.makedirs(args.cell_dir, exist_ok=True)
    path = lambda name: os.path.join(args.cell_dir, name)
    head = _head(args, 'incremental stream through FaVe, raw records '
                       '(INCREMENTAL_PLAN.md §5, §7, D14)', driven='fave', files=files)
    engine, phases = _start(make)
    failed, done, n_refused = None, 0, 0
    with tempfile.TemporaryDirectory(prefix='stream_') as work, \
            InProcessFaVe(engine) as fave:
        wl = fs.FaveWorkload(args.workload, work, files=files)
        cache = _initialize(fave, engine, wl.zero_prefix(), checks, head,
                            phases, files=files, expected=args.expect_violations)
        stream = fs.build_stream(args.stream, wl, args.fraction, args.seed)
        if args.limit_updates:
            stream = stream[:args.limit_updates]
        out = _Lines(path('stream.jsonl'))
        for pos, (op, unit) in enumerate(stream):
            out.write({'pos': pos, 'op': op, 'what': wl.describe(unit)})
        out.close()
        head.update({'checks': len(checks), 'rules': len(wl.rules()),
                     'links': len(wl.links()), 'updates': len(stream),
                     'stream_sha256': sha256_file(path('stream.jsonl'))})
        _write_json(path('head.json'), head)
        engine.take_affected()

        updates = _Lines(path('updates.jsonl'))
        oracles = _Lines(path('oracle.jsonl')) if oracle else None
        rng = random.Random(args.oracle_seed)
        for b, start in enumerate(range(0, len(stream), args.batch)):
            batch = stream[start:start + args.batch]
            messages, refused = [], []
            t_model = t_diff = 0.0
            pos = start
            t_a = time.perf_counter()
            for op, units in wl.messages(batch):
                t_m = time.perf_counter()
                try:
                    sent = wl.send(fave, op, units)
                except BarrierError as err:
                    if 'UpdateRefused' not in str(err):
                        raise
                    refused.extend([p, str(err)] for p in range(pos, pos + len(units)))
                    sent = {'kind': 'refused'}
                took = time.perf_counter() - t_m
                entry = {'kind': sent['kind'], 'n': len(units), 't_s': took}
                stats = sent.get('stats')
                if stats:
                    entry.update(t_diff_s=stats.get('t_diff_s', 0.0),
                                 t_engine_s=stats.get('t_update_s', 0.0),
                                 deleted=stats.get('deleted'), inserted=stats.get('inserted'))
                    t_diff += entry['t_diff_s']
                    t_model += took - entry['t_diff_s'] - entry['t_engine_s']
                messages.append(entry)
                pos += len(units)
            t_b = time.perf_counter()
            n_refused += len(refused)
            affected = engine.take_affected()
            rechecked = cache.selective(affected) if checks else []
            t_c = time.perf_counter()
            done = start + len(batch)
            updates.write({
                'b': b, 'pos': start, 'n': len(batch),
                'ops': [u[0] for u in batch],
                't_update_s': (t_b - t_a) - t_model - t_diff,
                't_model_s': t_model, 't_diff_s': t_diff,
                't_each_s': [m['t_s'] for m in messages], 'messages': messages,
                't_recheck_s': t_c - t_b,
                'affected': (None if affected is None
                             else sorted([s, p] for s, p in affected)),
                'rechecked': len(rechecked),
                'changed': [list(c) for c in cache.last_changes] if checks else [],
                'refused': refused,
                'rss_mb': rss_mb(), 'mono': time.monotonic(),
            })
            if not oracle:
                continue
            record = {'b': b, 'done': done,
                      'sample_mismatch': _oracle_sample(
                          cache, checks, args.oracle_sample, rng)}
            if (args.oracle_every and done // args.oracle_every
                    > start // args.oracle_every) or done == len(stream):
                t_o = time.perf_counter()
                full = cache.ask(checks)
                zero = inc.from_zero(make, wl.zero_prefix(), checks, set(), set(),
                                     files=files, like=engine)
                record.update({
                    'full': True,
                    'selective_vs_full': sorted(
                        l for l in full if full[l] != cache.verdict[l]),
                    'full_vs_zero': sorted(
                        l for l in full if full[l] != zero.get(l)),
                    't_full_and_zero_s': time.perf_counter() - t_o})
            oracles.write(record)
            if (record['sample_mismatch'] or record.get('selective_vs_full')
                    or record.get('full_vs_zero')):
                failed = record
                break
        updates.close()
        if oracles:
            oracles.close()

    every_refused = bool(done) and n_refused == done
    _write_json(path('end.json'), {
        'finished': _now(), 'completed_updates': done,
        'status': ('oracle_failed' if failed else
                   'refused' if every_refused else 'completed')})
    if every_refused:
        print("REFUSED: FaVe refused all %d updates; see updates.jsonl in %s"
              % (done, args.cell_dir), file=sys.stderr)
    return 1 if failed else 0


def run_z(args):
    """ The from-zero measurement alone (INCREMENTAL_PLAN.md D17.10): the
    workload built and its compliance verified once, phases and stamps as
    every cell's, no footprint pass, no stream. For engines without an
    update path (ad6) and the `wl_berkeley` size series. """
    from util.in_process_driver import InProcessFaVe
    make = _engine_maker(args)
    files = parse_files(args.files)
    checks_path = os.path.join(args.workload, args.checks)
    checks = inc.load_checks(checks_path) if os.path.exists(checks_path) else []
    os.makedirs(args.cell_dir, exist_ok=True)
    head = _head(args, 'the from-zero measurement, no stream (INCREMENTAL_PLAN.md '
                       'D17.10)', driven='fave', files=files)
    engine, phases = _start(make)
    try:
        with InProcessFaVe(engine) as fave:
            _initialize(fave, engine, args.workload, checks, head, phases, files=files,
                        expected=args.expect_violations, footprint_pass=False)
            head.update({'checks': len(checks), 'updates': 0})
            _write_json(os.path.join(args.cell_dir, 'head.json'), head)
    finally:
        if hasattr(engine, 'release'):
            engine.release()
    _write_json(os.path.join(args.cell_dir, 'end.json'),
                {'status': 'completed', 'completed_updates': 0, 'finished': _now()})
    return 0


def run_s4(args):
    """ S4 (INCREMENTAL_PLAN.md §8.1): seeded one-line configuration edits,
    each re-sending its device through the aggregator with stable indices --
    a configuration change to an updated verdict. One record per edit:
    `t_model_s` (regenerate and send the device), `t_diff_s` (align and
    diff), `t_update_s` (the engine's rule updates), `t_recheck_s`, the
    engine-rule changes and relabels. A workload without checks (wl_tum)
    records everything but the re-check. """
    import tempfile
    from util.barrier import BarrierError
    from util.in_process_driver import InProcessFaVe
    make = _engine_maker(args)
    checks_path = os.path.join(args.workload, args.checks)
    checks = inc.load_checks(checks_path) if os.path.exists(checks_path) else []
    oracle = args.oracle_sample > 0 and bool(checks)
    n = args.limit_updates or 200
    os.makedirs(args.cell_dir, exist_ok=True)
    path = lambda name: os.path.join(args.cell_dir, name)
    head = {
        'what': 'S4 configuration edits, raw records (INCREMENTAL_PLAN.md §8.1)',
        'workload': args.workload, 'engine': args.engine, 'stream': 's4',
        'seed': args.seed, 'batch': 1, 'limit_updates': n, 'stable_indices': True,
        'footprint': effective_footprint(args.engine, args.footprint),
        **_ndd_options(args),
        'oracle': ({'sample': args.oracle_sample, 'every': args.oracle_every,
                    'seed': args.oracle_seed} if oracle else None),
        'checks_file': checks_path if checks else None,
        'checks_sha256': sha256_file(checks_path) if checks else None,
        'started': _now(),
        'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True,
                                   check=False).stdout.strip(),
        'engine_commit': (engine_commit(_TREES[args.engine][0])
                          if len(_TREES[args.engine]) == 1 else
                          ' + '.join(str(engine_commit(tree))
                                     for tree in _TREES[args.engine])),
    }
    engine, phases = _start(make)
    failed, done = None, 0
    with tempfile.TemporaryDirectory(prefix='s4_') as work, \
            InProcessFaVe(engine, stable_indices=True) as fave:
        configs = inc.S4Configs(args.workload, work)
        cache = _initialize(fave, engine, configs.zero_prefix(), checks, head,
                            phases, expected=args.expect_violations)
        head.update({'checks': len(checks), 'editable_rule_lines': len(configs.rule_lines()),
                     'updates': n})
        _write_json(path('head.json'), head)
        engine.take_affected()

        stream = _Lines(path('stream.jsonl'))
        updates = _Lines(path('updates.jsonl'))
        oracles = _Lines(path('oracle.jsonl')) if oracle else None
        rng = random.Random(args.oracle_seed)
        for pos, edit in enumerate(inc.stream_s4(configs, n, args.seed)):
            op, dev, line, text = edit
            stream.write({'pos': pos, 'op': op, 'device': configs.devices[dev][0],
                          'line': line, 'text': text})
            configs.apply(edit)
            t_a = time.perf_counter()
            try:
                configs.resend(fave, dev)
            except BarrierError as err:
                # a refused edit leaves the engine and the stored model as they
                # were, but the working copy edited: the stream cannot go on
                failed = {'pos': pos, 'refused': str(err)}
                break
            t_b = time.perf_counter()
            got = fave._agg.update_stats
            affected = engine.take_affected()
            rechecked = cache.selective(affected) if checks else []
            t_c = time.perf_counter()
            done = pos + 1
            updates.write({
                'b': pos, 'pos': pos, 'n': 1, 'ops': [op],
                'device': configs.devices[dev][0],
                't_model_s': (t_b - t_a) - got['t_diff_s'] - got['t_update_s'],
                't_diff_s': got['t_diff_s'], 't_update_s': got['t_update_s'],
                't_recheck_s': t_c - t_b,
                'deleted': got['deleted'], 'inserted': got['inserted'],
                'windows': got['windows'], 'moved': got['moved'],
                'affected': (None if affected is None
                             else sorted([s, p] for s, p in affected)),
                'rechecked': len(rechecked),
                'changed': [list(c) for c in cache.last_changes] if checks else [],
                'rss_mb': rss_mb(), 'mono': time.monotonic(),
            })
            if not oracle:
                continue
            record = {'b': pos, 'done': done,
                      'sample_mismatch': _oracle_sample(
                          cache, checks, args.oracle_sample, rng)}
            if (args.oracle_every and done % args.oracle_every == 0) or done == n:
                t_o = time.perf_counter()
                full = cache.ask(checks)
                zero_engine = make()
                zero_engine.track_affected(True)
                with InProcessFaVe(zero_engine) as zero:
                    zero.replay(configs.zero_prefix())
                    expected = inc.VerdictCache(zero, zero_engine, checks).full()
                if hasattr(zero_engine, 'release'):
                    zero_engine.release()
                record.update({
                    'full': True,
                    'selective_vs_full': sorted(
                        l for l in full if full[l] != cache.verdict[l]),
                    'full_vs_zero': sorted(
                        l for l in full if full[l] != expected.get(l)),
                    't_full_and_zero_s': time.perf_counter() - t_o})
            oracles.write(record)
            if (record['sample_mismatch'] or record.get('selective_vs_full')
                    or record.get('full_vs_zero')):
                failed = record
                break
        stream.close()
        updates.close()
        if oracles:
            oracles.close()
    refused = bool(failed and 'refused' in failed)
    _write_json(path('end.json'), {
        'finished': _now(), 'completed_updates': done,
        'status': ('refused' if refused else
                   'oracle_failed' if failed else 'completed')})
    if refused:
        # a result, not an oracle failure: the exit code says only the latter
        print("REFUSED at edit %d: %s" % (failed['pos'], failed['refused']), file=sys.stderr)
        return 0
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('workload', help="the workload directory, e.g. bench/wl_ifi")
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--ad6-grounding', default='rank', help="ad6 only (cell_run.py)")
    parser.add_argument('--ad6-solver', default='cadical195', help="ad6 only")
    parser.add_argument('--ad6-lite-acyclic', action='store_true', help="ad6 only")
    parser.add_argument('--expect-violations', type=int, default=None,
                        help="the workload's declared violation count (D17.6): "
                             "the head's verdict_outcome is correct or wrong_verdict")
    parser.add_argument('--stream', choices=STREAMS, required=True)
    parser.add_argument('--fraction', type=float, default=0.2,
                        help="S2: the share of rules deleted and re-added")
    parser.add_argument('--seed', type=int, default=1, help="S2: the stated seed")
    parser.add_argument('--batch', type=int, default=1,
                        help="updates per re-verification (D4)")
    parser.add_argument('--files', default=None,
                        help="replay file overrides, e.g. "
                             "topology=device_topology.json,policies=probes.json")
    parser.add_argument('--checks', default='checks.json',
                        help="the check set, relative to the workload")
    parser.add_argument('--limit-updates', type=int, default=0,
                        help="only the stream's first N updates (0: all)")
    parser.add_argument('--oracle-sample', type=int, default=0,
                        help="an oracle run: ask k sampled checks after each batch")
    parser.add_argument('--oracle-every', type=int, default=0,
                        help="an oracle run: full check and from-zero build "
                             "every N updates (always at the end)")
    parser.add_argument('--oracle-seed', type=int, default=1)
    parser.add_argument('--cell-dir', required=True)
    parser.add_argument('--footprint', type=parse_footprint, default=None,
                        help="APKeep engines and VeriFlow-FR: footprint modes, "
                             "comma-separated (witness, dead-ends; "
                             "APKEEP_INCREMENTAL_SCOPE.md §9, "
                             "VERIFLOW_FOOTPRINT_SCOPE.md §4), or 'coarse'; "
                             "default both")
    parser.add_argument('--at-adapter', action='store_true', default=False,
                        help="S1-S3 at the adapter, bypassing FaVe's aggregator "
                             "(M1's path; development only -- measurements go "
                             "through FaVe, INCREMENTAL_PLAN.md D14)")
    parser.add_argument('--ndd-collect-visited', action='store_true', default=False,
                        help="NDD-APKeep: the NDD library collects a molecule's "
                             "atoms visiting each node once (ndd/FAVE_CHANGES.md "
                             "§15); off by default, same atoms")
    args = parser.parse_args(argv)
    if args.ndd_collect_visited and args.engine != 'ndd-apkeep':
        parser.error("--ndd-collect-visited needs --engine ndd-apkeep")
    if args.engine == 'ad6' and args.stream != 'z':
        parser.error("ad6 has no update path: it runs the from-zero stream z only")
    if args.footprint is not None and args.engine not in ('apkeep', 'ndd-apkeep', 'veriflow'):
        parser.error("--footprint needs an APKeep engine or VeriFlow-FR")
    if args.batch < 1:
        parser.error("--batch must be at least 1")
    if args.oracle_every and not args.oracle_sample:
        parser.error("--oracle-every needs --oracle-sample")
    if args.stream == 's4' and args.batch != 1:
        parser.error("S4 runs at batch 1: every edit is one device re-sent")
    # D17.7: the in-process aggregator's log, at INFO (a line per task: V5's
    # phase times come from it), in the cell's directory
    os.makedirs(args.cell_dir, exist_ok=True)
    agg_log = logging.getLogger('Aggregator')
    handler = logging.FileHandler(os.path.join(args.cell_dir, 'aggregator.log'))
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    agg_log.addHandler(handler)
    agg_log.setLevel(logging.INFO)
    try:
        if args.stream == 'z':
            rc = run_z(args)
        elif args.stream == 's4':
            rc = run_s4(args)
        elif args.at_adapter:
            rc = run_at_adapter(args)
        else:
            rc = run(args)
    finally:
        agg_log.removeHandler(handler)
        handler.close()
    if rc:   # 1 means the oracle failed, and nothing else does
        print("THE ORACLE FAILED: see oracle.jsonl in %s" % args.cell_dir,
              file=sys.stderr)
    return rc


if __name__ == '__main__':
    sys.exit(main())
