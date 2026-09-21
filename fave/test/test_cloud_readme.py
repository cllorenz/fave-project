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

""" The cloud dataset's own inventory, and the algebra that reads it (C7).

`cloud-tf/README.txt` is the source of wl_cloud's FPL policy, so everything the
policy rests on is derived here and pinned here. Three things in particular,
each of which CLOUD_BENCH_PLAN.md left open or assumed:

  * **service i <-> port 331+i <-> public address 121.140.254.i.** The README
    states a "Public TCP port: 331" and 25 services and never relates them.
    Asserted against `network.tf` in both directions.

  * **Index 25 is the Internet** (§1.9.5 asked for this "from the data, not
    assumed"). FOUR independently derived sets are asserted equal: matrix row
    25, the ACL rules with no source constraint, the gateway's destination-NAT
    rules, and the cores' source-NAT egress rules. Any one of them alone would
    be a coincidence; four is the identification.

  * **The matrix's private half is the data plane, exactly.** Every
    source-constrained ACL rule is a 1-cell and every 1-cell into a
    source-constrained service is a rule -- set equality, both directions, no
    slack. That is what makes the 173 unauthorised-but-reachable cells into
    PUBLIC services a finding about the generator rather than noise in the
    reading.

These are tests against the vendored dataset, not against a fixture, so they
fail if the reading drifts OR if the raw data changes.
"""

import collections
import ipaddress
import os
import unittest

from bench.wl_cloud.cloud_readme import (
    INTERNET_INDEX,
    CloudReadme,
    ReadmeParseError,
    parse_readme,
    read_readme,
)
from bench.wl_cloud.cloud_tf import (
    CLOUD_MAPPING,
    classify_nodes,
    parse_tf,
    read_match_field,
)


_PREFIX = 'bench/wl_cloud'
_README = os.path.join(_PREFIX, 'cloud-tf', 'README.txt')
_TF = os.path.join(_PREFIX, 'cloud-tf', 'network.tf')

_PORT_BASE = 331


def _fields(rule):
    """ Every header field a rule constrains, decoded. """
    out = {}
    for field in CLOUD_MAPPING:
        if field == 'length':
            continue
        value = read_match_field(rule.match, field)
        if value is not None:
            out[field] = value
    return out


def _minimal(**overrides):
    """ A tiny well-formed README, for the refusal tests.

    Two services and a 3x3 matrix: the smallest shape that still has one
    undeclared index, which is the property `_validate` reasons about.
    """
    text = {
        'preamble': (
            'Datacenter tree height: 1\n'
            'Public services IP: 121.140.254.0\n'
            'Public TCP port: 331\n'
            'Number of hosts per leaf router: 30\n'
            'Number of leaf routers: 8\n'
            'Number of bits of leaf IPs: 7\n'
            'Number of bits per datacenter: 10\n'
            'Router branching: 8\n'
        ),
        'dc': 'Services per Datacenter:\nDatacenter 0: #2 [0, 1]\n',
        'ips': (
            "Services' IPs:\n"
            'Service 0: #1 10.0.0.0/25\n'
            'Service 1: #1 10.0.1.0/25\n'
        ),
        'matrix': 'ACL Matrix:\n0: 001\n1: 001\n2: 110\n',
        'blocks': (
            'Datacenter 0: 10.0.0.0 (port 1000000)\n'
            'Services of router 1000001: set([0, 1])\n'
            'Internet port: 1500000\n'
        ),
    }
    text.update(overrides)
    return ''.join(text[k] for k in ('preamble', 'dc', 'ips', 'matrix', 'blocks'))


@unittest.skipUnless(os.path.isfile(_README), "wl_cloud raw scenario not present")
class TestCloudReadme(unittest.TestCase):
    """ What the README states, and what it therefore means. """

    @classmethod
    def setUpClass(cls):
        cls.readme = read_readme(_README)
        with open(_TF, 'r') as raw:
            cls.rules = parse_tf(raw)
        cls.model = classify_nodes(cls.rules)

    # -- what the file states ------------------------------------------------

    def test_the_readme_parses_whole(self):
        self.assertEqual(len(self.readme.services), 25)
        self.assertEqual(len(self.readme.matrix), 26)
        self.assertEqual({len(row) for row in self.readme.matrix}, {26})
        self.assertEqual(len(self.readme.router_services), 40)
        self.assertEqual(len(self.readme.datacenter_block), 5)
        self.assertEqual(self.readme.internet_port, 1500000)
        self.assertEqual(self.readme.scalars['public_ip'], '121.140.254.0')
        self.assertEqual(self.readme.service_port_base, _PORT_BASE)

    def test_the_matrix_is_symmetric_with_an_empty_diagonal(self):
        """ Both halves say the same thing, and nothing reaches itself.

        The symmetry is why a 1-cell becomes TWO `--->` rules rather than one
        bidirectional one, and the empty diagonal is why the policy states no
        self-rule at all.
        """
        matrix = self.readme.matrix
        for i in self.readme.roles:
            self.assertEqual(matrix[i][i], 0, "role %d reaches itself" % i)
            for j in self.readme.roles:
                self.assertEqual(
                    matrix[i][j], matrix[j][i],
                    "matrix is asymmetric at (%d, %d)" % (i, j))

    def test_there_are_226_authorised_ordered_pairs(self):
        self.assertEqual(len(self.readme.authorised_pairs()), 226)

    # -- the algebra, against the transfer function --------------------------

    def test_service_ports_are_the_port_base_plus_the_index(self):
        """ The 25 declared services are exactly the 25 ports the rules use. """
        used = {
            fields['packet.upper.dport'] for rule in self.rules
            for fields in [_fields(rule)] if 'packet.upper.dport' in fields
        }
        self.assertEqual(
            used, {self.readme.service_port(i) for i in self.readme.services})
        self.assertEqual(used, set(range(_PORT_BASE, _PORT_BASE + 25)))

    def test_gateway_nat_maps_the_public_address_of_each_service(self):
        """ `121.140.254.i : 331+i` -> a datacenter the README says hosts i.

        This is the measurement that ties the port offset and the address
        offset to the SAME index. A reading that got either wrong would still
        produce plausible NAT and would go wrong only here.
        """
        core_to_dc = {
            core: dc for dc, (_addr, core)
            in self.readme.datacenter_block.items()
        }

        seen = collections.defaultdict(set)
        for rule in self.model.rules_at(self.readme.internet_port):
            if rule.action != 'rw':
                continue
            fields = _fields(rule)
            index = fields['packet.upper.dport'] - _PORT_BASE
            self.assertEqual(
                fields['packet.ipv4.destination'],
                '%s/32' % self.readme.service_address(index),
                "gateway rule for port %d does not carry service %d's public "
                "address" % (fields['packet.upper.dport'], index))
            seen[index].add(core_to_dc[rule.out_ports[0]])

        for index, datacenters in seen.items():
            for datacenter in datacenters:
                self.assertIn(
                    index, self.readme.datacenter_services[datacenter],
                    "the gateway sends service %d to datacenter %d, which the "
                    "README does not list it in" % (index, datacenter))

    # -- index 25 is the Internet: FOUR sets, one identity -------------------

    def _source_less_services(self):
        """ Services whose ACL rule carries no source constraint. """
        return {
            fields['packet.upper.dport'] - _PORT_BASE
            for rule in self.rules for fields in [_fields(rule)]
            if 'packet.upper.dport' in fields
            and 'packet.ipv4.source' not in fields
        }

    def _gateway_nat_services(self):
        return {
            _fields(rule)['packet.upper.dport'] - _PORT_BASE
            for rule in self.model.rules_at(self.readme.internet_port)
            if rule.action == 'rw'
        }

    def _egress_nat_services(self):
        """ Services the cores source-NAT out to the internet egress. """
        egress = {
            sink for sink in self.model.sinks
            if sink > self.readme.internet_port
        }
        return {
            _fields(rule)['packet.upper.sport'] - _PORT_BASE
            for rule in self.rules
            if rule.action == 'rw' and set(rule.out_ports) & egress
        }

    def test_the_undeclared_matrix_index_is_the_internet(self):
        """ §1.9.5, answered from the data rather than assumed.

        Matrix row 25 == the source-less ACL services == the gateway's inbound
        NAT == the cores' outbound NAT. Four derivations, four halves of the
        dataset, one set.
        """
        row = {j for j in self.readme.roles if self.readme.permits(INTERNET_INDEX, j)}

        self.assertEqual(row, {0, 1, 8, 10, 11, 13, 14, 18, 19, 22, 23})
        self.assertEqual(row, self._source_less_services(),
                         "matrix row 25 is not the set reachable from anywhere")
        self.assertEqual(row, self._gateway_nat_services(),
                         "matrix row 25 is not the set the gateway publishes")
        self.assertEqual(row, self._egress_nat_services(),
                         "matrix row 25 is not the set the cores NAT outbound")

    def test_every_service_is_public_or_source_constrained_never_both(self):
        """ The 25 services partition. A service is published to the world OR
        it is reachable only from the matrix rows that name it. """
        public = self._source_less_services()
        private = {
            fields['packet.upper.dport'] - _PORT_BASE
            for rule in self.rules for fields in [_fields(rule)]
            if 'packet.upper.dport' in fields and 'packet.ipv4.source' in fields
        }

        self.assertEqual(public & private, set())
        self.assertEqual(public | private, set(self.readme.services))
        self.assertEqual(len(public), 11)
        self.assertEqual(len(private), 14)

    # -- the matrix IS the data plane, for the private half ------------------

    def test_the_private_half_of_the_matrix_is_realised_exactly(self):
        """ Set equality, both directions, over the source-constrained rules.

        A rule's source prefix is EXACTLY one of its source service's declared
        prefixes; its destination prefix is CONTAINED in one of the target
        service's, because a rule is written per leaf router and a leaf owns a
        /25 of the service.
        """
        realised = set()
        for rule in self.rules:
            fields = _fields(rule)
            if 'packet.ipv4.source' not in fields \
                    or 'packet.upper.dport' not in fields:
                continue

            source = fields['packet.upper.sport'] - _PORT_BASE
            target = fields['packet.upper.dport'] - _PORT_BASE
            realised.add((source, target))

            self.assertIn(
                fields['packet.ipv4.source'], self.readme.services[source],
                "a rule with sport %d does not carry service %d's own prefix"
                % (fields['packet.upper.sport'], source))
            self.assertTrue(
                any(
                    ipaddress.ip_network(
                        fields['packet.ipv4.destination']
                    ).subnet_of(ipaddress.ip_network(prefix))
                    for prefix in self.readme.services[target]
                ),
                "a rule with dport %d targets %s, outside service %d"
                % (fields['packet.upper.dport'],
                   fields['packet.ipv4.destination'], target))

        private = {target for _s, target in realised}
        expected = {
            (i, j) for (i, j) in self.readme.authorised_pairs()
            if j in private and i != INTERNET_INDEX
        }

        self.assertEqual(len(realised), 113)
        self.assertEqual(
            realised, expected,
            "the matrix's private half and the ACL rules are not the same set")

    def test_the_public_half_of_the_matrix_is_not_enforced(self):
        """ THE FINDING the `matrix`/`public` policy pair measures.

        A public service takes an ACL rule with no source match, so every role
        reaches it -- while the matrix authorises only some. This pins the size
        of the gap, so that a run reporting a different number is a change in
        the model rather than a change in the reading.
        """
        public = self._source_less_services()
        authorised = sum(
            1 for j in public for i in self.readme.roles
            if self.readme.permits(i, j))
        unauthorised = sum(
            1 for j in public for i in self.readme.roles
            if not self.readme.permits(i, j))

        self.assertEqual(authorised, 102)
        self.assertEqual(unauthorised, 184)
        self.assertEqual(authorised + unauthorised, len(public) * 26)

    # -- refusals ------------------------------------------------------------

    def test_an_unknown_preamble_line_is_refused(self):
        with self.assertRaises(ReadmeParseError):
            parse_readme(_minimal(
                preamble='Datacenter tree height: 1\nCosmic ray shielding: 3\n'))

    def test_a_non_square_matrix_is_refused(self):
        with self.assertRaises(ReadmeParseError):
            parse_readme(_minimal(matrix='ACL Matrix:\n0: 001\n1: 0011\n2: 110\n'))

    def test_a_matrix_that_is_not_services_plus_one_is_refused(self):
        """ The whole Internet reading rests on there being exactly one
        undeclared index; two would make it a guess. """
        with self.assertRaises(ReadmeParseError):
            parse_readme(_minimal(
                matrix='ACL Matrix:\n0: 0010\n1: 0010\n2: 1100\n3: 0000\n'))

    def test_a_service_whose_count_disagrees_with_its_list_is_refused(self):
        with self.assertRaises(ReadmeParseError):
            parse_readme(_minimal(ips=(
                "Services' IPs:\n"
                'Service 0: #2 10.0.0.0/25\n'
                'Service 1: #1 10.0.1.0/25\n')))

    def test_a_service_address_that_is_not_a_prefix_is_refused(self):
        with self.assertRaises(ReadmeParseError):
            parse_readme(_minimal(ips=(
                "Services' IPs:\n"
                'Service 0: #1 10.0.0.0\n'
                'Service 1: #1 10.0.1.0/25\n')))

    def test_the_minimal_readme_is_otherwise_accepted(self):
        """ Without this the refusal tests above could all be passing for the
        wrong reason. """
        readme = parse_readme(_minimal())
        self.assertIsInstance(readme, CloudReadme)
        self.assertEqual(len(readme.services), 2)
        self.assertEqual(readme.service_port(1), 332)
        self.assertEqual(readme.service_address(1), '121.140.254.1')


if __name__ == '__main__':
    unittest.main()
