#!/usr/bin/env python2

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


if __name__ == '__main__':
    unittest.main()
