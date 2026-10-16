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

""" util/fave_streams.py: S1-S3 as a FaVe user drives them (INCREMENTAL_PLAN.md
D14) -- the units, the streams, how a batch becomes messages, what is sent,
and the from-zero workload of the current state. A fake FaVe records the
messages; `test_incremental_fave_streams.py` runs them on the engines. """

import json
import os
import tempfile
import unittest

from util import fave_streams as fs
from util.barrier import BarrierError

_RULESET = '''ip6tables -P INPUT DROP
ip6tables -P FORWARD DROP
ip6tables -P OUTPUT DROP
ip6tables -A FORWARD -p tcp --dport 22 -j ACCEPT
ip6tables -A FORWARD -p tcp --dport 80 -j ACCEPT'''


class _FakeFave:
    def __init__(self):
        self.sent = []
        self.refuse = False
        self._agg = type('A', (), {'update_stats': {'t_diff_s': 0.1}})()

    def _send(self, what, arg):
        self.sent.append((what, arg))
        if self.refuse:
            raise BarrierError("FaVe failed to handle the request: UpdateRefused: no")

    def resend_device(self, device):
        with open(device[4]) as raw:
            self._send('resend', (device[0], raw.read()))

    def switch(self, argv):
        self._send('switch', argv)

    def topology(self, argv):
        self._send('topology', argv)


class TestFaveWorkload(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.prefix = os.path.join(self.tmp.name, 'wl')
        os.makedirs(d)
        with open(os.path.join(d, 'fw-ruleset'), 'w') as out:
            out.write(_RULESET)
        files = {
            'topology.json': {'devices': [['fw', 'packet_filter', 2, '2001:db8::1',
                                           os.path.join(d, 'fw-ruleset')],
                                          ['sw', 'switch', 2]],
                              'links': [['fw.2', 'sw.1', False]]},
            'routes.json': [['fw', 1, 0, ['ipv6_dst=2001:db8::/64'], ['fd=fw.2'], []],
                            ['sw', 1, 1, ['ipv6_dst=2001:db8::1'], ['fd=sw.2'], []],
                            ['sw', 1, 2, ['ipv6_dst=2001:db8::2'], ['fd=sw.2'], []]],
            'policies.json': {'devices': [], 'links': [['sw.2', 'probe.p.1', False]]},
            'sources.json': {'devices': [], 'links': [['source.s.1', 'fw.1', True]]},
            'checks.json': [],
        }
        for name, data in files.items():
            with open(os.path.join(d, name), 'w') as out:
                json.dump(data, out)
        self.work = os.path.join(self.tmp.name, 'work')
        os.makedirs(self.work)
        self.wl = fs.FaveWorkload(self.prefix, self.work)
        self.fave = _FakeFave()

    def test_rules_in_build_order_lines_then_routes(self):
        self.assertEqual(self.wl.rules(), [('line', 0, 3), ('line', 0, 4),
                                           ('route', 0), ('route', 1), ('route', 2)])
        self.assertEqual(self.wl.links(), [('link', 'topology', 0), ('link', 'policies', 0),
                                           ('link', 'sources', 0)])

    def test_the_streams(self):
        rules = self.wl.rules()
        s1 = fs.stream_s1(rules)
        self.assertEqual([u for _op, u in s1[:5]], list(reversed(rules)))
        self.assertEqual({op for op, _u in s1[:5]}, {'delete'})
        self.assertEqual(s1[5:], [('insert', u) for u in rules])
        s2 = fs.stream_s2(rules, 0.4, seed=1)
        self.assertEqual(len(s2), 4)
        self.assertEqual([u for _o, u in s2[:2]], [u for _o, u in s2[2:]])
        self.assertEqual(fs.stream_s2(rules, 0.4, seed=1), s2)
        s3 = fs.stream_s3(self.wl.links())
        self.assertEqual([op for op, _u in s3[:2]], ['link_down', 'link_up'])

    def test_a_batch_is_the_fewest_messages_that_keep_its_order(self):
        batch = [('delete', ('route', 1)), ('delete', ('route', 2)),   # sw, one command
                 ('delete', ('route', 0)),                             # fw
                 ('delete', ('line', 0, 3)), ('delete', ('line', 0, 4)),  # one re-send
                 ('insert', ('route', 1))]
        self.assertEqual(self.wl.messages(batch), [
            ('delete', [('route', 1), ('route', 2)]), ('delete', [('route', 0)]),
            ('delete', [('line', 0, 3), ('line', 0, 4)]), ('insert', [('route', 1)])])

    def test_a_line_is_deleted_and_inserted_by_re_sending_the_device(self):
        self.wl.send(self.fave, 'delete', [('line', 0, 3)])
        what, (node, text) = self.fave.sent[-1]
        self.assertEqual((what, node), ('resend', 'fw'))
        self.assertNotIn('--dport 22', text)
        self.assertIn('--dport 80', text)
        self.wl.send(self.fave, 'insert', [('line', 0, 3)])
        self.assertEqual(self.fave.sent[-1][1][1], _RULESET)

    def test_routes_and_links_go_as_commands(self):
        self.wl.send(self.fave, 'delete', [('route', 1), ('route', 2)])
        self.assertEqual(self.fave.sent[-1], ('switch', ['-d', '-r', 'sw$1$1#sw$1$2']))
        self.wl.send(self.fave, 'insert', [('route', 1)])
        self.assertEqual(self.fave.sent[-1],
                         ('switch', ['-a', '-r', 'sw$1$1$$ipv6_dst=2001:db8::1$fd=sw.2']))
        self.wl.send(self.fave, 'link_down', [('link', 'sources', 0)])
        self.assertEqual(self.fave.sent[-1], ('topology', ['-d', '-l', 'source.s.1:fw.1:True']))

    def test_a_refused_message_leaves_the_state(self):
        self.fave.refuse = True
        for op, unit in (('delete', ('line', 0, 3)), ('delete', ('route', 0)),
                         ('link_down', ('link', 'topology', 0))):
            with self.assertRaises(BarrierError):
                self.wl.send(self.fave, op, [unit])
        self.assertEqual((self.wl.absent, self.wl.down), (set(), set()))
        with open(self.wl.devices[0][4]) as raw:
            self.assertEqual(raw.read(), _RULESET)

    def test_the_zero_prefix_is_the_current_state(self):
        self.wl.send(self.fave, 'delete', [('line', 0, 4)])
        self.wl.send(self.fave, 'delete', [('route', 2)])
        self.wl.send(self.fave, 'link_down', [('link', 'policies', 0)])
        zero = self.wl.zero_prefix()
        with open(os.path.join(zero, 'routes.json')) as raw:
            self.assertEqual([r[2] for r in json.load(raw)], [0, 1])
        with open(os.path.join(zero, 'policies.json')) as raw:
            self.assertEqual(json.load(raw)['links'], [])
        with open(os.path.join(zero, 'topology.json')) as raw:
            topo = json.load(raw)
        self.assertEqual(topo['links'], [['fw.2', 'sw.1', False]])
        with open(topo['devices'][0][4]) as raw:
            self.assertNotIn('--dport 80', raw.read())
        self.assertTrue(os.path.islink(os.path.join(zero, 'checks.json')))

    def test_renamed_files_are_read_and_written_under_their_names(self):
        os.rename(os.path.join(self.prefix, 'topology.json'),
                  os.path.join(self.prefix, 'device_topology.json'))
        wl = fs.FaveWorkload(self.prefix, self.work, files={'topology': 'device_topology.json'})
        zero = wl.zero_prefix()
        self.assertTrue(os.path.exists(os.path.join(zero, 'device_topology.json')))
        self.assertFalse(os.path.exists(os.path.join(zero, 'topology.json')))
