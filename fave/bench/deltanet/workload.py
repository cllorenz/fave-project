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

""" The benchmark that every Delta-net workload IS (CLOUD_BENCH_PLAN.md §2).

One class for the whole family, parameterised by the trace. What differs
between `wl_airtel1` and `wl_airtel2` is the CSV and the output directory;
nothing about the model, the property or the run differs at all, which is why
this lives here and a driver is fifteen lines.

WHAT THIS WORKLOAD IS, AND WHAT IT IS NOT. The model is corroborated from
outside this repository: the Delta-net paper publishes 38,100 rules, 158 links
and 68 nodes for the data-plane snapshot its §4.3.2 reports on, and the
derivation matches all three (§2.3). A mis-parse of the traces would be caught
by something nobody here wrote.

THE VERDICTS ARE NOT SO CORROBORATED, and nothing in a result from this
workload may be written as though they were. The paper publishes query TIMES,
never answers, and it ships no statement of intent at all. So the reachability
matrix this benchmark checks is an expectation WE wrote (`policy.py`), derived
from the same traces as the model -- a consistency property. It catches a
converter bug or a disagreement between engines; it cannot catch a misreading
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

**The trace is a constructor argument and not an environment variable.** It was
one -- `FAVE_DELTANET_TRACE` -- and in the whole life of that selector nothing
ever set it, while the directory it wrote into said nothing about which trace
had produced it (§2.3's correction, and D6). A workload directory now names its
trace, and the registry is the only place that mapping exists.
"""

import json
import logging
import os

from bench.generic_benchmark import GenericBenchmark
from bench.input_stamp import STAMP, StampError, sha256, verify, write
from bench.deltanet.policy import (
    emit_inventory, emit_policy, homing_switches, role_endpoints)
from bench.deltanet.preparation import build_model
from bench.deltanet.registry import WORKLOADS, prefix_of
from bench.deltanet.topology import derive_topology, homes
from bench.deltanet.trace import RAW, read_trace
from util.raw_data import verify_raw


#: What `drift_from_previous` records when there was no earlier stamp to compare
#: against -- a first run, or a directory someone cleaned. Not the same as "no
#: drift", so it is not recorded as an empty list.
NO_PREVIOUS_STAMP = 'no previous stamp'


def previous_drift(prefix, files):
    """ How `files`, as just regenerated, differ from the stamp the PREVIOUS
    run left in `prefix` -- to be called BEFORE this run re-stamps.

    `[]` is the only clean answer; `NO_PREVIOUS_STAMP` when there is nothing to
    compare against. An unreadable stamp is reported as drift rather than
    raised: this is a warn-and-record check (owner, 2026-09-29), and a stamp
    that cannot be read is exactly the thing a reader should be told about.
    """
    if not os.path.isfile(os.path.join(prefix, STAMP)):
        return NO_PREVIOUS_STAMP
    try:
        return verify(prefix, files)
    except StampError as exc:
        return ["the previous stamp is unusable: %s" % exc]


class DeltanetBenchmark(GenericBenchmark):
    """ The Delta-net snapshot under a reachability matrix we wrote. """

    def __init__(self, prefix, trace, **kwargs):
        #: The vendored CSV this run models, resolved under `traces/`. Stored
        #: before the base constructor, because a subclass method may run
        #: during it.
        self.trace = trace
        super().__init__(prefix, **kwargs)

    def _pre_preparation(self):
        verify_raw(RAW)

        inserts = read_trace(os.path.join(RAW, self.trace))
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
            self.trace, self.census['devices'], self.census['links'],
            self.census['rules'], self.census['transit_rules'],
            self.census['delivery_rules'], len(topology.switches),
            len(homing_switches(homed)))

    def _preparation(self):
        # No topogen/routegen/policygen: the model comes from the trace in
        # `_pre_preparation` and the inventory is emitted beside the policy.
        self._delete_artifacts()
        self._generate_policy_matrix()
        self._convert_policy_to_checks()
        # BEFORE re-stamping: afterwards the only stamp left is this run's own,
        # and comparing against it cannot see anything (CLOUD_BENCH_PLAN.md
        # §2.13, found 2026-09-29 -- D7's "no drift" was that comparison).
        # Warn and record, never refuse: the drift also lands in the new stamp.
        self.input_drift = previous_drift(self.prefix, self._generated())
        if self.input_drift == NO_PREVIOUS_STAMP:
            self.logger.info("input stamp: %s in %s, nothing to compare",
                             NO_PREVIOUS_STAMP, self.prefix)
        elif self.input_drift:
            self.logger.warning(
                "INPUT DRIFT: %s now differs from the previous run's inputs "
                "-- results are not comparable across the two runs: %s",
                self.prefix, '; '.join(self.input_drift))
        self.stamp()

    def _generated(self):
        """ Every file this workload derives, by label. `np_config` is excluded:
        it is shared (`bench/np.conf`) and lives outside the prefix, so it is
        not this directory's to record. """
        return {label: path for label, path in self.files.items()
                if label != 'np_config' and path.startswith(self.prefix + '/')}

    def stamp(self):
        """ Record what this directory now holds, and from what.

        A benchmark run also records `drift_from_previous`: how its inputs
        differed from the run before it (`previous_drift`). `generate_inputs`
        does not check, so its stamp carries no such key -- regenerating is the
        sanctioned way to accept new inputs, not a comparison.
        """
        extra = {
            'trace': self.trace,
            'trace_sha256': sha256(os.path.join(RAW, self.trace)),
            'census': self.census,
        }
        drift = getattr(self, 'input_drift', None)
        if drift is not None:
            extra['drift_from_previous'] = drift
        return write(
            self.prefix,
            generator='bench.deltanet.workload',
            files=self._generated(),
            extra=extra)

    def check_stamp(self):
        """ The inputs are the ones the stamp recorded -- or say how they differ.

        Answers "has anything edited this directory since it was stamped?". It
        does NOT answer "did two runs get the same inputs?" when called after a
        run, because `run()` re-stamps: that comparison is `previous_drift`,
        made inside `_preparation` before the re-stamp, and recorded as
        `drift_from_previous` (CLOUD_BENCH_PLAN.md §2.13, 2026-09-29).
        """
        return verify(self.prefix, self._generated())


def build(name, logger=None):
    """ The benchmark for a registered workload -- the ONLY construction site.

    `use_internet` and `strict` are family properties, not per-workload ones, so
    they are set here: a driver that could forget them is a driver that can
    silently benchmark a different question. `--no-internet` because every
    border network is named and an unnamed outside would be a source this data
    set says nothing about; `--strict` because a border network reaching itself
    is not something this data plane states, and the model deliberately installs
    no rule that would let it.
    """
    return DeltanetBenchmark(
        prefix_of(name), WORKLOADS[name],
        logger=logger if logger else logging.getLogger(name),
        use_internet=False,
        strict=True)


def generate_inputs(name, logger=None):
    """ The model, the FPL, the checks and the stamp -- everything short of an
    engine. `run()` reaches the same steps through `_preparation`; this is the
    entry point for the integration tier, which needs them without a backend.

    `_preparation` is deliberately NOT called here: it would also delete
    /dev/shm state that a concurrent run may own.
    """
    run = build(name, logger=logger)
    run._pre_preparation()
    run._generate_policy_matrix()
    run._convert_policy_to_checks()
    run.stamp()
    return run
