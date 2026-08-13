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

""" No-skip enforcement for the backend-dependent tests (APKEEP_FAITHFUL_PLAN.md
Phase 3c -- "lock the differential in as a CI gate").

The APKeep and backend-differential tests each guard themselves with
`skipUnless(available(), ...)` so a developer without the JVM/JPype/APKeep-jar
stack (or without libnetplumber) still gets a green `fast`/`integration` run.
But pytest scores a skip as a PASS, so in CI -- where these tests ARE the gate
that proves FaVe+APKeep and FaVe+NetPlumber agree -- a jar-build failure, a
missing JPype, or an unbuilt libnetplumber would turn the whole differential
into a silent skip and the gate would go green vacuously. That is the exact
"a skip is NOT a pass" hazard `exactness_gate.sh` warns about, with nothing
enforcing it.

`require_or_skip(condition, reason)` is a drop-in for `unittest.skipUnless`:
- condition met                       -> run the test (no-op);
- condition unmet, REQUIRE flag unset -> skip, exactly as before (local runs
  stay skip-friendly);
- condition unmet, REQUIRE flag set   -> FAIL, so CI cannot pass the gate
  without actually executing it.

CI opts in by exporting FAVE_REQUIRE_BACKENDS=1 for the tier that owns the gate
(the integration job) -- the same "CI sets the floor, local does not gate"
pattern as COVERAGE_MIN. It is deliberately per-precondition: every reason a
required test could fail to run (backend unavailable, generated inputs missing)
becomes a hard failure under the flag, never a skip.
"""

import functools
import os
import unittest

from typing import Any, Callable

_REQUIRE_ENV = "FAVE_REQUIRE_BACKENDS"


def backends_required() -> bool:
    """ True iff CI has demanded that the backend-dependent tests actually run
    (FAVE_REQUIRE_BACKENDS set to a non-empty value). """
    return bool(os.environ.get(_REQUIRE_ENV))


def _fail(reason: str) -> Callable[[Any], Any]:
    """ Class/function decorator that makes the decorated test ERROR out with
    `reason` instead of being collected normally. On a class this replaces
    setUpClass (the whole class errors before any test body runs -- the original
    setUpClass would itself fail against the unavailable backend anyway); on a
    method it wraps the body. """
    def decorate(obj: Any) -> Any:
        if isinstance(obj, type):
            def _raise(_cls: Any) -> None:
                raise AssertionError(reason)
            obj.setUpClass = classmethod(_raise)  # type: ignore[assignment]
            return obj

        @functools.wraps(obj)
        def wrapper(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(reason)
        return wrapper
    return decorate


def require_or_skip(condition: bool, reason: str) -> Callable[[Any], Any]:
    """ Like `unittest.skipUnless(condition, reason)`, but an unmet condition is
    a hard FAILURE (not a skip) when FAVE_REQUIRE_BACKENDS is set -- so a CI job
    that owns the differential gate cannot pass it by silently skipping. """
    if condition:
        return lambda obj: obj
    if backends_required():
        return _fail("%s [%s set -> required, must not skip]" % (reason, _REQUIRE_ENV))
    return unittest.skip(reason)
