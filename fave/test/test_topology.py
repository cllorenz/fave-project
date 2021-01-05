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

""" This module provides tests for the links as well as the topology command models.
"""

import unittest

from topology.topology import LinksModel
from topology.topology import TopologyCommand


class TestLinksModel(unittest.TestCase):
    """ This class provides tests for the links model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """
        self.model = LinksModel([['foo.1', 'bar.2'], ['bar.1', 'foo.2']])


    def tearDown(self):
        """ Destroys the test environment.
        """
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a links model to JSON.
        """
        self.assertEqual(
            self.model.to_json(),
            {'type':'links', 'links':{'foo.1':['bar.2'], 'bar.1':['foo.2']}}
        )


    def test_from_json(self):
        """ Tests the creation of a links model from JSON.
        """
        self.assertEqual(
            LinksModel.from_json(
                {'type':'links', 'links':{'foo.1':['bar.2'], 'bar.1':['foo.2']}}
            ),
            self.model
        )


class TestTopologyCommand(unittest.TestCase):
    """ This class provides tests for the topology command model.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """

        self.model = LinksModel([['foo.1', 'bar.2'], ['bar.1', 'foo.2']])
        self.cmd = TopologyCommand('links', 'add', model=self.model)

    def tearDown(self):
        """ Destroys test environment.
        """

        del self.cmd
        del self.model


    def test_to_json(self):
        """ Tests the conversion of a topology command to JSON.
        """

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
        """ Tests the creation of a topology command from JSON.
        """

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
