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

""" Deriving wl_cloud's oracle from the dataset's own Datalog instances.

WHY THIS EXISTS. `oracle.json` is what makes wl_cloud a correctness GATE
rather than a reachability report: it carries six verdicts produced outside
this repository. The first version of it was transcribed BY HAND from `grep`
output over the `.smt2` files -- which meant a single mistyped node id would
have produced a wrong oracle that FaVe then "agreed" with, a self-confirming
result with no way to notice.

That is the class of defect the whole benchmark suite is scripted to avoid, and
it is visible in this tree already: `wl_stanford/stanford-json/*.tf.json` cannot
be regenerated from the `stanford-tfs/*.tf` beside it (their rewrite masks are
inverted), so nobody can now say which of the two is authoritative. A derived
artifact with no derivation is a measurement resting on someone's eyesight.

So the oracle is DERIVED, and these tests pin the derivation rather than the
result: the argument order is read out of each file instead of assumed, and
anything the parser does not fully understand is refused rather than partially
returned -- a half-parsed query would silently weaken the gate.
"""

import hashlib
import json
import os
import unittest

from bench.wl_cloud.cloud_oracle import (
    Smt2ParseError,
    derive_oracle,
    parse_instance,
)


_PREFIX = 'bench/wl_cloud'
_RAW = os.path.join(_PREFIX, 'cloud-tf')

_HEAD = """(declare-rel R_1500000 ((_ BitVec 32) (_ BitVec 32) (_ BitVec 16)))
(declare-var vlan (_ BitVec 16))
"""


def _instance(body):
    return _HEAD + body


class TestParsingOneInstance(unittest.TestCase):
    """ The two source-relation forms the dataset actually uses. """

    def test_the_argument_order_is_read_from_the_query_not_assumed(self):
        """ The query line names the variables positionally, so the file states
        its own convention. Assuming a fixed order would silently mis-assign
        every constant if another scenario ordered them differently. """
        inst = _instance(
            "(rule (R_1500000 ip_src ip_dst tcp_src #x014C vlan #x06 tcp_ctrl))\n"
            "(query (R_1100043 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n")
        got = parse_instance('03.sat.smt2', inst)

        self.assertEqual(got['source'], 1500000)
        self.assertEqual(got['target'], 1100043)
        self.assertEqual(sorted(got['fields']), ['ip_proto=6', 'tcp_dst=332'])
        self.assertEqual(got['conditions'], [])
        self.assertEqual(got['expect'], 'sat')

    def test_an_unconstrained_source_yields_no_fields(self):
        inst = _instance(
            "(rule (R_1500000 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"
            "(query (R_1100323 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n")
        got = parse_instance('01.sat.smt2', inst)

        self.assertEqual(got['fields'], [])
        self.assertEqual(got['conditions'], [])

    def test_a_negated_guard_becomes_a_check_condition_not_a_field(self):
        """ `(not (= tcp_dst #x014B))` cannot be a generator header -- a
        generator carries values, not complements -- so it becomes a condition
        on the check instead. """
        inst = _instance(
            "(rule (=> (and (init ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl)"
            " (not (= tcp_dst #x014B)))\n"
            "          (R_1500000 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl)))\n"
            "(rule (init ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"
            "(query (R_1400233 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n")
        got = parse_instance('04.unsat.smt2', inst)

        self.assertEqual(got['source'], 1500000)
        self.assertEqual(got['target'], 1400233)
        self.assertEqual(got['fields'], [])
        self.assertEqual(got['conditions'], ['!tcp_dst:331'])
        self.assertEqual(got['expect'], 'unsat')

    def test_the_verdict_comes_from_the_filename(self):
        inst = _instance(
            "(rule (R_1 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"
            "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n")
        self.assertEqual(parse_instance('02.unsat.smt2', inst)['expect'], 'unsat')
        self.assertEqual(parse_instance('05.sat.smt2', inst)['expect'], 'sat')


class TestRefusals(unittest.TestCase):
    """ Anything not fully understood is refused. A half-parsed query would
    weaken the gate without changing its shape. """

    def test_a_file_with_no_query_is_refused(self):
        with self.assertRaises(Smt2ParseError):
            parse_instance('01.sat.smt2', _instance(
                "(rule (R_1 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"))

    def test_a_file_with_no_source_relation_is_refused(self):
        with self.assertRaises(Smt2ParseError):
            parse_instance('01.sat.smt2', _instance(
                "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"))

    def test_an_unknown_verdict_in_the_filename_is_refused(self):
        with self.assertRaises(Smt2ParseError):
            parse_instance('01.maybe.smt2', _instance(
                "(rule (R_1 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"
                "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"))

    def test_a_variable_the_field_map_does_not_know_is_refused(self):
        """ Silently dropping an unknown CONSTRAINED field would widen the
        query -- the direction that reports reachable what is not. The constant
        has to land on the unknown variable for this to bite, which is what the
        `#x06` in the `mystery` position does. """
        with self.assertRaises(Smt2ParseError):
            parse_instance('01.sat.smt2', _instance(
                "(rule (R_1 ip_src ip_dst tcp_src tcp_dst vlan #x06 tcp_ctrl))\n"
                "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan mystery tcp_ctrl))\n"))

    def test_an_unknown_variable_left_UNCONSTRAINED_is_accepted(self):
        """ The deliberate complement: a field nothing constrains cannot widen
        anything, so refusing it would reject a legal instance. """
        got = parse_instance('01.sat.smt2', _instance(
            "(rule (R_1 ip_src ip_dst tcp_src tcp_dst vlan mystery tcp_ctrl))\n"
            "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan mystery tcp_ctrl))\n"))

        self.assertEqual(got['fields'], [])

    def test_a_source_and_query_disagreeing_on_argument_order_is_refused(self):
        with self.assertRaises(Smt2ParseError):
            parse_instance('01.sat.smt2', _instance(
                "(rule (R_1 ip_dst ip_src tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"
                "(query (R_2 ip_src ip_dst tcp_src tcp_dst vlan ip_proto tcp_ctrl))\n"))


@unittest.skipUnless(
    os.path.isdir(_RAW) and len([f for f in os.listdir(_RAW) if f.endswith('.smt2')]) == 6,
    "%s does not hold the six vendored .smt2 instances" % _RAW)
class TestTheRealInstances(unittest.TestCase):
    """ The derivation against the vendored raw data.

    These assertions are the oracle itself. They are written out here, once, so
    that a change in the parser cannot quietly change what the benchmark is
    gated on -- the generated `oracle.json` is not tracked, and this is what
    stands in for reviewing it.
    """

    EXPECTED = [
        ('q01', '01.sat.smt2', 1500000, 1100323, [], [], 'sat'),
        ('q02', '02.unsat.smt2', 1500000, 1200449, [], [], 'unsat'),
        ('q03', '03.sat.smt2', 1500000, 1100043, ['ip_proto=6', 'tcp_dst=332'], [], 'sat'),
        ('q04', '04.unsat.smt2', 1500000, 1400233, [], ['!tcp_dst:331'], 'unsat'),
        ('q05', '05.sat.smt2', 1100380, 1000067, ['tcp_dst=350'], [], 'sat'),
        ('q06', '06.unsat.smt2', 1100376, 1000067, ['tcp_dst=351'], [], 'unsat'),
    ]

    @classmethod
    def setUpClass(cls):
        cls.oracle = derive_oracle(_RAW)

    def test_six_queries_are_derived(self):
        self.assertEqual(len(self.oracle['queries']), 6)

    def test_every_query_matches_the_verdicts_the_dataset_ships(self):
        for expected, got in zip(self.EXPECTED, self.oracle['queries']):
            name, smt2, source, target, fields, conditions, expect = expected
            self.assertEqual(got['name'], name)
            self.assertEqual(got['smt2'], smt2, name)
            self.assertEqual(got['source'], source, name)
            self.assertEqual(got['target'], target, name)
            self.assertEqual(sorted(got['fields']), sorted(fields), name)
            self.assertEqual(got['conditions'], conditions, name)
            self.assertEqual(got['expect'], expect, name)

    def test_three_sat_and_three_unsat(self):
        verdicts = [q['expect'] for q in self.oracle['queries']]
        self.assertEqual(verdicts.count('sat'), 3)
        self.assertEqual(verdicts.count('unsat'), 3)

    def test_each_query_records_the_checksum_of_the_instance_it_came_from(self):
        """ So a result file can name the exact bytes its verdicts came from. """
        for query in self.oracle['queries']:
            digest = hashlib.sha256(
                open(os.path.join(_RAW, query['smt2']), 'rb').read()).hexdigest()
            self.assertEqual(query['sha256'], digest, query['name'])

    def test_the_derivation_is_deterministic(self):
        self.assertEqual(
            json.dumps(derive_oracle(_RAW), sort_keys=True),
            json.dumps(self.oracle, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
