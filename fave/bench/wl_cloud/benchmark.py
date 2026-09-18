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
OUTSIDE this repository. `oracle.json` transcribes six reachability queries the
dataset ships as Z3-Datalog instances, each labelled sat or unsat in its own
filename by a tool that predates this tree by a decade. Every other correctness
result in the suite is a consensus between implementations here -- see
AD6_PLAN.md §9.28 and TODO.md item 1s, which say so explicitly.

So the gate is exact: the six queries become six compliance checks, a `sat`
query as "must reach" and an `unsat` one as "must not reach". **Zero violations
means all six third-party verdicts reproduced.** Any violation is either a
modelling bug here or the port discrepancy `oracle.json` records under
`open_discrepancy` -- check that one first.

The policy-generation steps the other benchmarks run (PolicyTranslator over
`roles.txt`/`reach.txt`) are deliberately skipped: this phase's checks are the
dataset's own queries, not a policy of ours. Compiling the README's 26x26 ACL
matrix into a full compliance matrix is phase C7, after the oracle reproduces.
"""

import json
import logging
import os

from bench.generic_benchmark import GenericBenchmark
from bench.wl_cloud.cloud_preparation import Query, build_model, write_model
from bench.wl_cloud.cloud_tf import CLOUD_MAPPING, classify_nodes, parse_tf


_PREFIX = 'bench/wl_cloud'


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
        rules = parse_tf(open(self.files['cloud_tf'], 'r'))
        model = classify_nodes(rules)

        queries, spec = load_queries(self.files['oracle'])
        self.logger.info(
            "cloud model: %d devices, %d rules, %d queries",
            len(model.devices), len(rules), len(queries))

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


if __name__ == '__main__':

    files = {
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
