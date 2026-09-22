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

""" Benchmarks FaVe on the Delta-net snapshot (CLOUD_BENCH_PLAN.md §2).

WHAT THIS WORKLOAD IS, AND WHAT IT IS NOT. The model is corroborated from
outside this repository: the Delta-net paper publishes 38,100 rules, 158 links
and 68 nodes for the data-plane snapshot its §4.3.2 reports on, and the
derivation matches all three (§2.3). A mis-parse of the traces would be caught
by something nobody here wrote.

THE VERDICTS ARE NOT SO CORROBORATED, and nothing in a result from this
workload may be written as though they were. The paper publishes query TIMES,
never answers, and it ships no statement of intent at all. So the reachability
matrix this benchmark checks is an expectation WE wrote (`deltanet_policy.py`),
derived from the same traces as the model -- a consistency property. It catches
a converter bug or a disagreement between engines; it cannot catch a misreading
of the trace that the model and the expectation share. §0's external-oracle gap
stays `wl_cloud`'s alone.

AND THE PAPER'S OWN GOALS WERE DIFFERENT ONES. §4.3.1 checks for forwarding
loops on every rule update; §4.3.2 asks "what is the fate of packets that are
using a link that fails", one query per link. Neither is a reachability matrix.
Reproducing those would be reproducing the EXPERIMENT; this reproduces the DATA
under a property of our own choosing, which is the weaker claim (§2.5).

WHAT THE RUN SHOULD REPORT: zero violations. 256 checks -- 210 must-reach, one
per ordered pair of border networks whose destination is addressable, and 46
must-NOT-reach, which is what keeps the matrix from being the all-reachable mesh
`AD6_PLAN.md` §5.5 records as satisfiable by any over-approximating engine. 30
of those 46 end at s8 or s9, which home no prefix; the other 16 are the
diagonal.
"""

import json
import logging
import os
import sys

from bench.generic_benchmark import GenericBenchmark
from bench.wl_deltanet.deltanet_policy import (
    emit_inventory, emit_policy, homing_switches, role_endpoints)
from bench.wl_deltanet.deltanet_preparation import build_model
from bench.wl_deltanet.deltanet_topology import derive_topology, homes
from bench.wl_deltanet.deltanet_trace import RAW, TRACES, read_trace
from util.raw_data import verify_raw


_PREFIX = 'bench/wl_deltanet'

#: Which vendored trace to model. airtel1 is the one the paper publishes
#: figures for (§2.3), so it is the default; airtel2 is the same network under
#: a different failure regime and is what §2.3's differential compares against.
TRACE = os.environ.get('FAVE_DELTANET_TRACE', TRACES[0])


class DeltanetBenchmark(GenericBenchmark):
    """ The Delta-net snapshot under a reachability matrix we wrote. """

    def _pre_preparation(self):
        verify_raw(RAW)

        inserts = read_trace(os.path.join(RAW, TRACE))
        topology = derive_topology(inserts)
        homed = homes(inserts)

        with open(self.files['roles_services'], 'w') as out:
            out.write(emit_inventory(topology, homed))
        with open(self.files['reach_policies'], 'w') as out:
            out.write(emit_policy(topology, homed))

        with open(self.files['inventory'], 'w') as out:
            out.write(json.dumps(role_endpoints(topology), indent=2) + '\n')

        built = build_model(inserts, topology, homed)
        self.census = built['census']

        for key, payload in (
                ('topology', built['topology']),
                ('routes', built['routes']),
                ('sources', built['sources']),
                ('policies', built['probes']),
        ):
            with open(self.files[key], 'w') as out:
                out.write(json.dumps(payload, indent=2) + '\n')

        self.logger.info(
            "deltanet model from %s: %d devices, %d links, %d rules "
            "(%d read from the trace + %d SYNTHESISED delivery rules), "
            "%d roles of which %d are addressable",
            TRACE, self.census['devices'], self.census['links'],
            self.census['rules'], self.census['transit_rules'],
            self.census['delivery_rules'], len(topology.switches),
            len(homing_switches(homed)))

    def _preparation(self):
        # No topogen/routegen/policygen: the model comes from the trace in
        # `_pre_preparation` and the inventory is emitted beside the policy.
        self._delete_artifacts()
        self._generate_policy_matrix()
        self._convert_policy_to_checks()


def main():
    logging.basicConfig(level=logging.INFO)

    run = DeltanetBenchmark(
        _PREFIX,
        logger=logging.getLogger('deltanet'),
        # No Internet role: every border network is named, and an unnamed
        # outside would be a source this data set says nothing about.
        use_internet=False,
        # No implicit self-policy -- `reach_csv_to_checks --strict`. A border
        # network reaching itself is not something this data plane states, and
        # the model deliberately installs no rule that would let it.
        strict=True,
    )
    run.run()


if __name__ == '__main__':
    sys.exit(main())
