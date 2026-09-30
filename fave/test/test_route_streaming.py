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

""" Streaming `routes.json` (CLOUD_BENCH_PLAN.md §2.15), and interning the
strings every rule repeats.

`iter_json_array` must be `json.load` element for element -- checked at chunk
sizes down to ONE character, so every element straddles a boundary somewhere
-- and `add_routes_streamed` must send exactly the commands `add_routes` sends,
or refuse. Pure Python: fast tier.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from rule.rule_model import Forward, Rule, RuleField
from util import bench_utils
from util.bench_utils import add_routes, add_routes_streamed, iter_json_array


_ROUTES = [
    ['sw.s1', 1, 1, ['ipv4_dst=10.0.0.0/8'], ['fd=sw.s1.52'], []],
    ['sw.s1', 1, 2, ['ipv4_dst=10.1.0.0/16'], ['fd=sw.s1.53'], ['sw.s1.2']],
    ['sw.s2', 2, 1, ['ipv4_dst=20.0.0.0/8'], ['fd=sw.s2.51'], []],
    ['sw.s3', 3, 1, ['ipv4_dst=30.0.0.0/8'], ['fd=sw.s3.52'], [],
     {'nested': [1, 2.5, None, True, "a,]b"]}],
]


class TestIterJsonArray(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='stream_test_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, text):
        path = os.path.join(self.tmp, 'r.json')
        with open(path, 'w') as handle:
            handle.write(text)
        return path

    def test_equals_json_load_at_every_chunk_size(self):
        for indent in (None, 2):
            path = self._file(json.dumps(_ROUTES, indent=indent) + '\n')
            for chunk in (1, 2, 3, 7, 64, 1 << 20):
                self.assertEqual(list(iter_json_array(path, chunk=chunk)),
                                 _ROUTES, (indent, chunk))

    def test_a_top_level_number_is_not_cut_short(self):
        path = self._file('[12345, 678]')
        self.assertEqual(list(iter_json_array(path, chunk=2)), [12345, 678])

    def test_empty_array(self):
        self.assertEqual(list(iter_json_array(self._file(' [ ] '), chunk=1)), [])

    def test_not_an_array_is_refused(self):
        self.assertRaises(ValueError, list, iter_json_array(self._file('{}')))

    def test_a_truncated_file_is_refused(self):
        path = self._file(json.dumps(_ROUTES)[:-5])
        self.assertRaises(ValueError, list, iter_json_array(path, chunk=4))

    def test_the_generated_workloads_if_present(self):
        for prefix in ('bench/wl_airtel1', 'bench/wl_berkeley'):
            path = os.path.join(prefix, 'routes.json')
            if not os.path.isfile(path) or os.path.getsize(path) > 50 << 20:
                continue
            with open(path) as handle:
                whole = json.load(handle)
            self.assertEqual(list(iter_json_array(path, chunk=4096)), whole,
                             path)


class TestAddRoutesStreamed(unittest.TestCase):

    def _sent(self, send, routes):
        with mock.patch.object(bench_utils, '_add_rules') as fake:
            send(routes)
        return [call.args[0] for call in fake.call_args_list]

    def test_sends_what_add_routes_sends(self):
        self.assertEqual(self._sent(add_routes_streamed, iter(_ROUTES)),
                         self._sent(add_routes, list(_ROUTES)))

    def test_ungrouped_routes_are_refused(self):
        routes = [_ROUTES[0], _ROUTES[2], _ROUTES[1]]
        with self.assertRaises(ValueError) as caught:
            self._sent(add_routes_streamed, iter(routes))
        self.assertIn('sw.s1', str(caught.exception))


class TestInterning(unittest.TestCase):
    """ Rules share one copy of each recurring string, and keep their lists. """

    def test_recurring_strings_are_shared(self):
        a = Rule(''.join(['sw.', 's1']), ''.join(['sw.s1', '.1']), 1,
                 in_ports=[''.join(['sw.s1.', '2'])],
                 actions=[Forward(ports=[''.join(['sw.s1.', '52'])])])
        b = Rule('sw.s1', 'sw.s1.1', 2, in_ports=['sw.s1.2'],
                 actions=[Forward(ports=['sw.s1.52'])])
        self.assertIs(a.node, b.node)
        self.assertIs(a.tid, b.tid)
        self.assertIs(a.in_ports[0], b.in_ports[0])
        self.assertIs(a.actions[0].ports[0], b.actions[0].ports[0])
        self.assertIs(RuleField(''.join(['ipv4', '_dst']), '10.0.0.0/8').name,
                      RuleField('ipv4_dst', '10.0.0.0/8').name)

    def test_a_caller_keeps_its_list(self):
        ports = ['sw.s1.2']
        self.assertIs(Rule('sw.s1', 1, 1, in_ports=ports).in_ports, ports)

    def test_non_strings_pass_through(self):
        self.assertEqual(Rule('sw.s1', 7, 1).tid, 7)


if __name__ == '__main__':
    unittest.main()
