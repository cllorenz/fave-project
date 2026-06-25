#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" This modules provides tests for the flow checking tool.
"""

import unittest

from test.check_flows import check_flow, _parse_flow_spec
from test.check_flows import _get_parser as get_default_parser
from test.check_flows import _parse_one_flow_spec, _classify, FlowCheck

class TestChecker(unittest.TestCase):
    """ This class provides tests for the flow checking tool.
    """

    def setUp(self):
        """ Sets up a clean test environment.
        """

        mapping = {
            'related' : 0,
            'length' : 8
        }

        self.inv_fave = {
            "generator_to_id" : {"source1" : 1},
            "probe_to_id" : {"probe1" : 2, "probe2" : 3},
            "table_id_to_rules" : {
                1 : [4294967297, 4294967298],
                2 : [8589934593, 8589934594],
                3 : []
            },
            "table_to_id" : {"table1" : 1, "table2" : 2, "table3" : 3},
            "mapping" : mapping
        }

        self.flow_tree = {
            'node' : 1,
            'flow' : "xxxxxxxx",
            'children' : [
                {
                    'node' : 4294967297,
                    'flow' : "00000001",
                    'children' : [
                        {
                            'node' : 2,
                            'flow' : "00000001"
                        }
                    ]
                },
                {
                    'node' : 8589934594,
                    'flow' : "00000000"
                }
            ]
        }

        self.parser = get_default_parser()


    def tearDown(self):
        """ Destroys test environment.
        """

        del self.inv_fave
        del self.flow_tree


    def test_check_flow(self):
        """ Tests different path specifications against a flow tree.
        """

        checks = [
            ("s=source1 && EX t=table1", True),
            ("s=source1 && EX t=table3", False),
            ("! s=source1 && EX t=table3", True),
            ("s=source1 && EX t=table3", False),
            ("s=source1 && EF p=probe1", True),
            ("s=source1 && EF p=probe2", False),
            ("! s=source1 && EF p=probe2", True)
        ]

        for check, result in checks:
            flow_spec = _parse_flow_spec(check, self.parser)
            self.assertEqual(
                check_flow(flow_spec, self.flow_tree, self.inv_fave),
                result
            )


    def test_check_flow_fields(self):
        """ Tests path specifications including flow fields
        """

        checks = [
            ("s=source1 && EF p=probe1", True),
            ("s=source1 && EF p=probe2", False),
            ("! s=source1 && EF p=probe2", True),
            ("s=source1 && EF p=probe1 && f=related:1", True),
            ("s=source1 && EF p=probe1 && f=related:0", False),
            ("! s=source1 && EF p=probe1 && f=related:0", True),
            ("s=source1 && EX t=table2 && f=related:0", True),
            ("s=source1 && EX t=table2 && f=related:1", False),
            ("! s=source1 && EX t=table2 && f=related:1", True)
        ]

        for check, result in checks:
            flow_spec = _parse_flow_spec(check, self.parser)
            self.assertEqual(
                check_flow(flow_spec, self.flow_tree, self.inv_fave),
                result
            )


class TestFindingClassification(unittest.TestCase):
    """ Tests the assertion-vs-finding split: a '?'-marked check is an expected
    finding (reported, non-gating); everything else is an assertion (gates). """

    def setUp(self):
        self.parser = get_default_parser()

    def test_marker_tags_finding_and_parses_rest(self):
        plain = _parse_one_flow_spec("s=source1 && EF p=probe1", self.parser)
        finding = _parse_one_flow_spec("?! s=source1 && EF p=probe2", self.parser)
        self.assertFalse(plain.is_finding)
        self.assertTrue(finding.is_finding)
        # The '?' is stripped before parsing; the rest of the spec is intact.
        self.assertIn('!', list(finding))
        self.assertTrue(any(t.startswith('s=') for t in finding))

    def _classify_one(self, deviated, is_finding):
        failed, findings, unexpected = [], [], []
        _classify('lbl', deviated, is_finding, failed, findings, unexpected)
        return failed, findings, unexpected

    def test_assertion_deviation_fails(self):
        failed, findings, unexpected = self._classify_one(True, is_finding=False)
        self.assertEqual((failed, findings, unexpected), (['lbl'], [], []))

    def test_finding_deviation_is_reported_not_failed(self):
        failed, findings, unexpected = self._classify_one(True, is_finding=True)
        self.assertEqual((failed, findings, unexpected), ([], ['lbl'], []))

    def test_assertion_holding_is_silent(self):
        failed, findings, unexpected = self._classify_one(False, is_finding=False)
        self.assertEqual((failed, findings, unexpected), ([], [], []))

    def test_finding_no_longer_deviating_is_unexpected(self):
        failed, findings, unexpected = self._classify_one(False, is_finding=True)
        self.assertEqual((failed, findings, unexpected), ([], [], ['lbl']))


if __name__ == '__main__':
    unittest.main()
