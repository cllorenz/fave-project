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

""" `TRACES.md` still describes the Delta-net traces (CLOUD_BENCH_PLAN.md §2).

The same two kinds of assertion as `test_cloud_census.py`, and the second kind
is the one that matters:

  * `test_document_is_current` compares the tracked file byte for byte with a
    fresh derivation. It catches an edit by hand and a reading that drifted,
    and it is worth exactly as much as the derivation behind it.

  * everything else asserts against facts established some OTHER way -- D1's
    identity checked by arithmetic rather than by the parser that enforces it,
    the parser's refusals, and the three figures the document corrects. A
    census that only agrees with itself is the failure mode being avoided, so
    the cross-checks do not go through `census()`.

This workload had a head start on that failure mode: three figures in
`deltanet-traces/README.md` were wrong from the day they were written, and
survived because nothing read them.
"""

import os
import unittest

from bench.wl_deltanet.deltanet_census import (
    DOCUMENT,
    PAPER_NODES,
    PAPER_SNAPSHOT_LINKS,
    PAPER_SNAPSHOT_RULES,
    build,
    census,
    pair_census,
    trace_census,
)
from bench.wl_deltanet.deltanet_trace import (
    PRIORITY_BASE,
    PRIORITY_SLOPE,
    RAW,
    TRACES,
    TraceError,
    collisions,
    edges,
    lpm_priority,
    parse_trace,
    read_trace,
)
from util.raw_data import RawDataError, verify_raw


def _load():
    return [read_trace(os.path.join(RAW, name)) for name in TRACES]


class TestDeltanetCensusDocument(unittest.TestCase):
    """ The tracked document is what the raw traces say today. """

    def test_document_is_current(self):
        with open(DOCUMENT) as handle:
            tracked = handle.read()

        self.assertEqual(
            tracked, build(),
            "TRACES.md no longer matches the raw data it claims to describe. "
            "It is GENERATED -- regenerate it with `python3 -m "
            "bench.wl_deltanet.deltanet_census` from fave/ rather than editing "
            "it, and read the diff before committing: a change here means the "
            "reading of the traces moved.")

    def test_document_is_tracked(self):
        self.assertTrue(os.path.isfile(DOCUMENT))

    def test_the_raw_traces_match_their_manifest(self):
        """ Nothing above is worth anything if the inputs moved. """
        verify_raw(RAW)


class TestDeltanetD1(unittest.TestCase):
    """ D1: the fourth field is `5 * prefix_length + 100`.

    Checked here by arithmetic over the raw bytes, NOT via `parse_trace` --
    which enforces the identity and would therefore confirm it by construction.
    """

    def test_every_row_of_every_trace_encodes_lpm_as_priority(self):
        rows = 0
        for name in TRACES:
            with open(os.path.join(RAW, name)) as handle:
                for number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    prefix, _router, _next_hop, priority = line.split(',')
                    plen = int(prefix.split('/')[1])
                    self.assertEqual(
                        int(priority), PRIORITY_SLOPE * plen + PRIORITY_BASE,
                        "%s:%d encodes something other than LPM in its fourth "
                        "field" % (name, number))
                    rows += 1

        self.assertEqual(rows, 76200, "both traces, every row")

    def test_the_identity_is_a_bijection_on_the_lengths_present(self):
        """ No two lengths share a priority, so the encoding loses nothing. """
        lengths = set()
        for inserts in _load():
            lengths |= {i.plen for i in inserts}
        self.assertEqual(
            len({lpm_priority(plen) for plen in lengths}), len(lengths))

    def test_the_lengths_are_14_to_32_without_31(self):
        """ The figure `deltanet-traces/README.md` had as 14-25. """
        lengths = set()
        for inserts in _load():
            lengths |= {i.plen for i in inserts}
        self.assertEqual(min(lengths), 14)
        self.assertEqual(max(lengths), 32)
        self.assertEqual(len(lengths), 18)
        self.assertNotIn(31, lengths)

    def test_the_priority_range_is_170_to_260(self):
        """ The figure both documents had as 180-220. """
        self.assertEqual(lpm_priority(14), 170)
        self.assertEqual(lpm_priority(32), 260)


class TestDeltanetTraceRefusals(unittest.TestCase):
    """ The parser refuses what it does not recognise, rather than skipping.

    A skipped line is a rule that silently is not in the model, and a
    forwarding model missing rules still answers every query -- just wrongly.
    """

    def test_a_withdrawal_is_refused(self):
        with self.assertRaises(TraceError) as caught:
            parse_trace(['-100.3.0.0/16,s10-1,s2-9,180'])
        self.assertIn('WITHDRAWAL', str(caught.exception))

    def test_a_priority_that_is_not_the_lpm_identity_is_refused(self):
        """ The guard that keeps D1 a finding rather than an assumption. """
        with self.assertRaises(TraceError):
            parse_trace(['+100.3.0.0/16,s10-1,s2-9,181'])

    def test_a_malformed_line_is_refused(self):
        for line in ('+100.3.0.0/16,s10-1,s2-9',
                     '100.3.0.0/16,s10-1,s2-9,180',
                     '+100.3.0.0,s10-1,s2-9,180',
                     'nonsense'):
            with self.assertRaises(TraceError):
                parse_trace([line])

    def test_blank_lines_are_skipped_and_a_good_line_parses(self):
        inserts = parse_trace(['', '+100.3.0.0/16,s10-1,s2-9,180', ''])
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0].plen, 16)
        self.assertEqual(inserts[0].router, 's10-1')
        self.assertEqual(inserts[0].next_hop, 's2-9')

    def test_a_missing_manifest_is_refused(self):
        self.assertRaises(RawDataError, verify_raw, os.path.dirname(RAW))


class TestDeltanetShape(unittest.TestCase):
    """ The structural facts D2/D3 rest on, counted without `census()`. """

    @classmethod
    def setUpClass(cls):
        cls.left, cls.right = _load()

    def test_no_insert_overwrites_an_earlier_one(self):
        """ Why the final FIB is the file: replay order cannot matter. """
        for inserts in (self.left, self.right):
            self.assertEqual(collisions(inserts), 0)
            self.assertEqual(
                len({(i.router, i.prefix) for i in inserts}), len(inserts))

    def test_both_traces_carry_1400_prefixes(self):
        """ The figure stated of airtel2 alone. """
        for inserts in (self.left, self.right):
            self.assertEqual(len({i.prefix for i in inserts}), 1400)
            self.assertEqual(len(inserts), 38100)

    def test_next_hops_are_not_a_subset_of_routers(self):
        """ The sinks -- a D3 modelling decision, not a defect. """
        for inserts in (self.left, self.right):
            routers = {i.router for i in inserts}
            next_hops = {i.next_hop for i in inserts}
            self.assertTrue(next_hops - routers)
            self.assertTrue(routers - next_hops)

    def test_the_pair_shares_everything_but_the_routing(self):
        pair = pair_census(self.left, self.right)
        self.assertTrue(pair['same_prefixes'])
        self.assertTrue(pair['same_routers'])
        self.assertTrue(pair['same_next_hops'])
        self.assertFalse(pair['same_edges'])
        self.assertTrue(pair['differing_next_hop'] > 0)

    def test_census_agrees_with_counts_taken_directly(self):
        """ One end-to-end tie between `trace_census` and the raw lists. """
        c = trace_census(TRACES[0], self.left)
        self.assertEqual(c['inserts'], len(self.left))
        self.assertEqual(c['prefixes'], len({i.prefix for i in self.left}))
        self.assertEqual(c['routers'], len({i.router for i in self.left}))
        self.assertEqual(
            sum(c['plen_histogram'].values()), len(self.left))

    def test_census_reads_both_traces(self):
        self.assertEqual(len(census()['traces']), len(TRACES))


class TestDeltanetAgainstThePublishedPaper(unittest.TestCase):
    """ The derivation against figures published OUTSIDE this repository.

    Horn, Kheradmand and Prasad, "Delta-net: Real-time Network Verification
    Using Atoms", NSDI'17. Every other assertion in this file checks the
    derivation against the traces or against itself; these three check it
    against a third party, which is the only kind of check that can catch a
    reading of the data that is self-consistent and wrong.

    They are also what IDENTIFIES the file. Table 4's "consistent data plane
    snapshot" extracted from ONOS has 38,100 rules, §4.3.2 poses 158 queries on
    it (one per link), and Table 2 gives 68 nodes. `airtel1-only-inserts.csv`
    matches all three, so it is not merely "an insert trace" -- it is that
    published snapshot.

    What this does NOT establish is any reachability verdict. The paper's
    results are query times, not answers, so this workload still has no
    external oracle (CLOUD_BENCH_PLAN.md §0).
    """

    @classmethod
    def setUpClass(cls):
        cls.snapshot = read_trace(os.path.join(RAW, TRACES[0]))

    def test_the_snapshot_has_the_published_rule_count(self):
        """ Table 4, second column. """
        self.assertEqual(len(self.snapshot), PAPER_SNAPSHOT_RULES)

    def test_the_snapshot_has_the_published_link_count(self):
        """ §4.3.2: "the new Airtel data plane snapshot where we pose 158
        queries" -- the query count is the link count. """
        self.assertEqual(len(edges(self.snapshot)), PAPER_SNAPSHOT_LINKS)

    def test_the_snapshot_has_the_published_node_count(self):
        """ Table 2, and the reason a node is not a switch: the paper splits a
        switch per matched input port, 16 switches becoming 68 graph nodes. """
        names = ({i.router for i in self.snapshot}
                 | {i.next_hop for i in self.snapshot})
        self.assertEqual(len(names), PAPER_NODES)


if __name__ == '__main__':
    unittest.main()
