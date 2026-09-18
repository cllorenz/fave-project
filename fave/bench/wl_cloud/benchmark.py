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

""" Benchmarks FaVe on the NoD cloud workload (CLOUD_BENCH_PLAN.md §1).

WHAT MAKES THIS WORKLOAD DIFFERENT from the other six: its verdicts come from
OUTSIDE this repository. The dataset ships six reachability queries as
Z3-Datalog instances, each labelled sat or unsat in its own filename by a tool
that predates this tree by a decade. Every other correctness result in the suite
is a consensus between implementations here -- see AD6_PLAN.md §9.28 and TODO.md
item 1s, which say so explicitly.

`oracle.json` IS DERIVED FROM THOSE INSTANCES ON EVERY RUN, never written by
hand (bench/wl_cloud/cloud_oracle.py, CLOUD_BENCH_PLAN.md §1.8). It was
hand-transcribed once, and that is the one thing this workload could not afford:
a mistyped node id would have produced a wrong oracle that FaVe then "agreed"
with, a self-confirming result with nothing able to notice.

So the gate is exact: the six queries become six compliance checks, a `sat`
query as "must reach" and an `unsat` one as "must not reach". **Zero violations
means all six third-party verdicts reproduced.** Any violation is either a
modelling bug here or the 331/332 port discrepancy CLOUD_BENCH_PLAN.md §1.4
records -- check that one first.

The policy-generation steps the other benchmarks run (PolicyTranslator over
`roles.txt`/`reach.txt`) are deliberately skipped: this phase's checks are the
dataset's own queries, not a policy of ours. Compiling the README's 26x26 ACL
matrix into a full compliance matrix is phase C7, after the oracle reproduces.
"""

import datetime
import hashlib
import json
import logging
import os
import platform
import re

from bench.generic_benchmark import GenericBenchmark
from bench.wl_cloud.cloud_oracle import derive_oracle
from bench.wl_cloud.cloud_preparation import Query, build_model, write_model
from bench.wl_cloud.cloud_tf import CLOUD_MAPPING, classify_nodes, parse_tf


_PREFIX = 'bench/wl_cloud'


class RawDataError(Exception):
    """ The vendored raw data does not match its manifest. """


def verify_raw(raw_dir):
    """ Check every vendored file against `SHA256SUMS`.

    The whole workload is regenerated from this directory on every run, so a
    byte that changed here silently changes what the benchmark measures. Loud,
    and BEFORE anything is derived: a manual edit made while debugging is
    exactly how a benchmark comes to measure something nobody intended, and it
    is unrecoverable once the edit is forgotten.
    """
    manifest = os.path.join(raw_dir, 'SHA256SUMS')
    if not os.path.isfile(manifest):
        raise RawDataError("%s is missing: the raw data has no manifest to "
                           "check against" % manifest)

    bad = []
    for line in open(manifest, 'r'):
        expected, name = line.split()
        path = os.path.join(raw_dir, name)
        if not os.path.isfile(path):
            bad.append("%s is missing" % name)
            continue
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if digest != expected:
            bad.append("%s: expected %s, found %s" % (name, expected, digest))

    if bad:
        raise RawDataError(
            "the vendored raw data under %s does not match SHA256SUMS:\n  %s"
            % (raw_dir, "\n  ".join(bad)))


def violated_queries(report_path):
    """ The query names `report.md` reports a violation for.

    Its own function, and tested, because a result stamp that always reports
    "all reproduced" is worse than no stamp at all -- it manufactures evidence.
    The report names a violating pair by its generator, and this workload names
    one generator per query (`source.q04`), so the generator name IS the query.
    """
    if not os.path.isfile(report_path):
        return set()

    violated = set()
    for line in open(report_path, 'r'):
        violated.update(re.findall(r'`source\.(\w+)`', line))
    return violated


def load_queries(path):
    """ The oracle's queries, in file order. """
    spec = json.load(open(path, 'r'))
    return [
        Query(
            name=q['name'],
            source=q['source'],
            target=q['target'],
            fields=q['fields'],
            expect=q['expect'],
        ) for q in spec['queries']
    ], spec


def build_checks(queries, spec):
    """ One `compliance_checker.py` line per query, conditions included.

    A query's `conditions` are check-level field conditions rather than
    generator fields because a generator cannot carry a NEGATED field: query 04
    asks about every port *other* than 331, which is `f=!tcp_dst:331` on the
    check (see `bench/compliance_checker.py`).
    """
    by_name = dict((q['name'], q) for q in spec['queries'])
    checks = []

    for query in queries:
        tokens = [query.check()]
        tokens.extend('f=%s' % c for c in by_name[query.name]['conditions'])
        checks.append(' '.join(tokens))

    return checks


class CloudBenchmark(GenericBenchmark):
    """ The cloud workload, gated on the dataset's own verdicts. """

    def _pre_preparation(self):
        # Everything below is regenerated from the vendored raw scenario on
        # every run -- the transfer function AND the oracle. Nothing this
        # benchmark reads was produced by hand, which is the only way a
        # measurement can be recreated from the raw data later.
        raw = self.files['cloud_raw']
        verify_raw(raw)

        with open(self.files['oracle'], 'w') as out:
            out.write(json.dumps(derive_oracle(raw), indent=2) + '\n')

        rules = parse_tf(open(self.files['cloud_tf'], 'r'))
        model = classify_nodes(rules)

        queries, spec = load_queries(self.files['oracle'])
        self.logger.info(
            "cloud model: %d devices, %d rules, %d queries (oracle derived "
            "from %d .smt2 instances)",
            len(model.devices), len(rules), len(queries),
            len([q for q in spec['queries']]))

        built = build_model(rules, model, queries=queries)
        write_model(built, self.files)

        with open(self.files['checks'], 'w') as out:
            out.write(json.dumps(build_checks(queries, spec), indent=2) + '\n')

        with open(self.files['mapping'], 'w') as out:
            out.write(json.dumps(CLOUD_MAPPING, indent=2) + '\n')

    def _preparation(self):
        # Only the artifact cleanup. The policy-matrix and inventory steps of
        # the base class need `roles.txt`/`reach.txt`, which this phase has no
        # use for -- its checks are the dataset's queries (see module docstring).
        self._delete_artifacts()

    def _report(self):
        super()._report()
        try:
            self._stamp_result()
        except Exception:                       # pylint: disable=broad-except
            # Non-fatal for the same reason _report is: by now the verdict
            # exists. But say so -- a silently missing stamp is how a number
            # ends up with no record of what produced it.
            self.logger.exception("could not write the result stamp")

    def _stamp_result(self):
        """ Write `eval/<backend>-<utc>.json`: the verdict plus everything
        needed to say what produced it.

        A run whose configuration is not recorded cannot be compared with
        another one -- AD6_PLAN.md's "every collapse of the configuration space
        must be a stamped result field, never an undocumented habit". Here that
        means the backend and its options, the model census, and the sha256 of
        each `.smt2` the verdicts came from.
        """
        oracle = json.load(open(self.files['oracle'], 'r'))
        queries = oracle['queries']

        violated = violated_queries(self.files.get('report', 'report.md'))

        topology = json.load(open(self.files['topology'], 'r'))
        routes = json.load(open(self.files['routes'], 'r'))
        sources = json.load(open(self.files['sources'], 'r'))
        probes = json.load(open(self.files['policies'], 'r'))

        # WHERE a measurement ran is part of what produced it. This project's
        # own guardrail trusts wall-clock numbers only from the controlled
        # bare-metal environment, and wl_stanford/eval/ already marks its
        # sandbox runs by filename -- but a marker somebody has to remember to
        # type is a marker that eventually goes missing. Detected and recorded
        # instead, and carried into the filename so the distinction survives a
        # directory listing.
        sandbox = bool(os.environ.get('YOLOBOX') or os.environ.get('container'))

        stamp = {
            'bench': 'cloud',
            'scenario': 'cloud/base',
            'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'sandbox': sandbox,
            'host': platform.node(),
            'platform': platform.platform(),
            'engine': self.backend,
            'engine_options': self.engine_options,
            'use_interweaving': self.use_interweaving,
            'hdr_len_bytes': self.length,
            'devices': len(topology['devices']),
            'links': len(topology['links']),
            'routes': len(routes),
            'generators': len(sources['devices']),
            'probes': len(probes['devices']),
            'oracle_derived_by': oracle['derived_by'],
            'queries': [
                {
                    'name': q['name'],
                    'smt2': q['smt2'],
                    'sha256': q['sha256'],
                    'expect': q['expect'],
                    'agrees': q['name'] not in violated,
                } for q in queries
            ],
            'violations': sorted(violated),
            'reproduced': len(queries) - len(violated),
            'of': len(queries),
        }

        odir = '%s/eval' % self.prefix
        if not os.path.isdir(odir):
            os.makedirs(odir)
        path = '%s/%s-%s%s.json' % (
            odir, self.backend,
            stamp['utc'].replace(':', '').replace('-', ''),
            '_sandbox' if sandbox else '')
        with open(path, 'w') as out:
            out.write(json.dumps(stamp, indent=2) + '\n')

        self.logger.info(
            "result stamped to %s: %d/%d oracle verdicts reproduced%s",
            path, stamp['reproduced'], stamp['of'],
            " (SANDBOX -- wall-clock numbers are not comparable with the "
            "controlled environment)" if sandbox else "")


if __name__ == '__main__':

    files = {
        'cloud_raw': '%s/cloud-tf' % _PREFIX,
        'cloud_tf': '%s/cloud-tf/network.tf' % _PREFIX,
        'oracle': '%s/oracle.json' % _PREFIX,
        'mapping': '%s/mapping.json' % _PREFIX,
        'inventory': 'bench/empty.json',
    }

    # AD6_PLAN.md §9.29: `length` and `mapping` are ONE setting and must be
    # passed TOGETHER. `length` pre-sizes net_plumber's vectors (BYTES);
    # `mapping` pre-sizes the ADAPTER's mapping, which every vector it builds is
    # sized from. Passing only `length` lets the engine start wider than the
    # adapter and reachability collapses SILENTLY. The mapping file is written
    # by _pre_preparation, so it is generated here before the run needs it.
    if not os.path.isfile(files['mapping']):
        with open(files['mapping'], 'w') as out:
            out.write(json.dumps(CLOUD_MAPPING, indent=2) + '\n')

    CloudBenchmark(
        _PREFIX,
        logger=logging.getLogger('cloud'),
        extra_files=files,
        use_internet=False,
        length=CLOUD_MAPPING['length'] // 8,
        mapping=files['mapping'],
    ).run()
