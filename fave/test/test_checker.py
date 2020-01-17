#!/usr/bin/env python2

""" This modules provides tests for the flow checking tool.
"""

import unittest

from test.check_flows import check_flow, _parse_flow_spec

class TestChecker(unittest.TestCase):
    """ This class provides tests for the flow checking tool.
    """

    def setUp(self):
        """ Sets up a clean test environment.
        """
        pass


    def tearDown(self):
        """ Destroys test environment.
        """
        pass


    def test_check_flow(self):
        """ Tests different path specifications against a flow tree.
        """
        inv_fave = {
            "generator_to_id" : { "source1" : 1 },
            "probe_to_id" : { "probe1" : 2, "probe2" : 3 },
            "table_id_to_rules" : {
                1 : [4294967297, 4294967298],
                2 : [8589934593, 8589934594],
                3 : []
            },
            "table_to_id" : { "table1" : 1, "table2" : 2, "table3" : 3 }
        }

        flow_tree = {
            'node' : 1,
            'children' : [
                {
                    'node' : 4294967297,
                    'children' : [
                        {
                            'node' : 2
                        }
                    ]
                },
                {
                    'node' : 8589934594
                }
            ]
        }

        checks = [
            ("s=source1 && EX t=table1", True),
            ("! s=source1 && EX t=table3", True), # XXX: why not False?
            ("s=source1 && EX t=table3", False),
            ("s=source1 && EF p=probe1", True),
            ("! s=source1 && EF p=probe2", True) # XXX: why not False?
        ]

        for check, result in checks:
            print "try %s -> %s" % (check, result)
            flow_spec = _parse_flow_spec(check)
            print flow_spec
            self.assertEqual(check_flow(flow_spec, flow_tree, inv_fave), result)


if __name__ == '__main__':
    unittest.main()
