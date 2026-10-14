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


""" util/lock_util.py: `PreLockedFileLock` holds its lock file from
construction and `release` removes it, leaking no descriptor. Under filelock
3.29 its release had become a no-op (TODO item 53). """

import os
import tempfile
import unittest

from util.lock_util import PreLockedFileLock


def _open_fds():
    return set(os.listdir('/proc/self/fd'))


class TestPreLockedFileLock(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, '.lock')

    def tearDown(self):
        self.tmp.cleanup()

    def test_construction_creates_the_file_and_release_removes_it(self):
        before = _open_fds()
        lock = PreLockedFileLock(self.path)
        self.assertTrue(os.path.exists(self.path))
        lock.release()
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(_open_fds(), before)

    def test_release_removes_a_file_another_process_created(self):
        """ The dump protocol: `dump_np.py` creates `.lock`, the aggregator
        releases it with a fresh PreLockedFileLock. """
        with open(self.path, 'w', encoding='utf-8'):
            pass
        PreLockedFileLock(self.path).release()
        self.assertFalse(os.path.exists(self.path))

    def test_release_twice_is_harmless(self):
        lock = PreLockedFileLock(self.path)
        lock.release()
        lock.release()
        self.assertFalse(os.path.exists(self.path))


if __name__ == '__main__':
    unittest.main()
