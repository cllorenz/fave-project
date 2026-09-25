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

""" What produced a generated workload directory, recorded IN it.

A benchmark's inputs are derived, gitignored and rebuilt by whatever ran last,
so a directory full of them says nothing about where it came from. That is not
hypothetical: `wl_deltanet` had a `FAVE_DELTANET_TRACE` selector for three days
and the directory it wrote into recorded neither which trace had been used nor
that a choice existed (CLOUD_BENCH_PLAN.md §2.3, and D6 is the fix).

`SOURCE.json` is that record: the generator, every generated file's sha256, and
whatever the workload knows that the files do not state about themselves.

**It is also the only honest way to say "all backends got the same inputs".**
`GenericBenchmark.run()` calls `_pre_preparation` itself, so running one model
on three engines regenerates it three times; without a stamp to compare against,
"the same inputs" is an assumption about determinism rather than an observation.
`verify` turns it into one, and catches a hand edit made while debugging by the
same mechanism -- which is `util/raw_data.verify_raw`'s argument, one tier down.

It is deliberately NOT a manifest of what SHOULD be there. It records what was,
so a mismatch means something changed between two moments, not that something
failed a specification nobody wrote.
"""

import hashlib
import json
import os

from typing import Any, Dict, List, Optional


#: Written into every generated workload directory.
STAMP = 'SOURCE.json'

#: Bumped when the stamp's shape changes, so a stale one is refused rather than
#: read with the wrong expectations.
VERSION = 1


class StampError(Exception):
    """ A stamp that cannot be read, or that no longer describes what is there. """


def _sha256(path: str) -> str:
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def sha256(path: str) -> str:
    """ A file's digest -- exported because callers stamp raw inputs too. """
    return _sha256(path)


def write(prefix: str, generator: str, files: Dict[str, str],
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ Record `files` as they are now, under `prefix/SOURCE.json`.

    `files` maps a label to a path. A path that does not exist is an ERROR
    rather than an omission: a stamp that quietly skips a missing file is a
    stamp that says a directory is complete when it is not.
    """
    missing = sorted(label for label, path in files.items()
                     if not os.path.isfile(path))
    if missing:
        raise StampError(
            "cannot stamp %s: %s not generated. A stamp that skipped them "
            "would record an incomplete directory as a complete one."
            % (prefix, ', '.join(missing)))

    stamp: Dict[str, Any] = {
        'version': VERSION,
        'generator': generator,
        'files': {label: _sha256(path) for label, path in sorted(files.items())},
    }
    if extra:
        stamp.update(extra)

    path = os.path.join(prefix, STAMP)
    with open(path, 'w') as handle:
        handle.write(json.dumps(stamp, indent=2, sort_keys=True) + '\n')
    return stamp


def read(prefix: str) -> Dict[str, Any]:
    """ The stamp in `prefix`, or a `StampError` naming what is wrong with it. """
    path = os.path.join(prefix, STAMP)
    if not os.path.isfile(path):
        raise StampError(
            "%s has no %s: nothing records which inputs are in it, so nothing "
            "can say whether they moved." % (prefix, STAMP))

    with open(path) as handle:
        try:
            stamp = json.load(handle)
        except ValueError as exc:
            raise StampError("%s is not readable JSON: %s" % (path, exc)) from exc

    if stamp.get('version') != VERSION:
        raise StampError(
            "%s is version %r and this reader is version %d -- refused rather "
            "than read with the wrong expectations."
            % (path, stamp.get('version'), VERSION))
    return stamp


def verify(prefix: str, files: Dict[str, str]) -> List[str]:
    """ Every way `files` now differs from what `prefix`'s stamp recorded.

    An empty list is the only clean answer. Returned rather than raised, because
    the caller decides whether a difference is a failure -- a benchmark
    regenerating its own inputs between backends wants a hard stop, while a
    tool reporting on a directory wants to print all of them.
    """
    stamp = read(prefix)
    recorded = stamp['files']
    problems: List[str] = []

    for label in sorted(set(recorded) | set(files)):
        if label not in files:
            problems.append("%s: stamped, but not asked about now" % label)
            continue
        if label not in recorded:
            problems.append("%s: present now, but not stamped" % label)
            continue
        path = files[label]
        if not os.path.isfile(path):
            problems.append("%s: stamped, and now missing (%s)" % (label, path))
            continue
        digest = _sha256(path)
        if digest != recorded[label]:
            problems.append(
                "%s: %s changed since the stamp (%s -> %s)"
                % (label, path, recorded[label][:12], digest[:12]))

    return problems
