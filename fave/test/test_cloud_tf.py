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

""" The cloud (NoD) transfer-function reader: parsing, the header layout, and
the node taxonomy the whole workload model is derived from.

WHY THE LAYOUT IS PINNED BY A TEST. `cloud-tf/network.tf` is Hassel transfer
function syntax, the same shape `wl_stanford` uses, but the 128-bit match string
orders its fields DIFFERENTLY and nothing in the file declares that. Worse, the
two layouts agree on where `packet.ipv4.destination` sits (bit 48), so a reader
that got the layout wrong would still produce plausible forwarding and would go
wrong only on the ACL (proto/dport) and NAT fields -- silently, and in the exact
manner of AD6_PLAN.md §9.29's `length`/`mapping` defect. CLOUD_BENCH_PLAN.md
§1.1 records how the layout was measured; this pins it.

WHY THE CENSUS IS PINNED BY A TEST. The dataset has no `link$` lines: ports are
NODES and the topology is implicit in shared node ids, so the device model is
DERIVED (CLOUD_BENCH_PLAN.md §1.2) rather than read. The derivation reproduces
the generator parameters in `cloud-tf/README.txt` exactly -- 5 datacenters, 8
leaf routers each, 30 hosts per leaf -- and that agreement is the evidence the
derivation is right. A change that breaks it must fail loudly.
"""

import os
import unittest

from bench.wl_cloud.cloud_tf import (
    CLOUD_MAPPING,
    NodeRole,
    classify_nodes,
    node_name,
    parse_tf,
    read_match_field,
)


_PREFIX = 'bench/wl_cloud'
_TF = os.path.join(_PREFIX, 'cloud-tf', 'network.tf')

# One real line of `network.tf` (rule `_1`, the first ACL rule of datacenter 0's
# first leaf router), kept verbatim so the layout assertions below are made
# against the dataset itself and not against a fixture someone can adjust.
_REAL_ACL_RULE = (
    'fwd$[1000001]$'
    'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
    '0000101000000000000000000xxxxxxx'
    '00000110'
    'xxxxxxxxxxxxxxxx'
    '0000000101011110'
    'xxxxxxxx'
    '$None$None$None$None$[1000002]$#$#62#64#$$$_1$'
)


def _tf_available():
    return os.path.isfile(_TF)


class TestParsing(unittest.TestCase):
    """ The `$`-separated transfer-function syntax. """

    def test_a_forwarding_rule_parses_into_its_fields(self):
        rule, = parse_tf([_REAL_ACL_RULE])

        self.assertEqual(rule.action, 'fwd')
        self.assertEqual(rule.in_ports, [1000001])
        self.assertEqual(rule.out_ports, [1000002])
        self.assertEqual(rule.name, '_1')
        self.assertEqual(len(rule.match), 128)
        self.assertIsNone(rule.mask)
        self.assertIsNone(rule.rewrite)

    def test_a_rule_with_no_out_port_is_a_drop(self):
        line = 'fwd$[1000001]$%s$None$None$None$None$$#$#$$$_63$' % ('x' * 128)
        rule, = parse_tf([line])

        self.assertEqual(rule.out_ports, [])
        self.assertTrue(rule.is_drop)

    def test_a_rewrite_rule_carries_its_mask_and_rewrite(self):
        line = 'rw$[1500000]$%s$%s$%s$None$None$[1000000]$#$#$$$_2914$' % (
            'x' * 128, '1' * 48 + '0' * 32 + '1' * 48, '0' * 128)
        rule, = parse_tf([line])

        self.assertEqual(rule.action, 'rw')
        self.assertEqual(len(rule.mask), 128)
        self.assertEqual(len(rule.rewrite), 128)
        self.assertFalse(rule.is_drop)

    def test_the_header_and_comment_lines_are_not_rules(self):
        self.assertEqual(parse_tf(['32$$2941$0$0$', '#', _REAL_ACL_RULE]), parse_tf([_REAL_ACL_RULE]))


class TestHeaderLayout(unittest.TestCase):
    """ CLOUD_BENCH_PLAN.md §1.1 -- the measured field layout, pinned.

    The values below are read off ONE real rule whose meaning is known
    independently from `cloud-tf/README.txt`: datacenter 0 is `10.0.0.0`, its
    first leaf router serves `10.0.0.0/25`, and the generator only ever emits
    TCP. A layout error moves at least one of them.
    """

    def test_the_mapping_covers_the_whole_128_bit_header_without_gaps(self):
        spans = sorted(
            (off, off + size) for off, size in (
                (CLOUD_MAPPING[f], s) for f, s in _FIELD_SIZES.items()
            )
        )
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], 128)
        self.assertEqual(CLOUD_MAPPING['length'], 128)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertEqual(end, start, "gap or overlap at bit %d" % end)

    def test_the_destination_prefix_decodes_to_the_leaf_subnet(self):
        rule, = parse_tf([_REAL_ACL_RULE])
        self.assertEqual(
            read_match_field(rule.match, 'packet.ipv4.destination'), '10.0.0.0/25')

    def test_the_protocol_byte_decodes_to_tcp(self):
        rule, = parse_tf([_REAL_ACL_RULE])
        self.assertEqual(read_match_field(rule.match, 'packet.ipv6.proto'), 6)

    def test_the_destination_port_decodes_to_the_service_port(self):
        rule, = parse_tf([_REAL_ACL_RULE])
        self.assertEqual(read_match_field(rule.match, 'packet.upper.dport'), 350)

    def test_the_unconstrained_fields_read_as_absent(self):
        rule, = parse_tf([_REAL_ACL_RULE])
        for field in ('packet.ipv4.source', 'packet.ether.vlan',
                      'packet.upper.sport', 'packet.upper.tcp.flags'):
            self.assertIsNone(read_match_field(rule.match, field), field)

    def test_the_stanford_layout_would_decode_this_rule_differently(self):
        """ The guard that makes the two preceding tests meaningful.

        Under `wl_stanford`'s layout the protocol byte sits at bit 40, not 80.
        If both layouts agreed on every field the pinning above would be
        vacuous; this asserts they do not.
        """
        rule, = parse_tf([_REAL_ACL_RULE])
        stanford_proto = rule.match[40:48]
        cloud_proto = rule.match[CLOUD_MAPPING['packet.ipv6.proto']:][:8]
        self.assertNotEqual(stanford_proto, cloud_proto)


def _src_rule(in_port, out_port, cidr):
    """ A host-transmit line: one `fwd` constrained to the host's own prefix. """
    net, plen = cidr.split('/')
    octets = [int(o) for o in net.split('.')]
    bits = ''.join('{:08b}'.format(o) for o in octets)
    bits = bits[:int(plen)] + 'x' * (32 - int(plen))
    match = 'x' * 16 + bits + 'x' * 80
    return 'fwd$[%d]$%s$None$None$None$None$[%d]$#$#$$$_s$' % (
        in_port, match, out_port)


_FIELD_SIZES = {
    'packet.ether.vlan': 16,
    'packet.ipv4.source': 32,
    'packet.ipv4.destination': 32,
    'packet.ipv6.proto': 8,
    'packet.upper.sport': 16,
    'packet.upper.dport': 16,
    'packet.upper.tcp.flags': 8,
}


class TestNodeTaxonomy(unittest.TestCase):
    """ CLOUD_BENCH_PLAN.md §1.2 -- the derived device model. """

    def test_a_node_whose_only_rule_injects_under_a_source_constraint_is_a_source(self):
        """ The host-transmit idiom: one rule, handing traffic to the router
        under the host's own `src` prefix. That rule is a generator header, not
        a table. """
        rules = parse_tf([
            _src_rule(10, 20, '10.0.0.0/30'),
            'fwd$[20]$%s$None$None$None$None$[30]$#$#$$$_b$' % ('x' * 128),
        ])
        model = classify_nodes(rules)

        self.assertEqual(model.role(10), NodeRole.SOURCE)
        self.assertEqual(model.role(20), NodeRole.DEVICE)
        self.assertEqual(model.role(30), NodeRole.SINK)

    def test_being_in_only_is_not_enough_to_be_a_source(self):
        """ The internet gateway is the reason this distinction exists: node
        `1500000` never appears as anyone's out-port, yet it carries the
        dataset's 19 inbound DNAT rules and is plainly a table. Classifying by
        "appears only as an in-port" would file it as a bare traffic source and
        silently drop every NAT rule it holds. """
        rules = parse_tf([
            'rw$[10]$%s$%s$%s$None$None$[20]$#$#$$$_a$' % (
                'x' * 128, '1' * 48 + '0' * 32 + '1' * 48, '0' * 128),
            'fwd$[20]$%s$None$None$None$None$[30]$#$#$$$_b$' % ('x' * 128),
        ])
        model = classify_nodes(rules)

        self.assertEqual(model.role(10), NodeRole.DEVICE)

    def test_an_unconstrained_single_hand_off_is_a_device(self):
        """ Deliberate: only a SOURCE-CONSTRAINED hand-off is generator-shaped.
        An unconstrained one carries no header to give a generator, so treating
        it as a source would invent an unconstrained injection point. """
        rules = parse_tf([
            'fwd$[10]$%s$None$None$None$None$[20]$#$#$$$_a$' % ('x' * 128),
            'fwd$[20]$%s$None$None$None$None$[30]$#$#$$$_b$' % ('x' * 128),
        ])
        model = classify_nodes(rules)

        self.assertEqual(model.role(10), NodeRole.DEVICE)

    def test_a_drop_rule_still_makes_its_node_a_device(self):
        """ A node whose only rule drops never appears as an out-port, but it is
        plainly a forwarding element and not a traffic source. """
        rules = parse_tf([
            'fwd$[10]$%s$None$None$None$None$[20]$#$#$$$_a$' % ('x' * 128),
            'fwd$[20]$%s$None$None$None$None$$#$#$$$_b$' % ('x' * 128),
        ])
        model = classify_nodes(rules)

        self.assertEqual(model.role(20), NodeRole.DEVICE)


class TestNodeNaming(unittest.TestCase):
    """ Node id -> a name a report can be read with. """

    def test_a_datacenter_core(self):
        self.assertEqual(node_name(1000000), 'dc0_core')
        self.assertEqual(node_name(1400000), 'dc4_core')

    def test_a_leaf_router_has_an_ingress_and_an_egress_node(self):
        self.assertEqual(node_name(1000001), 'dc0_leaf0_in')
        self.assertEqual(node_name(1000002), 'dc0_leaf0_out')
        self.assertEqual(node_name(1000063), 'dc0_leaf1_in')
        self.assertEqual(node_name(1000064), 'dc0_leaf1_out')

    def test_a_host_owns_a_receive_and_a_transmit_node(self):
        self.assertEqual(node_name(1000003), 'dc0_leaf0_host0_rx')
        self.assertEqual(node_name(1000004), 'dc0_leaf0_host0_tx')
        self.assertEqual(node_name(1000061), 'dc0_leaf0_host29_rx')
        self.assertEqual(node_name(1000062), 'dc0_leaf0_host29_tx')

    def test_the_internet_endpoints(self):
        self.assertEqual(node_name(1500000), 'internet_gw')
        self.assertEqual(node_name(1500001), 'internet_rx')


@unittest.skipUnless(_tf_available(), "%s not present" % _TF)
class TestTheRealDataset(unittest.TestCase):
    """ The census. These numbers are the evidence that the derivation of §1.2
    is right: they reproduce `cloud-tf/README.txt`'s generator parameters
    exactly, and nothing in the `.tf` file states them. """

    @classmethod
    def setUpClass(cls):
        cls.rules = parse_tf(open(_TF, 'r'))
        cls.model = classify_nodes(cls.rules)

    def test_the_rule_count_matches_the_file_header(self):
        header = open(_TF, 'r').readline().strip()
        self.assertEqual(header.split('$')[2], '2941')
        self.assertEqual(len(self.rules), 2941)

    def test_the_action_census(self):
        actions = [r.action for r in self.rules]
        self.assertEqual(actions.count('fwd'), 2913)
        self.assertEqual(actions.count('rw'), 28)

    def test_the_node_census(self):
        """ 86 = the 85 nodes that appear on both sides of a rule, plus the
        internet gateway, which is in-only but carries the inbound NAT rules
        (see TestNodeTaxonomy). The 1,200 sources are the host transmit nodes;
        the 1,201 sinks are the host receive nodes plus the internet egress. """
        self.assertEqual(len(self.model.devices), 86)
        self.assertEqual(len(self.model.sources), 1200)
        self.assertEqual(len(self.model.sinks), 1201)

    def test_the_topology_matches_the_readme_generator_parameters(self):
        """ 5 datacenters x (1 core + 8 leaf routers x 2 nodes), 30 hosts each. """
        cores = [
            n for n in self.model.devices
            if n % 100000 == 0 and n < 1500000
        ]
        self.assertEqual(len(cores), 5)

        leaves = [n for n in self.model.devices if n % 100000 != 0 and n < 1500000]
        self.assertEqual(len(leaves), 80)
        self.assertEqual(len([n for n in leaves if n % 2 == 1]), 40)
        self.assertEqual(len([n for n in leaves if n % 2 == 0]), 40)

        hosts = [n for n in self.model.sources if n < 1500000]
        self.assertEqual(len(hosts), 1200)

    def test_the_internet_gateway_is_a_device_not_a_bare_source(self):
        """ `1500000` carries the inbound DNAT rules, so it is a table. """
        self.assertIn(1500000, self.model.devices)
        self.assertIn(1500001, self.model.sinks)

    def test_every_drop_rule_belongs_to_a_device(self):
        drops = [r for r in self.rules if r.is_drop]
        self.assertEqual(len(drops), 45)
        for rule in drops:
            self.assertIn(rule.in_ports[0], self.model.devices)

    def test_every_host_transmit_node_injects_under_a_source_constraint(self):
        """ The host transmit rules are what becomes a generator header, so each
        one must carry exactly the `src` prefix of its own /30 and nothing else. """
        for node in self.model.sources:
            if node >= 1500000:
                continue
            rules = self.model.rules_at(node)
            self.assertEqual(len(rules), 1, node_name(node))
            src = read_match_field(rules[0].match, 'packet.ipv4.source')
            self.assertIsNotNone(src, node_name(node))
            self.assertTrue(src.endswith('/30'), src)

    def test_the_rewrite_rules_all_rewrite_the_same_field(self):
        """ Destination NAT inbound, source NAT outbound -- both touch exactly
        one 32-bit field, and a rewrite that touched another would mean the
        layout of §1.1 is wrong. """
        for rule in [r for r in self.rules if r.action == 'rw']:
            ones = set(i for i, c in enumerate(rule.mask) if c == '0')
            self.assertTrue(
                ones in (set(range(16, 48)), set(range(48, 80))),
                "rw rule %s masks bits %s" % (rule.name, sorted(ones)[:4]))


if __name__ == '__main__':
    unittest.main()
