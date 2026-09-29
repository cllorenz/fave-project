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
from bench.input_stamp import STAMP, StampError, read, sha256, verify, write
from bench.deltanet.fib_walk import reachability, reached_pairs
from bench.deltanet.policy import (
    emit_inventory, emit_policy, emit_walked_policy, homing_switches,
    role_endpoints)
from bench.deltanet.preparation import build_model, port_rule
from bench.deltanet.registry import DERIVED, prefix_of, trace_of
from bench.deltanet.sample import sample
from bench.deltanet.routers import (
    PORT_ASSIGNMENT, derive_router_topology, router_homes, router_rule)
from bench.deltanet.topology import derive_topology, homes
from bench.deltanet.trace import (
    FIELD4_LPM_PRIORITY, FIELD4_UNREAD, RAW, read_trace)
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

    #: Which manifest under `traces/` pins the trace.
    MANIFEST = 'SHA256SUMS'
    #: How the trace's fourth field is read -- D1's assertion, for airtel.
    FIELD4 = FIELD4_LPM_PRIORITY
    #: `routes.json`'s indentation. 2 keeps airtel's artifacts -- and so their
    #: stamps -- byte-identical to what they were; a 13M-rule model uses None.
    ROUTES_INDENT = 2

    def __init__(self, prefix, trace, **kwargs):
        #: The vendored CSV this run models, resolved under `traces/`. Stored
        #: before the base constructor, because a subclass method may run
        #: during it.
        self.trace = trace
        super().__init__(prefix, **kwargs)

    def _select(self, inserts):
        """ Which of the trace's inserts the model is built from: all of them.
        A subclass may measure a smaller snapshot, and stamps that it did. """
        return inserts

    def _derive(self, inserts):
        """ `(topology, homing, rule reading)` -- the `s<i>-<j>` reading. """
        return derive_topology(inserts), homes(inserts), port_rule

    def _policy_text(self, topology, homed, model):
        """ `reach.txt`. The homing states airtel's matrix (`policy.py`). The
        model is passed so a subclass can state one the homing cannot. """
        return emit_policy(topology, homed)

    def _pre_preparation(self):
        verify_raw(RAW, self.MANIFEST)

        inserts = self._select(read_trace(os.path.join(RAW, self.trace),
                                          field4=self.FIELD4))
        topology, homed, rule_of = self._derive(inserts)
        built = build_model(inserts, topology, homed, rule_of=rule_of)
        del inserts
        self.census = built['census']

        with open(self.files['roles_services'], 'w') as out:
            out.write(emit_inventory(topology, homed))
        with open(self.files['reach_policies'], 'w') as out:
            out.write(self._policy_text(topology, homed, built))

        with open(self.files['inventory'], 'w') as out:
            out.write(json.dumps(role_endpoints(topology), indent=2) + '\n')

        for key, payload, indent in (
                ('topology', built['topology'], 2),
                ('routes', built['routes'], self.ROUTES_INDENT),
                ('sources', built['sources'], 2),
                ('policies', built['probes'], 2),
        ):
            with open(self.files[key], 'w') as out:
                json.dump(payload, out, indent=indent)
                out.write('\n')
        del built

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
        extra.update(self._stamped_choices())
        drift = getattr(self, 'input_drift', None)
        if drift is not None:
            extra['drift_from_previous'] = drift
        return write(
            self.prefix,
            generator='bench.deltanet.workload',
            files=self._generated(),
            extra=extra)

    def _stamped_choices(self):
        """ Measurement-affecting choices a subclass makes (§3). None here:
        airtel's are all derived, and its stamp stays what it was. """
        return {}

    def check_stamp(self):
        """ The inputs are the ones the stamp recorded -- or say how they differ.

        Answers "has anything edited this directory since it was stamped?". It
        does NOT answer "did two runs get the same inputs?" when called after a
        run, because `run()` re-stamps: that comparison is `previous_drift`,
        made inside `_preparation` before the re-stamp, and recorded as
        `drift_from_previous` (CLOUD_BENCH_PLAN.md §2.13, 2026-09-29).
        """
        return verify(self.prefix, self._generated())


class RouterTraceBenchmark(DeltanetBenchmark):
    """ A trace that names ROUTERS and no ports -- `wl_berkeley` (§2.15).

    Differs from the family in four stamped choices, each forced by the data
    and none of them free:

      * the fourth field is NOT READ. D1 does not hold outside airtel (§2.14),
        and nothing here needs a priority: the tables declare LPM and every
        backend orders by prefix length;
      * the PORTS ARE INVENTED, as a renaming of the adjacency (`routers.py`);
      * a router with NO RULE for a prefix DROPS it. The alternative -- deliver
        it to that router's own border network -- would invent a second home
        for 25,433 prefixes the trace delivers at exactly one router each;
      * the MATRIX COMES FROM A WALK of the model (`fib_walk.py`), not from the
        homing: longest-prefix fallback reaches cells the homing cannot state.
        So the expectation is a second implementation of the forwarding
        semantics, checked against every engine -- still a consistency
        property, never an oracle.
    """

    MANIFEST = 'DERIVED.SHA256SUMS'
    FIELD4 = FIELD4_UNREAD
    ROUTES_INDENT = None

    def __init__(self, prefix, trace, keep_every=1, reuse_inputs=False,
                 **kwargs):
        #: 1/k of the prefixes plus every LPM witness (`sample.py`), for the
        #: size series; 1 is the whole trace. A constructor argument, stamped,
        #: and never an environment variable (`FAVE_DELTANET_TRACE`'s lesson).
        self.keep_every = keep_every
        #: Run on the inputs a previous generation stamped, instead of
        #: regenerating them. At full size generation peaks at ~16 GB, and
        #: `run()` would otherwise hold that process beside the engine's JVM
        #: (the NDD drill, §2.15). Refused unless the stamp verifies.
        self.reuse_inputs = reuse_inputs
        super().__init__(prefix, trace, **kwargs)

    def _pre_preparation(self):
        if not self.reuse_inputs:
            super()._pre_preparation()
            return
        verify_raw(RAW, self.MANIFEST)
        stamp = read(self.prefix)
        refusals = []
        if stamp.get('keep_every') != self.keep_every:
            refusals.append("the stamp is for keep_every=%s, not %d"
                            % (stamp.get('keep_every'), self.keep_every))
        if stamp.get('trace_sha256') != sha256(os.path.join(RAW, self.trace)):
            refusals.append("the stamp records another trace digest")
        refusals.extend(self.check_stamp())
        if refusals:
            raise StampError(
                "%s: refusing to reuse inputs -- %s. Regenerate them with "
                "`bash test/gen_deltanet_inputs.sh --keep-every %d %s`."
                % (self.prefix, '; '.join(refusals), self.keep_every,
                   os.path.basename(self.prefix)))
        self.census = stamp['census']
        self.lpm_sensitive_cells = [tuple(c)
                                    for c in stamp['lpm_sensitive_cells']]
        self.logger.info("reusing the inputs stamped in %s (%d rules)",
                         self.prefix, self.census['rules'])

    def _select(self, inserts):
        return sample(inserts, router_homes(inserts), self.keep_every)

    def _derive(self, inserts):
        return (derive_router_topology(inserts), router_homes(inserts),
                router_rule)

    def _policy_text(self, topology, homed, model):
        lpm = reached_pairs(reachability(model))
        inverted = reached_pairs(reachability(model, resolve='shortest'))
        #: §3's guard, run on the matrix itself: the cells inverting the
        #: priority would change. Non-empty is what airtel's matrix is not.
        self.lpm_sensitive_cells = sorted(lpm ^ inverted)
        self.logger.info(
            "fib walk: %d of %d cells reached; inverting LPM changes %d",
            len(lpm), len(topology.switches) ** 2,
            len(self.lpm_sensitive_cells))
        return emit_walked_policy(topology, lpm)

    def _stamped_choices(self):
        choices = {
            'field4': FIELD4_UNREAD,
            'port_assignment': PORT_ASSIGNMENT,
            'no_rule': 'dropped',
            'matrix_from': 'bench.deltanet.fib_walk (lpm)',
            'keep_every': self.keep_every,
            'inputs': 'reused' if self.reuse_inputs else 'generated',
        }
        sensitive = getattr(self, 'lpm_sensitive_cells', None)
        if sensitive is not None:
            choices['lpm_sensitive_cells'] = [list(cell) for cell in sensitive]
        return choices


def build(name, logger=None, **options):
    """ The benchmark for a registered workload -- the ONLY construction site.

    `use_internet` and `strict` are family properties, not per-workload ones, so
    they are set here: a driver that could forget them is a driver that can
    silently benchmark a different question. `--no-internet` because every
    border network is named and an unnamed outside would be a source this data
    set says nothing about; `--strict` because a border network reaching itself
    is not something airtel's data plane states, and the model deliberately
    installs no rule that would let it. (Berkeley's does state it, by hairpin --
    `RouterTraceBenchmark` -- and `--strict` is what turns its unreached
    diagonal into must-NOT-reach checks.)

    `options` go to the family's constructor -- `keep_every` for a derived
    workload's size series, and nothing for airtel, which refuses them.
    """
    family = RouterTraceBenchmark if name in DERIVED else DeltanetBenchmark
    return family(
        prefix_of(name), trace_of(name),
        logger=logger if logger else logging.getLogger(name),
        use_internet=False,
        strict=True,
        **options)


def generate_inputs(name, logger=None, **options):
    """ The model, the FPL, the checks and the stamp -- everything short of an
    engine. `run()` reaches the same steps through `_preparation`; this is the
    entry point for the integration tier, which needs them without a backend.

    `_preparation` is deliberately NOT called here: it would also delete
    /dev/shm state that a concurrent run may own.
    """
    run = build(name, logger=logger, **options)
    run._pre_preparation()
    run._generate_policy_matrix()
    run._convert_policy_to_checks()
    run.stamp()
    return run
