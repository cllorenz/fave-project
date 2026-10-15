#/usr/bin/env python3

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

""" This module waits until FaVe operations are finished.

It waits for the dumper's lock (`netplumber/dump_np.py`) to go: the aggregator
removes it when it has handled the dump. A lock nobody can remove is no reason
to wait forever (TODO item 58), and is told apart the way `util.barrier` tells
a dead aggregator from a busy one:

* no lock: done;
* a lock written BEFORE the running aggregator registered: no live process
  received the request it guards, so it is a leftover of an earlier run --
  removed, with a warning naming it, and done;
* no live aggregator: this run's request can never be handled -- exit 1;
* otherwise the aggregator is alive and the request is its: wait.
"""

import os
import sys
import time
import argparse

from typing import Optional, Tuple

from util import barrier

POLL_SECONDS = 0.2


def lock_state(lock: str, directory: Optional[str] = None) -> Tuple[str, str]:
    """ ('free' | 'held' | 'stale' | 'orphaned', why) for the dump lock. """
    try:
        written = os.stat(lock).st_mtime_ns
    except FileNotFoundError:
        return 'free', ''
    alive, reason = barrier.owner_alive(directory)
    if not alive:
        return 'orphaned', reason
    try:
        registered = os.stat(barrier.owner_path(directory)).st_mtime_ns
    except FileNotFoundError:
        return 'orphaned', 'the aggregator withdrew its registration'
    if written < registered:
        return 'stale', ('it was written before the running aggregator '
                         'registered, so no live process will remove it')
    return 'held', ''


def main(argv):
    """ Main method.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-d', '--dump',
        dest='dump',
        default='np_dump'
    )

    args = parser.parse_args(argv)
    lock = "%s/.lock" % args.dump

    while True:
        state, why = lock_state(lock)
        if state == 'free':
            return 0
        if state == 'stale':
            print("await_fave: removing the stale lock %s: %s" % (lock, why),
                  file=sys.stderr)
            try:
                os.remove(lock)
            except FileNotFoundError:
                pass
            return 0
        if state == 'orphaned':
            print("await_fave: FaVe will never release %s: %s" % (lock, why),
                  file=sys.stderr)
            return 1
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
