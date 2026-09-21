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

""" `scripts/start_aggr.sh` returns only once the aggregator is REGISTERED.

It used to return once the aggregator had BOUND. The two are one statement
apart in `aggregator_service.py` -- `sock.bind()` then `barrier.publish_owner()`
-- and `sock.bind()` is what creates the socket the gate watched, so the gate
released in between. `GenericBenchmark._startup` logs "started aggregator" and
calls `_wait_for_fave()` immediately, and the first barrier then found no owner;
since `barrier._owner_alive` reads an absent owner as "no aggregator is
registered" and `BarrierError` means "can no longer complete at all", a state
lasting microseconds was reported as permanent.

Measured on the real aggregator: the owner file was absent when the gate
returned in 10 of 12 starts before the change and 0 of 8 after. See TODO
item 17 -- note that the back-to-back benchmark failure which PROMPTED the item
had a different cause (`barrier.withdraw_owner`, covered in
`test_barrier.py`); this closes the gap the item proposed a fix for.

Driven with a STUB interpreter rather than a real aggregator, so it is
deterministic and belongs in the `fast` tier: the property under test is the
shell gate's contract, not anything the aggregator computes.
"""

import os
import shutil
import signal
import subprocess
import tempfile
import unittest


_FAVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_FAVE, 'scripts', 'start_aggr.sh')

#: Stands in for `$PYTHON`. `start_aggr.sh` invokes the interpreter twice: once
#: as `-c` to ask `util.barrier` where the owner file lives, and once to run the
#: aggregator itself. The stub answers the first from $STUB_OWNER and, for the
#: second, publishes (or does not) after a delay -- which is precisely the
#: bind-to-publish window the gate has to cover.
_STUB = """#!/bin/sh
if [ "$1" = "-c" ]; then
    echo "$STUB_OWNER"
    exit 0
fi
# Detach stdio before lingering. A real aggregator inherits the caller's
# stdout/stderr and holds them for its whole life, which is why capturing
# `start_aggr.sh` through a pipe blocks until the AGGREGATOR exits rather than
# until the script returns. True of the real thing and worth knowing, but here
# it would only make the suite wait for a stub that has already done its job.
exec >/dev/null 2>&1
sleep "$STUB_DELAY"
if [ "$STUB_PUBLISH" = "1" ]; then
    printf '{"pid": %d, "starttime": "1"}' $$ > "$STUB_OWNER"
fi
sleep "$STUB_LINGER"
"""


@unittest.skipUnless(os.path.isfile(_SCRIPT), "start_aggr.sh not present")
class TestStartAggrWaitsForRegistration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='start_aggr_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.owner = os.path.join(self.tmp, 'aggregator.owner')
        self.stub = os.path.join(self.tmp, 'python-stub')
        with open(self.stub, 'w') as raw:
            raw.write(_STUB)
        os.chmod(self.stub, 0o755)

    def _run(self, publish='1', delay='2', linger='3', wait='20'):
        env = dict(
            os.environ,
            PYTHON=self.stub,
            STUB_OWNER=self.owner,
            STUB_PUBLISH=publish,
            STUB_DELAY=delay,
            STUB_LINGER=linger,
            AGGR_WAIT=wait,
        )
        done = subprocess.run(
            ['bash', _SCRIPT, '-b', 'netplumber'],
            cwd=_FAVE, env=env, check=False, capture_output=True, timeout=120)
        self.addCleanup(self._reap)
        return done

    def _reap(self):
        """ Kill the backgrounded stub, which outlives the script by design. """
        try:
            with open(self.owner) as raw:
                import json
                os.kill(json.load(raw)['pid'], signal.SIGKILL)
        except Exception:                        # pylint: disable=broad-except
            pass

    def test_it_returns_only_AFTER_the_owner_file_exists(self):
        """ THE PROPERTY. The stub publishes two seconds late; a gate watching
        anything earlier would return with the file still absent. """
        done = self._run(publish='1', delay='2')

        self.assertEqual(done.returncode, 0, done.stderr.decode())
        self.assertTrue(
            os.path.exists(self.owner),
            "start_aggr.sh returned before the aggregator registered")

    def test_it_refuses_when_the_aggregator_never_registers(self):
        """ Bounded and loud: a silent give-up would let the benchmark carry on
        and blame the model. """
        done = self._run(publish='0', delay='0', linger='3', wait='2')

        self.assertEqual(done.returncode, 1)
        self.assertIn('did not register', done.stderr.decode())

    def test_it_refuses_at_once_when_the_aggregator_dies(self):
        """ Without the `kill -0` check this would wait out the full timeout on
        a process that is already gone. """
        done = self._run(publish='0', delay='0', linger='0', wait='60')

        self.assertEqual(done.returncode, 1)
        self.assertIn('exited before it registered', done.stderr.decode())

    def test_a_stale_registration_does_not_satisfy_the_gate(self):
        """ An owner file left by an unclean shutdown names a process that is
        gone. Returning on it would hand the caller a registration whose pid
        `_owner_alive` then rejects -- the same failure one step later. """
        with open(self.owner, 'w') as raw:
            raw.write('{"pid": 999999, "starttime": "1"}')

        done = self._run(publish='0', delay='0', linger='3', wait='2')

        self.assertEqual(done.returncode, 1, done.stderr.decode())
        self.assertIn('did not register', done.stderr.decode())

    def test_it_reports_a_barrier_module_it_cannot_reach(self):
        """ The owner path comes from `util.barrier`, so a PYTHONPATH that does
        not reach fave/ is named here rather than surfacing later as an
        aggregator dying inside a backgrounded process nobody reads. """
        broken = os.path.join(self.tmp, 'python-broken')
        with open(broken, 'w') as raw:
            raw.write('#!/bin/sh\nif [ "$1" = "-c" ]; then\n'
                      '  echo "ModuleNotFoundError: util" >&2\n  exit 1\nfi\n')
        os.chmod(broken, 0o755)

        done = subprocess.run(
            ['bash', _SCRIPT, '-b', 'netplumber'],
            cwd=_FAVE, env=dict(os.environ, PYTHON=broken),
            check=False, capture_output=True, timeout=60)

        self.assertEqual(done.returncode, 1)
        self.assertIn('cannot locate the barrier owner file',
                      done.stderr.decode())


if __name__ == '__main__':
    unittest.main()
