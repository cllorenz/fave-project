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

""" bench/incremental_cell.py's RSS limit: declared, or the memory available
at a repetition's start less a margin (a cell run alone). Pure; no cell runs. """

import argparse
import os
import sys
import tempfile
import unittest

from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# pylint: disable=wrong-import-position
from bench import incremental_cell as cell


def _args(**kw):
    base = {'limit_rss': 32768, 'limit_rss_margin': None}
    base.update(kw)
    return argparse.Namespace(**base)


class TestRssLimit(unittest.TestCase):

    def test_a_declared_limit_is_kept(self):
        self.assertEqual(cell.rss_limit(_args()), (32768, {'declared_mb': 32768}))

    def test_a_margin_is_taken_from_what_is_available(self):
        """ The k = 1 trial: 59,831 MB available at its start, so with a 2 GB
        margin its limit is 57,783 MB, below what the kernel would allow
        (the RAM less 2 GB, 62,246 MB, was above it). """
        limit, basis = cell.rss_limit(_args(limit_rss=None, limit_rss_margin=2048),
                                      available_mb=59831)
        self.assertEqual(limit, 57783)
        self.assertEqual(basis, {'available_at_start_mb': 59831, 'margin_mb': 2048})

    def test_the_margin_reads_the_machine_by_default(self):
        with mock.patch.object(cell.cell_metrics, 'available_mb', return_value=10000):
            self.assertEqual(cell.rss_limit(_args(limit_rss=None, limit_rss_margin=1000))[0],
                             9000)

    def test_no_memory_left_is_refused(self):
        with self.assertRaises(SystemExit):
            cell.rss_limit(_args(limit_rss=None, limit_rss_margin=4096), available_mb=4000)


class TestArguments(unittest.TestCase):
    """ The parser's refusals, which come before any repetition starts. """

    def _main(self, *extra):
        out = tempfile.mkdtemp()
        with mock.patch.object(cell, 'run_repetition') as run, \
                mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                cell.main(['bench/wl_ifi', '--engine', 'apkeep', '--stream', 'z',
                           '--out', os.path.join(out, 'c')] + list(extra))
        run.assert_not_called()

    def test_a_limit_and_a_margin_exclude_each_other(self):
        self._main('--limit-rss', '32768', '--limit-rss-margin', '2048')

    def test_limit_class_v5_takes_no_margin(self):
        self._main('--limit-class', 'v5', '--limit-rss-margin', '2048')


if __name__ == '__main__':
    unittest.main()
