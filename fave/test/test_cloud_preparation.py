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

""" The cloud workload's model builder (CLOUD_BENCH_PLAN.md §1.3).

The dataset states its forwarding as node-to-node rules with no interfaces and
no link lines, so this step invents the port structure FaVe needs: one in-port
per device and one out-port per (device, neighbour) pair, with a link joining
each out-port to the neighbour's in-port. Everything below pins that invention,
because nothing in the source data would catch it going wrong -- a mis-wired
port produces a model that builds cleanly and answers the wrong question.
"""

import os
import unittest

from bench.wl_cloud.cloud_preparation import build_model
from bench.wl_cloud.cloud_tf import classify_nodes, parse_tf


_PREFIX = 'bench/wl_cloud'
_TF = os.path.join(_PREFIX, 'cloud-tf', 'network.tf')

_ALL = 'x' * 128


def _match(**fields):
    """ A 128-bit match string in the cloud layout (CLOUD_BENCH_PLAN.md §1.1). """
    bits = ['x'] * 128
    if 'dst' in fields:
        net, plen = fields['dst'].split('/')
        raw = ''.join('{:08b}'.format(int(o)) for o in net.split('.'))
        bits[48:80] = list(raw[:int(plen)] + 'x' * (32 - int(plen)))
    if 'src' in fields:
        net, plen = fields['src'].split('/')
        raw = ''.join('{:08b}'.format(int(o)) for o in net.split('.'))
        bits[16:48] = list(raw[:int(plen)] + 'x' * (32 - int(plen)))
    if 'dport' in fields:
        bits[104:120] = list('{:016b}'.format(fields['dport']))
    return ''.join(bits)


def _fwd(in_port, out_port, match=_ALL, name='_r'):
    out = '[%d]' % out_port if out_port is not None else ''
    return 'fwd$[%d]$%s$None$None$None$None$%s$#$#$$$%s$' % (
        in_port, match, out, name)


def _rw(in_port, out_port, match, rewrite_dst, name='_rw'):
    mask = '1' * 48 + '0' * 32 + '1' * 48
    raw = ''.join('{:08b}'.format(int(o)) for o in rewrite_dst.split('.'))
    rewrite = '0' * 48 + raw + '0' * 48
    return 'rw$[%d]$%s$%s$%s$None$None$[%d]$#$#$$$%s$' % (
        in_port, match, mask, rewrite, out_port, name)


def _build(lines, **kwargs):
    rules = parse_tf(lines)
    return build_model(rules, classify_nodes(rules), **kwargs)


# A minimum viable network in the dataset's own idiom: one host transmitting
# into a leaf ingress, which routes to a leaf egress, which delivers to the
# host's receive node.
_TINY = [
    _fwd(1000004, 1000001, _match(src='10.0.0.0/30'), '_tx'),
    _fwd(1000001, 1000002, _match(dst='10.0.0.0/25', dport=350), '_acl'),
    _fwd(1000001, None, _match(dst='10.0.0.0/25'), '_drop'),
    _fwd(1000002, 1000003, _match(dst='10.0.0.0/30'), '_deliver'),
]


class TestPortStructure(unittest.TestCase):
    """ The invented port structure of §1.3. """

    def setUp(self):
        self.model = _build(_TINY)
        self.devices = dict((d[0], d) for d in self.model['topology']['devices'])

    def test_every_device_is_declared_with_its_ports(self):
        self.assertEqual(
            sorted(self.devices), ['lin.dc0_leaf0', 'lout.dc0_leaf0'])
        for _name, kind, ports, _tid in self.devices.values():
            self.assertEqual(kind, 'switch')
            self.assertTrue(ports)

    def test_a_device_has_exactly_one_in_port(self):
        """ The dataset keys rules by NODE, not by arriving interface, so every
        rule of a device shares one in-port and nothing is lost by it. """
        for route in self.model['routes']:
            self.assertEqual(len(route[5]), 1)
        in_ports = set(r[5][0] for r in self.model['routes'] if r[0] == 'lin.dc0_leaf0')
        self.assertEqual(len(in_ports), 1)

    def test_a_device_has_one_out_port_per_distinct_neighbour(self):
        """ `lin.dc0_leaf0` forwards only to `lout.dc0_leaf0` (its drop rule has
        no out-port at all), so it needs exactly one out-port. """
        _name, _kind, ports, _tid = self.devices['lin.dc0_leaf0']
        self.assertEqual(len(ports), 2, "one in-port + one out-port: %s" % ports)

    def test_each_out_port_is_linked_to_its_neighbours_in_port(self):
        links = self.model['topology']['links']
        self.assertEqual(len(links), 1)
        src, dst, internal = links[0]
        self.assertTrue(src.startswith('lin.dc0_leaf0.'))
        self.assertTrue(dst.startswith('lout.dc0_leaf0.'))
        self.assertFalse(internal)

        forwards = [
            a for r in self.model['routes'] if r[0] == 'lin.dc0_leaf0'
            for a in r[4] if a.startswith('fd=')
        ]
        self.assertEqual(forwards, ['fd=%s' % src])


class TestRules(unittest.TestCase):
    """ Rule translation: matches, drops, rewrites, and order. """

    def setUp(self):
        self.model = _build(_TINY)
        self.routes = self.model['routes']

    def test_a_match_is_translated_field_by_field(self):
        acl = [r for r in self.routes if r[0] == 'lin.dc0_leaf0'][0]
        self.assertIn('ipv4_dst=10.0.0.0/25', acl[3])
        self.assertIn('tcp_dst=350', acl[3])

    def test_a_drop_rule_keeps_its_match_and_forwards_nowhere(self):
        drops = [r for r in self.routes if not any(a.startswith('fd=') for a in r[4])]
        self.assertEqual(len(drops), 1)
        self.assertIn('ipv4_dst=10.0.0.0/25', drops[0][3])
        self.assertEqual(drops[0][4], [])

    def test_the_host_transmit_rule_does_not_become_a_route(self):
        """ It is a generator header instead -- see TestSourcesAndProbes. """
        self.assertEqual(sorted(set(r[0] for r in self.routes)),
                         ['lin.dc0_leaf0', 'lout.dc0_leaf0'])

    def test_a_rewrite_rule_emits_its_rewrite_before_its_forward(self):
        lines = [
            _rw(1500000, 1000000, _match(dst='121.140.254.11/32'), '10.0.0.5'),
            _fwd(1000000, 1000001, _match(dst='10.0.0.0/25')),
            _fwd(1000001, 1000002, _ALL),
        ]
        routes = _build(lines)['routes']
        gateway = [r for r in routes if r[0] == 'gw.internet']

        self.assertEqual(len(gateway), 1)
        actions = gateway[0][4]
        self.assertTrue(actions[0].startswith('rw='), actions)
        self.assertIn('ipv4_dst:10.0.0.5/32', actions[0])
        self.assertTrue(actions[1].startswith('fd='), actions)

    def test_a_rewrite_to_a_subnet_keeps_its_prefix_length(self):
        """ The dataset's DNAT maps a public address onto a /24 SERVICE SUBNET,
        leaving the host bits free. Dropping the `/24` pins every inbound flow
        to a single host and makes every internet-sourced query unreachable --
        see CLOUD_BENCH_PLAN.md §1.6. """
        mask = '1' * 48 + '0' * 32 + '1' * 48
        rewrite = '0' * 48 + '00001010000000000000000000000000'[:24] + 'x' * 8 + '0' * 48
        lines = [
            'rw$[1500000]$%s$%s$%s$None$None$[1000000]$#$#$$$_rw$' % (
                _match(dst='121.140.254.11/32'), mask, rewrite),
            _fwd(1000000, 1000001, _match(dst='10.0.0.0/25')),
            _fwd(1000001, 1000002, _ALL),
        ]
        gateway = [r for r in _build(lines)['routes'] if r[0] == 'gw.internet']

        self.assertIn('rw=ipv4_dst:10.0.0.0/24', gateway[0][4])


class TestSourcesAndProbes(unittest.TestCase):
    """ Host transmit nodes become generators; receive nodes become probes. """

    def setUp(self):
        self.model = _build(_TINY)

    def test_a_host_transmit_node_becomes_a_generator_with_its_own_prefix(self):
        devices = self.model['sources']['devices']
        self.assertEqual(len(devices), 1)
        name, kind, fields = devices[0]
        self.assertEqual(name, 'source.dc0_leaf0_host0_tx')
        self.assertEqual(kind, 'generator')
        self.assertIn('ipv4_src=10.0.0.0/30', fields)

    def test_a_generator_is_linked_into_its_routers_in_port(self):
        (src, dst, internal), = self.model['sources']['links']
        self.assertEqual(src, 'source.dc0_leaf0_host0_tx.1')
        self.assertTrue(dst.startswith('lin.dc0_leaf0.'))
        self.assertTrue(internal)

    def test_a_host_receive_node_becomes_a_probe(self):
        devices = self.model['probes']['devices']
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][0], 'probe.dc0_leaf0_host0_rx')
        self.assertEqual(devices[0][1], 'probe')
        self.assertEqual(devices[0][2], 'existential')

    def test_a_probe_is_linked_from_the_out_port_that_targets_it(self):
        (src, dst, internal), = self.model['probes']['links']
        self.assertTrue(src.startswith('lout.dc0_leaf0.'))
        self.assertEqual(dst, 'probe.dc0_leaf0_host0_rx.1')
        self.assertFalse(internal)

    def test_only_the_selected_endpoints_are_instantiated(self):
        """ The oracle phase needs 3 sources and 5 probes out of 2,401, and a
        generator that nothing asks about still costs a full flow propagation. """
        model = _build(_TINY, endpoints=[1000004])

        self.assertEqual(len(model['sources']['devices']), 1)
        self.assertEqual(model['probes']['devices'], [])


class TestTheDatasetOrderIsPreserved(unittest.TestCase):
    """ wl_cloud is FIRST-MATCH, so its file order IS its semantics.

    This class used to assert the opposite: that the generation-time repair
    reassigned indices so a longer prefix outranked a shorter one whatever the
    file order. That repair no longer runs here, and under the semantics the
    owner settled (TABLE_SEMANTICS_PLAN.md §0.6 / §2.8) it should never have:
    45 of this dataset's devices hold ONE table mixing forwarding and filtering,
    where two rules share a prefix and disagree, so only their ORDER can resolve
    them and reordering by prefix length would be the defect rather than the fix.

    Measured, so this is not a story: removing the repair leaves the generated
    routes BYTE-IDENTICAL (1,741 rules), because this dataset is already written
    longest-prefix-first wherever prefixes nest. The guard that matters is
    therefore that the emitted index follows the dataset, which is what a
    first-match table needs and what every backend now receives.
    """

    def test_the_emitted_index_follows_the_dataset_not_the_prefix_length(self):
        """ Priority is the route's rule INDEX (lower wins). Nothing reorders
        this workload, so the index must follow the order the dataset wrote. """
        lines = [
            _fwd(1000004, 1000001, _match(src='10.0.0.0/30'), '_tx'),
            # deliberately shortest-first, which is what the dataset does
            _fwd(1000001, 1000002, _ALL, '_default'),
            _fwd(1000001, 1000002, _match(dst='10.0.0.0/25'), '_leaf'),
            _fwd(1000002, 1000003, _match(dst='10.0.0.0/30'), '_host'),
        ]
        routes = _build(lines)['routes']
        ingress = [r for r in routes if r[0] == 'lin.dc0_leaf0']

        by_prefix = dict(
            (next((f for f in r[3] if f.startswith('ipv4_dst=')), 'default'), r[2])
            for r in ingress
        )
        # The dataset writes the default FIRST here, and that is the order the
        # model must carry -- the inverse of what the deleted repair produced.
        self.assertEqual(by_prefix['default'], 1)
        self.assertEqual(by_prefix['ipv4_dst=10.0.0.0/25'], 2)


@unittest.skipUnless(os.path.isfile(_TF), "%s not present" % _TF)
class TestTheRealDataset(unittest.TestCase):
    """ Whole-dataset invariants. """

    @classmethod
    def setUpClass(cls):
        rules = parse_tf(open(_TF, 'r'))
        cls.model = build_model(rules, classify_nodes(rules))

    def test_every_device_becomes_a_table(self):
        self.assertEqual(len(self.model['topology']['devices']), 86)

    def test_the_route_count_is_the_rule_count_less_the_generator_rules(self):
        """ 2,941 rules - 1,200 host transmit rules = 1,741. """
        self.assertEqual(len(self.model['routes']), 1741)

    def test_every_forward_action_names_a_port_of_its_own_device(self):
        ports = dict(
            (d[0], set(d[2])) for d in self.model['topology']['devices'])
        for table, _p, _rid, _match, actions, in_ports in self.model['routes']:
            for port in in_ports:
                self.assertIn(port.rsplit('.', 1)[1], ports[table], port)
            for action in actions:
                if action.startswith('fd='):
                    dev, port = action[3:].rsplit('.', 1)
                    self.assertEqual(dev, table, action)
                    self.assertIn(port, ports[table], action)

    def test_every_link_joins_two_declared_ports(self):
        declared = set(
            '%s.%s' % (d[0], p)
            for d in self.model['topology']['devices'] for p in d[2]
        )
        for src, dst, _internal in self.model['topology']['links']:
            self.assertIn(src, declared)
            self.assertIn(dst, declared)

    def test_every_sink_gets_a_probe_and_every_source_a_generator(self):
        self.assertEqual(len(self.model['sources']['devices']), 1200)
        self.assertEqual(len(self.model['probes']['devices']), 1201)


if __name__ == '__main__':
    unittest.main()
