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

""" Request barriers: let a client wait until FaVe has actually FINISHED a
request, rather than merely accepted it (TODO.md item 1r).

FaVe's aggregator protocol is fire-and-forget: `fave_sendmsg` posts a message
and returns. That is fine for model-building messages, but for the ones whose
whole point is a RESULT -- `check_compliance`, `check_anomalies`, `report` --
the caller has no way to know when the answer exists. The `bench` tier read the
report immediately after asking for it and reported 35 false compliance
violations on wl_i2 while the correct answer (matching the tracked oracle) was
0.

Protocol -- three parties, one small file per request:

  1. the CLIENT arms a barrier (`arm`), puts its path in the message it sends,
     and then blocks on it (`wait`);
  2. the AGGREGATOR, having finished handling that message, marks the barrier
     done (`release`), passing an error string if the handling failed;
  3. the CLIENT's `wait` returns on success, or raises `BarrierError`.

The aggregator handles messages with ONE thread off ONE FIFO queue, and
`check_compliance` blocks all the way down to net_plumber's reply
(`jsonrpc._asend_recv`). So "the aggregator finished message N" transitively
means "every earlier message was applied AND net_plumber answered N" -- which
is exactly the barrier the benchmarks need, with no polling of the engine.

WHY THERE IS NO TIMEOUT
-----------------------
FaVe's runtime is not known beforehand -- measured 4.4 s (wl_stanford) to 289 s
(wl_i2) on one machine, and it grows with the workload -- so any wall-clock
deadline is simultaneously too tight (a premature timeout is a FALSE failure,
the worst outcome for a compliance tool) and too loose (a deadlock noticed
hours later is not detection). This module therefore waits INDEFINITELY, and
bounds the wait on EVIDENCE instead: it keeps waiting only while the process
responsible for releasing the barrier is provably still the live aggregator.
When that stops being true it fails immediately, with a reason. Nothing here
guesses a duration.

The two liveness traps this deliberately handles:

  * ZOMBIES. `os.kill(pid, 0)` and a bare `pgrep -f` both SUCCEED for a
    `<defunct>` process, so either would wait forever on a backend that died
    minutes ago. Liveness is read from the process STATE in /proc.
  * PID REUSE. A pid alone can be recycled by an unrelated process, which would
    also produce an unbounded wait. The owner file records the aggregator's
    start time as well, so identity -- not just existence -- is checked.

Residual, out of scope here (see TODO.md item 1r): the aggregator's handler
THREAD could wedge while its process stays alive. `release`-in-`finally` on the
aggregator side covers the case where handling *raises*; a thread blocked
forever inside a healthy process is what an optional bounded-silence heartbeat
would add.
"""

import errno
import json
import os
import time
import uuid

from typing import Optional, Tuple

# Where barriers and the owner file live. Same tmpfs directory the rest of the
# runtime state uses; overridable so tests need no /dev/shm.
BARRIER_DIR = os.environ.get("FAVE_BARRIER_DIR", "/dev/shm/np")

# The aggregator publishes its identity here so waiters know whom to watch.
OWNER_FILE = "aggregator.owner"

_POLL_SECONDS = 0.05

_ARMED = "armed"
_DONE = "done"


class BarrierError(Exception):
    """ Raised when a request cannot complete: either the aggregator reported a
    failure handling it, or it can no longer complete it at all (the aggregator
    died). Never raised merely because something took a long time. """


def _proc_identity(pid: int) -> Optional[Tuple[str, str]]:
    """ `(state, starttime)` for `pid` from /proc, or None if it is gone.

    `comm` (field 2) may itself contain spaces and parentheses, so the fields
    after it are parsed from the LAST ')' rather than by splitting the whole
    line. State is field 3 and starttime field 22, i.e. offsets 0 and 19 in
    what follows.
    """
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as stat_file:
            raw = stat_file.read()
    except (IOError, OSError):
        return None

    tail = raw[raw.rfind(')') + 1:].split()
    if len(tail) < 20:
        return None
    return tail[0], tail[19]


def owner_path(directory: str = None) -> str:
    """ Path of the file identifying the process that releases barriers. """
    return os.path.join(directory or BARRIER_DIR, OWNER_FILE)


def publish_owner(directory: str = None) -> str:
    """ Aggregator side, at startup: declare "I am the one who releases
    barriers", recording pid AND start time so waiters can verify identity
    rather than mere pid existence. Returns the path written. """
    path = owner_path(directory)
    pid = os.getpid()
    identity = _proc_identity(pid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as owner_file:
        json.dump(
            {"pid": pid, "starttime": identity[1] if identity else None},
            owner_file
        )
    return path


def withdraw_owner(directory: str = None) -> None:
    """ Aggregator side, on clean shutdown: a missing owner file is an
    unambiguous "nobody will release anything any more".

    ONLY IF THE REGISTRATION IS STILL OURS. `aggregator/stop.py` sends the
    request and returns without waiting for the process to exit, so an
    aggregator can still be shutting down while the NEXT one is already up and
    registered. Withdrawing unconditionally then deleted the successor's
    registration, and its very next barrier reported "no aggregator is
    registered" -- a live aggregator declared dead by its predecessor. Two
    benchmarks run back to back hit this every time (TODO.md item 17).

    A file we cannot read is left alone rather than removed: we cannot tell
    whose it is, and `_owner_alive` already diagnoses that case loudly.
    """
    path = owner_path(directory)

    try:
        with open(path, encoding="utf-8") as owner_file:
            owner = json.load(owner_file)
    except (IOError, OSError):
        return                                  # already gone
    except ValueError:
        return                                  # unreadable: not ours to judge

    # The pid alone is exact here: a reused pid would mean this process is gone,
    # and a gone process is not running this line.
    if owner.get("pid") == os.getpid():
        _unlink(path)


def _owner_alive(directory: str = None) -> Tuple[bool, str]:
    """ `(alive, reason_if_not)` for the declared barrier owner. """
    path = owner_path(directory)
    try:
        with open(path, encoding="utf-8") as owner_file:
            owner = json.load(owner_file)
    except (IOError, OSError):
        return False, "no aggregator is registered (%s is absent)" % path
    except ValueError:
        return False, "the aggregator registration in %s is unreadable" % path

    pid = owner.get("pid")
    if not isinstance(pid, int):
        return False, "the aggregator registration in %s has no pid" % path

    identity = _proc_identity(pid)
    if identity is None:
        return False, "the aggregator (pid %d) no longer exists" % pid

    state, starttime = identity
    if state == "Z":
        # NB os.kill(pid, 0) would happily report this one as alive.
        return False, "the aggregator (pid %d) is a zombie" % pid

    expected = owner.get("starttime")
    if expected is not None and expected != starttime:
        return False, (
            "pid %d is no longer the aggregator (it was reused by another "
            "process)" % pid
        )

    return True, ""


def _unlink(path: str) -> None:
    """ Remove `path`, tolerating its absence. """
    try:
        os.unlink(path)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise


def _write_state(path: str, state: str, error: Optional[str] = None) -> None:
    """ Write a barrier's state atomically, so a waiter never reads a half-file
    (rename within a directory is atomic). """
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as barrier_file:
        json.dump({"state": state, "error": error}, barrier_file)
    os.replace(tmp, path)


def _read_state(path: str) -> Optional[dict]:
    """ A barrier's state, or None if the file is gone / not yet readable. """
    try:
        with open(path, encoding="utf-8") as barrier_file:
            return json.load(barrier_file)
    except (IOError, OSError):
        return None
    except ValueError:
        # A concurrent write should be impossible (os.replace is atomic), but
        # treat an unparseable read as "not ready" rather than as an error.
        return None


def arm(directory: str = None) -> str:
    """ Client side: create a fresh barrier and return its path, to be put in
    the message whose completion it guards. """
    path = os.path.join(
        directory or BARRIER_DIR, "barrier.%s" % uuid.uuid4().hex
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write_state(path, _ARMED)
    return path


def release(path: str, error: Optional[str] = None) -> None:
    """ Aggregator side: mark the guarded request finished.

    MUST be called from a `finally`: if handling raised, a waiter that never
    learns about it waits for as long as the aggregator process happens to live
    -- which converts a loud failure into a silent hang. Pass the exception
    text as `error` and the waiter raises it instead.
    """
    if not path:
        return
    try:
        _write_state(path, _DONE, error)
    except (IOError, OSError):
        # Losing the release is bad (a waiter blocks until it notices the
        # aggregator is gone), but it must never take the aggregator down.
        pass


def wait(path: str, directory: str = None, poll: float = _POLL_SECONDS) -> None:
    """ Client side: block until the guarded request is finished.

    Waits indefinitely while the aggregator is provably alive -- there is no
    timeout, by design (see the module docstring). Raises `BarrierError` if the
    aggregator reported a failure, or if it can no longer complete the request.
    """
    while True:
        state = _read_state(path)

        if state is not None and state.get("state") == _DONE:
            error = state.get("error")
            _unlink(path)
            if error:
                raise BarrierError("FaVe failed to handle the request: %s" % error)
            return

        alive, reason = _owner_alive(directory)
        if not alive:
            _unlink(path)
            raise BarrierError(
                "FaVe will never finish the request: %s" % reason
            )

        if state is None:
            # Armed file vanished while the aggregator is still alive: someone
            # cleaned the runtime directory underneath us. Waiting on a barrier
            # that can no longer be released would hang forever.
            raise BarrierError("the barrier file %s disappeared" % path)

        time.sleep(poll)
