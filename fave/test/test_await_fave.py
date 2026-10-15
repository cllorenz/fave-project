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

""" `misc/await_fave.py` (TODO item 58): a dump lock nobody can remove is no
reason to wait forever. A lock left by a run of 2026-10-09, in an earlier
container, held the first cell of 2026-10-15 for 11 minutes. """

import json
import os
import tempfile
import unittest

from unittest import mock

from misc import await_fave
from util import barrier


class TestAwaitFave(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run_dir = os.path.join(tmp.name, 'run')
        self.dump = os.path.join(tmp.name, 'np_dump')
        os.makedirs(self.dump)
        self.lock = os.path.join(self.dump, '.lock')
        patcher = mock.patch.object(barrier, 'BARRIER_DIR', self.run_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _register(self, when=None):
        """ This process as the registered aggregator, at `when`. """
        path = barrier.publish_owner(self.run_dir)
        if when is not None:
            os.utime(path, (when, when))

    def _lock(self, when):
        with open(self.lock, 'w') as handle:
            handle.write('111113\n5fdf45bfc27e')
        os.utime(self.lock, (when, when))

    def test_no_lock_is_done(self):
        self.assertEqual(await_fave.lock_state(self.lock)[0], 'free')
        self.assertEqual(await_fave.main(['-d', self.dump]), 0)

    def test_a_lock_older_than_the_aggregator_is_removed(self):
        self._lock(1_000_000)
        self._register(2_000_000)
        self.assertEqual(await_fave.lock_state(self.lock)[0], 'stale')
        with mock.patch('sys.stderr') as err:
            self.assertEqual(await_fave.main(['-d', self.dump]), 0)
        self.assertFalse(os.path.exists(self.lock))
        self.assertIn('stale lock', ''.join(c.args[0] for c in err.write.call_args_list))

    def test_a_lock_of_the_running_aggregator_is_waited_for(self):
        self._register(1_000_000)
        self._lock(2_000_000)
        self.assertEqual(await_fave.lock_state(self.lock)[0], 'held')

    def test_no_live_aggregator_fails_instead_of_waiting(self):
        self._lock(2_000_000)
        os.makedirs(self.run_dir, exist_ok=True)
        with open(barrier.owner_path(self.run_dir), 'w') as owner:
            json.dump({'pid': 2**22 + 12345, 'starttime': None}, owner)
        state, why = await_fave.lock_state(self.lock)
        self.assertEqual(state, 'orphaned')
        self.assertIn('no longer exists', why)
        with mock.patch('sys.stderr'):
            self.assertEqual(await_fave.main(['-d', self.dump]), 1)
        self.assertTrue(os.path.exists(self.lock))     # not ours to remove


if __name__ == '__main__':
    unittest.main()
