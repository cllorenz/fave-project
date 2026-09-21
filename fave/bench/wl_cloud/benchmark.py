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

THE CHECKS COME FROM AN FPL POLICY (§1.9), not from the oracle. That is the
owner's direction of 2026-09-18 and it changes what this benchmark is: the six
queries are expressed as five policy rules over a fabricated inventory, and
`bench/reach_csv_to_checks.py --complement` compiles them into 71 compliance
checks. Six carry a third-party verdict; the other 65 are expectations derived
from a policy WE wrote.

SO EVERY CHECK IS LABELLED BY PROVENANCE, and the two kinds are never summed.
`bench/wl_cloud/cloud_provenance.py` pairs each `.smt2` instance with the one
check that asks its question and REFUSES if any query is carried by none or by
several -- because the failure this replaces was exactly that: a check that went
missing still counted as agreement, since nothing had violated it.

AND AN EXPECTED VERDICT IS NOT AN EXPECTED PASS. A policy states an intent, so
where it disagrees with the dataset the reproduction IS a violation: query 06
asserts a permission this network does not grant, and the check generated for it
is expected to fail. `expected_violated` is where that lives, and `reach.txt`
says why each rule is written the way it is.

**Zero disagreements means all six third-party verdicts reproduced.** Any
disagreement is either a modelling bug here or the 331/332 port discrepancy
CLOUD_BENCH_PLAN.md §1.4 records -- check that one first.
"""

import datetime
import hashlib
import json
import logging
import os
import platform

from bench.generic_benchmark import GenericBenchmark
from bench.wl_cloud.cloud_endpoints import derive_endpoints, role_members
from bench.wl_cloud.cloud_oracle import derive_oracle
from bench.wl_cloud.cloud_preparation import build_model, write_model
from bench.wl_cloud.cloud_provenance import (
    check_key, pair_oracle_to_checks, parse_violations)
from bench.wl_cloud.cloud_tf import FAVE_MAPPING, classify_nodes, parse_tf


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


class CloudBenchmark(GenericBenchmark):
    """ The cloud workload, gated on the dataset's own verdicts. """

    def _pre_preparation(self):
        # Everything below is regenerated from the vendored raw scenario on
        # every run -- the transfer function AND the oracle. Nothing this
        # benchmark reads was produced by hand, which is the only way a
        # measurement can be recreated from the raw data later. The one
        # exception is the FPL inventory and policy, which state an INTENT and
        # so cannot be derived; `role_members` checks them against the model
        # instead.
        raw = self.files['cloud_raw']
        verify_raw(raw)

        with open(self.files['oracle'], 'w') as out:
            out.write(json.dumps(derive_oracle(raw), indent=2) + '\n')

        rules = parse_tf(open(self.files['cloud_tf'], 'r'))
        model = classify_nodes(rules)

        # BEFORE the model, not after: the policy decides which of the 1,201
        # endpoints are instantiated, and every generator costs a full flow
        # propagation whether or not a check asks about it.
        self._generate_policy_matrix()
        members = role_members(self.files['roles_json'], derive_endpoints(model))

        with open(self.files['inventory'], 'w') as out:
            out.write(json.dumps(
                dict((role, [member.name]) for role, member in members.items()),
                indent=2) + '\n')

        self.logger.info(
            "cloud model: %d devices, %d rules, %d roles -> %d endpoints",
            len(model.devices), len(rules), len(members),
            len(set(m.name for m in members.values())))

        built = build_model(rules, model, role_members=sorted(
            members.values(), key=lambda m: m.name))
        write_model(built, self.files)

        with open(self.files['mapping'], 'w') as out:
            out.write(json.dumps(FAVE_MAPPING, indent=2) + '\n')

    def _preparation(self):
        # The policy matrix is already generated (_pre_preparation needed it to
        # know which endpoints to build). What is left is turning it into
        # checks, and the artifact cleanup. The inventory and topology steps of
        # the base class are not run: this workload derives both from the
        # transfer function rather than from a per-workload generator script.
        self._delete_artifacts()
        self._convert_policy_to_checks()

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
        means the backend and its options, the model census, the sha256 of each
        `.smt2` the verdicts came from, and -- because the checks now come from
        a policy we wrote -- which checks carry a third-party verdict and which
        are our own.
        """
        oracle = json.load(open(self.files['oracle'], 'r'))
        checks = json.load(open(self.files['checks'], 'r'))

        topology = json.load(open(self.files['topology'], 'r'))
        routes = json.load(open(self.files['routes'], 'r'))
        sources = json.load(open(self.files['sources'], 'r'))
        probes = json.load(open(self.files['policies'], 'r'))

        report_path = self.files.get('report', 'report.md')
        violated = parse_violations(
            open(report_path, 'r').read() if os.path.isfile(report_path) else '')

        endpoint_of = {}
        for member in role_members(
                self.files['roles_json'],
                derive_endpoints(classify_nodes(
                    parse_tf(open(self.files['cloud_tf'], 'r'))))).values():
            endpoint_of[member.tx] = member.name
            endpoint_of[member.rx] = member.name

        # Raises rather than returning a partial answer: a verdict carried by
        # no check is not being tested, and reporting it as reproduced is the
        # vacuity this module exists to close.
        records = pair_oracle_to_checks(
            oracle['queries'], checks, endpoint_of)

        queries = []
        oracle_checks = set()
        for record in records:
            key = check_key(record['check'])
            oracle_checks.add(key)
            was_violated = key in violated
            queries.append(dict(
                record,
                violated=was_violated,
                agrees=was_violated == record['expected_violated'],
            ))

        disagreements = sorted(q['name'] for q in queries if not q['agrees'])

        # The other 65. Reported SEPARATELY and never added to the six: an
        # expectation we derived carries none of the authority of a verdict
        # produced outside this tree, and one table would hide the difference
        # (CLOUD_BENCH_PLAN.md §1.9.0).
        derived = [check_key(c) for c in checks]
        derived_violated = sum(
            1 for key in derived
            if key not in oracle_checks and key in violated)

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
            'checks_derived_by': 'bench/reach_csv_to_checks.py --complement',
            'queries': queries,
            'disagreements': disagreements,
            'reproduced': len(queries) - len(disagreements),
            'of': len(queries),
            'self_derived': {
                'checks': len(checks) - len(oracle_checks),
                'violated': derived_violated,
                'note': "expectations generated from bench/wl_cloud/reach.txt, "
                        "which is OUR policy -- not third-party verdicts, and "
                        "deliberately not summed with them",
            },
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
            "result stamped to %s: %d/%d oracle verdicts reproduced, "
            "%d/%d self-derived expectations violated%s",
            path, stamp['reproduced'], stamp['of'],
            derived_violated, stamp['self_derived']['checks'],
            " (SANDBOX -- wall-clock numbers are not comparable with the "
            "controlled environment)" if sandbox else "")


if __name__ == '__main__':

    files = {
        'cloud_raw': '%s/cloud-tf' % _PREFIX,
        'cloud_tf': '%s/cloud-tf/network.tf' % _PREFIX,
        'oracle': '%s/oracle.json' % _PREFIX,
        'mapping': '%s/mapping.json' % _PREFIX,
    }

    # AD6_PLAN.md §9.29: `length` and `mapping` are ONE setting and must be
    # passed TOGETHER. `length` pre-sizes net_plumber's vectors (BYTES);
    # `mapping` pre-sizes the ADAPTER's mapping, which every vector it builds is
    # sized from. Passing only `length` lets the engine start wider than the
    # adapter and reachability collapses SILENTLY. The mapping file is written
    # by _pre_preparation, so it is generated here before the run needs it.
    if not os.path.isfile(files['mapping']):
        with open(files['mapping'], 'w') as out:
            out.write(json.dumps(FAVE_MAPPING, indent=2) + '\n')

    CloudBenchmark(
        _PREFIX,
        logger=logging.getLogger('cloud'),
        extra_files=files,
        # The policy names `Internet`, which is where four of the six oracle
        # queries inject.
        use_internet=True,
        # No implicit self-policy: the dataset says nothing about a host
        # reaching itself, so a filled diagonal would be an expectation with no
        # source at all (reach_csv_to_checks --strict).
        strict=True,
        # "These services and NOTHING ELSE" -- the half of a conditional
        # permission that carries query 04 (CLOUD_BENCH_PLAN.md §1.9.3).
        use_complement=True,
        length=FAVE_MAPPING['length'] // 8,
        mapping=files['mapping'],
    ).run()
