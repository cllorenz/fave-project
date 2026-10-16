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
ENGINES = ('netplumber', 'veriflow', 'apkeep', 'ndd-apkeep')
STREAMS = ('s1', 's2', 's3', 's4')

#: the engine's source tree, for `engine_commit`
_TREES = {'netplumber': ('net_plumber',), 'veriflow': ('veriflow_fr',),
          'apkeep': ('apkeep',), 'ndd-apkeep': ('apkeep', 'ndd')}

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
    return make_engine(args.engine, **options)


def make_engine(name, footprint=None, ndd_collect_visited=False):
    log = logging.getLogger("incremental_run")
    log.setLevel(logging.WARNING)
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


def run(args):
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
    engine = make()
    from util.in_process_driver import InProcessFaVe
    with InProcessFaVe(engine) as fave:
        t0 = time.perf_counter()
        fave.replay(args.workload, files=files)
        # On BEFORE the first answers, so an engine that records what its
        # answers depended on (VeriFlow-FR's walk footprints) has it.
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        if checks:
            cache.full()
        head['build_and_first_check_s'] = time.perf_counter() - t0
        head['rss_after_build_mb'] = rss_mb()
        head['configuration'] = engine.configuration_stamp()
        head['initial_verdicts'] = dict(cache.verdict)
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
    engine = make()
    failed, done = None, 0
    with tempfile.TemporaryDirectory(prefix='s4_') as work, \
            InProcessFaVe(engine, stable_indices=True) as fave:
        configs = inc.S4Configs(args.workload, work)
        t0 = time.perf_counter()
        fave.replay(configs.zero_prefix())
        engine.track_affected(True)
        cache = inc.VerdictCache(fave, engine, checks)
        if checks:
            cache.full()
        head['build_and_first_check_s'] = time.perf_counter() - t0
        head['rss_after_build_mb'] = rss_mb()
        head['configuration'] = engine.configuration_stamp()
        head['initial_verdicts'] = dict(cache.verdict)
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
    parser.add_argument('--ndd-collect-visited', action='store_true', default=False,
                        help="NDD-APKeep: the NDD library collects a molecule's "
                             "atoms visiting each node once (ndd/FAVE_CHANGES.md "
                             "§15); off by default, same atoms")
    args = parser.parse_args(argv)
    if args.ndd_collect_visited and args.engine != 'ndd-apkeep':
        parser.error("--ndd-collect-visited needs --engine ndd-apkeep")
    if args.footprint is not None and args.engine not in ('apkeep', 'ndd-apkeep', 'veriflow'):
        parser.error("--footprint needs an APKeep engine or VeriFlow-FR")
    if args.batch < 1:
        parser.error("--batch must be at least 1")
    if args.oracle_every and not args.oracle_sample:
        parser.error("--oracle-every needs --oracle-sample")
    if args.stream == 's4':
        if args.batch != 1:
            parser.error("S4 runs at batch 1: every edit is one device re-sent")
        rc = run_s4(args)
    else:
        rc = run(args)
    if rc:   # 1 means the oracle failed, and nothing else does
        print("THE ORACLE FAILED: see oracle.jsonl in %s" % args.cell_dir,
              file=sys.stderr)
    return rc


if __name__ == '__main__':
    sys.exit(main())
