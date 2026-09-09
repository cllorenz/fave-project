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

""" Request-barrier protocol (util/barrier.py, TODO.md item 1r).

Pure Python -- no aggregator, no backend -- so these run in the `fast` tier and
gate. Every test that waits does so with a real `wait()` call and must return
promptly; the point of the design is that waiting is bounded by EVIDENCE (the
releaser's liveness), never by a clock, so a broken predicate shows up here as
a hanging test rather than a wrong answer. Each such test therefore runs the
wait on a helper thread and asserts it finished, so a regression fails instead
of wedging the suite.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from util import barrier
from util.barrier import BarrierError


def _run_wait(path, directory, timeout=10.0):
    """ Run barrier.wait on a thread; return (finished, raised_exception). """
    box = {}

    def target():
        try:
            barrier.wait(path, directory=directory, poll=0.01)
            box['ok'] = True
        except BaseException as exc:            # noqa: BLE001
            box['exc'] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    return (not thread.is_alive()), box


class BarrierTestCase(unittest.TestCase):
    """ Common fixture: an isolated barrier directory (no /dev/shm needed). """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _own(self):
        """ Register this test process as the barrier owner. """
        return barrier.publish_owner(self.dir)


class TestBarrierHappyPath(BarrierTestCase):
    """ A released barrier lets the waiter through. """

    def test_release_unblocks_the_waiter(self):
        self._own()
        guard = barrier.arm(self.dir)

        finished, box = _run_wait(guard, self.dir, timeout=0.2)
        self.assertFalse(finished, "wait() returned before the release")

        barrier.release(guard)
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "wait() did not return after the release")
        self.assertNotIn('exc', box)

    def test_wait_removes_the_barrier_file(self):
        self._own()
        guard = barrier.arm(self.dir)
        barrier.release(guard)
        barrier.wait(guard, directory=self.dir, poll=0.01)
        self.assertFalse(os.path.exists(guard))

    def test_armed_barrier_blocks_while_owner_lives(self):
        # The whole point: a slow-but-live FaVe must NOT be failed, however
        # long it takes. This process is the (live) owner, so the waiter has to
        # keep waiting rather than time out.
        self._own()
        guard = barrier.arm(self.dir)
        finished, _ = _run_wait(guard, self.dir, timeout=0.5)
        self.assertFalse(finished, "wait() gave up on a live owner")


class TestBarrierFailurePropagation(BarrierTestCase):
    """ L2a: a failure reported through the barrier must reach the waiter. """

    def test_release_with_error_raises(self):
        self._own()
        guard = barrier.arm(self.dir)
        barrier.release(guard, error="RPCError: peer closed the connection")

        with self.assertRaises(BarrierError) as ctx:
            barrier.wait(guard, directory=self.dir, poll=0.01)
        self.assertIn("peer closed the connection", str(ctx.exception))

    def test_error_release_also_unblocks_promptly(self):
        self._own()
        guard = barrier.arm(self.dir)
        barrier.release(guard, error="boom")
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "an error release must not leave a waiter hanging")
        self.assertIsInstance(box.get('exc'), BarrierError)


class TestBarrierOwnerLiveness(BarrierTestCase):
    """ L2: the wait is bounded by the releaser's liveness, not by a clock. """

    def test_no_owner_registered_fails_immediately(self):
        guard = barrier.arm(self.dir)          # nobody published an owner
        with self.assertRaises(BarrierError) as ctx:
            barrier.wait(guard, directory=self.dir, poll=0.01)
        self.assertIn("no aggregator is registered", str(ctx.exception))

    def test_dead_owner_fails_instead_of_waiting_forever(self):
        # A real process that exits without releasing: its pid is gone, so the
        # barrier can never be released and the waiter must say so.
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self._publish_pid(proc.pid, self._starttime_of(proc.pid))

        guard = barrier.arm(self.dir)
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "wait() hung on a dead owner")
        self.assertIsInstance(box.get('exc'), BarrierError)

    def test_zombie_owner_counts_as_dead(self):
        # THE trap this design exists to avoid: os.kill(pid, 0) and a bare
        # `pgrep -f` both succeed for a <defunct> process, so either predicate
        # would wait forever on a backend that already died. Popen without
        # wait() leaves exactly such a zombie.
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.poll()                     # do NOT reap -> stays a zombie
        _wait_for_state(proc.pid, 'Z')

        # Sanity: the naive predicate really would be fooled here.
        os.kill(proc.pid, 0)            # raises nothing -> "alive"

        self._publish_pid(proc.pid, self._starttime_of(proc.pid))
        guard = barrier.arm(self.dir)
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "wait() hung on a zombie owner")
        self.assertIn("zombie", str(box.get('exc')))
        proc.wait()                     # reap, keep the test env clean

    def test_pid_reuse_is_detected(self):
        # A recycled pid must not read as "still the aggregator", or the wait
        # would again be unbounded. Same pid, wrong start time.
        self._publish_pid(os.getpid(), "0")
        guard = barrier.arm(self.dir)
        with self.assertRaises(BarrierError) as ctx:
            barrier.wait(guard, directory=self.dir, poll=0.01)
        self.assertIn("reused", str(ctx.exception))

    def test_owner_withdrawal_fails_the_waiter(self):
        self._own()
        guard = barrier.arm(self.dir)
        barrier.withdraw_owner(self.dir)
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "wait() hung after the owner withdrew")
        self.assertIsInstance(box.get('exc'), BarrierError)

    def test_live_owner_with_missing_barrier_file_fails(self):
        # A cleaned runtime directory must not strand the waiter.
        self._own()
        guard = barrier.arm(self.dir)
        os.unlink(guard)
        finished, box = _run_wait(guard, self.dir)
        self.assertTrue(finished, "wait() hung on a vanished barrier file")
        self.assertIn("disappeared", str(box.get('exc')))

    # --- helpers -----------------------------------------------------------

    def _publish_pid(self, pid, starttime):
        with open(barrier.owner_path(self.dir), "w", encoding="utf-8") as fh:
            json.dump({"pid": pid, "starttime": starttime}, fh)

    @staticmethod
    def _starttime_of(pid):
        identity = barrier._proc_identity(pid)   # pylint: disable=protected-access
        return identity[1] if identity else None


class TestBarrierMisc(BarrierTestCase):
    """ Small contract details. """

    def test_release_of_empty_path_is_a_noop(self):
        # Messages without a barrier are the norm (model-building traffic), so
        # the aggregator's unconditional release must tolerate None/''.
        barrier.release(None)
        barrier.release("")

    def test_arm_returns_distinct_paths(self):
        self._own()
        paths = {barrier.arm(self.dir) for _ in range(8)}
        self.assertEqual(len(paths), 8)

    def test_release_is_atomic_from_a_readers_view(self):
        # wait() must never see a half-written state file.
        self._own()
        guard = barrier.arm(self.dir)
        for _ in range(50):
            barrier.release(guard, error=None)
            with open(guard, encoding="utf-8") as fh:
                self.assertIn(json.load(fh)["state"], ("armed", "done"))


def _wait_for_state(pid, state, tries=500):
    """ Spin briefly until `pid` reaches process state `state`. """
    import time
    for _ in range(tries):
        identity = barrier._proc_identity(pid)  # pylint: disable=protected-access
        if identity and identity[0] == state:
            return True
        time.sleep(0.01)
    raise AssertionError("pid %s never reached state %s" % (pid, state))


if __name__ == '__main__':
    unittest.main()
