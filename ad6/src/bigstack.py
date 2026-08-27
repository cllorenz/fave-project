#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

""" AD6_PLAN.md §5.4 Stage B, B1's "third item" / AD6_ENCODING_PLAN.md §3.10:
sys.setrecursionlimit(10**6) (set by both main.py and fave_bridge.py, on
their own real recursive per-edge/per-node XML-tree operations -- e.g.
Instantiator._ConvertNodesToImplications, SATUtils.ConvertToCNF) lets
Python recurse far past the process's actual C stack, which is bounded by
the OS `ulimit -s` (8MB by default on Linux) regardless of
sys.setrecursionlimit -- raising that Python-level counter only disables
CPython's OWN bookkeeping guard, it does not grow the real stack. Once a
real topology is large/cyclic enough (confirmed on wl_stanford's real
16-router model, ~450k extra clauses once the acyclic rank constraints
escalate in), the process can blow the real stack and SEGFAULT --
silently: no Python exception, no traceback, the process just vanishes.
Confirmed and root-caused empirically (AD6_ENCODING_PLAN.md §3.10): fixed
by raising the OS stack ulimit before running.

`resource.setrlimit(RLIMIT_STACK, ...)` can raise the CURRENT process's
own limit on Linux (the main thread's stack is a growable-down mapping;
the kernel re-checks the current RLIMIT_STACK on page fault, not a value
frozen at exec time) -- but only up to the HARD limit, which the process
does not control and may already be capped low by whatever launched it,
and this trick is not portably reliable across platforms/kernels.

Reliably portable instead: run the actual work in a NEW thread with an
explicit large stack size (`threading.stack_size`, honoured at thread-
creation time everywhere Python's threading module runs, independent of
the process's own OS ulimit) -- the standard fix for exactly this
"deep recursion + raised sys.setrecursionlimit" pattern. """

import threading

_BIG_STACK_BYTES = 256 * 1024 * 1024  # 256MB -- comfortably covers the
# worst real case measured (Stanford's ~450k-extra-clause escalated
# instance); cheap to reserve (virtual address space, not committed
# memory) even when unused.


def run_with_big_stack(func, *args, **kwargs):
    """ Runs func(*args, **kwargs) in a new thread with a large explicit
    stack, and returns its result (or re-raises its exception) in the
    calling thread -- so a caller doing `sys.exit(run_with_big_stack(main))`
    behaves exactly like `sys.exit(main())` would, just without the real
    stack-overflow risk on deep recursion. """
    outcome = {}

    def _target():
        try:
            outcome['result'] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 -- re-raised verbatim below
            outcome['exception'] = exc

    previous_stack_size = threading.stack_size()
    threading.stack_size(_BIG_STACK_BYTES)
    try:
        thread = threading.Thread(target=_target)
        thread.start()
        thread.join()
    finally:
        threading.stack_size(previous_stack_size)

    if 'exception' in outcome:
        raise outcome['exception']
    return outcome.get('result')
