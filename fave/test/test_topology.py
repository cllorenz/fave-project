#!/usr/bin/env python2

import unittest

from topology.topology import LinksModel
from topology.topology import TopologyCommand

class TestLinksModel(unittest.TestCase):

    def setUp(self):
        self.model = LinksModel([['foo.1','bar.2'],['bar.1','foo.2']])

    def tearDown(self):
        del self.model

    def test_to_json(self):
        self.assertEqual(
            self.model.to_json(),
            {'type':'links','links':{'foo.1':'bar.2','bar.1':'foo.2'}}
        )

    def test_from_json(self):
        self.assertEqual(
            LinksModel.from_json(
                {'type':'links','links':{'foo.1':'bar.2','bar.1':'foo.2'}}
            ),
            self.model
        )

class TestTopologyCommand(unittest.TestCase):

    def setUp(self):
        self.model = LinksModel([['foo.1','bar.2'],['bar.1','foo.2']])
        self.cmd = TopologyCommand('links','add',model=self.model)

    def tearDown(self):
        del self.cmd
        del self.model

    def test_to_json(self):
        self.assertEqual(
            self.cmd.to_json(),
            {
                'node':'links',
                'type':'topology_command',
                'mtype' : 'links',
                'model':self.model.to_json(),
                'command':'add'
            }
        )

    def test_from_json(self):
        self.assertEqual(
            TopologyCommand.from_json(
                {
                    'node':'links',
                    'type':'topology_command',
                    'model':self.model.to_json(),
                    'command':'add'
                }
            ),
            self.cmd
        )

if __name__ == '__main__':
    unittest.main()
