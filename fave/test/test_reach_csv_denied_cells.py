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

""" A DENIED matrix cell covers every endpoint of the target role.

It did not. The branch used the bare `target`, which the `for target in targets`
loop above it had left bound to the LAST element -- so a role mapping to several
devices was asserted unreachable at one of them and silently unasserted at the
rest. Every branch above it iterates; this one did not, and the denied direction
is the one where a missing check means a missing violation.

Only a workload with multi-device roles in denied cells can see it. wl_up has
40 such roles: its check set moves 11,911 -> 18,811, and all 6,900 that had been
missing PASS -- so nothing was hiding behind them, but they were not being
asked. Found while building wl_cloud's policy, whose roles are services spread
over one to nine leaf routers and so are multi-device by nature.

Tested on a synthetic matrix rather than a workload, so the rule is pinned where
it is decided.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)

# Two roles, one permitted cell and one denied, so both branches are exercised
# by the same run. `Server` maps to THREE devices and `Client` to two.
_MATRIX = (
    ",Client,Server\n"
    "Client,,(protocol:tcp;port:80)\n"
    "Server,,\n"
)

_MAPPING = {
    "Client": ["c1", "c2"],
    "Server": ["s1", "s2", "s3"],
}

_ROLES = [
    {"name": "Client", "attributes": {"ipv4": "10.0.0.0/24"}},
    {"name": "Server", "attributes": {"ipv4": "10.0.1.0/24"}},
]


def _generate(*extra):
    with tempfile.TemporaryDirectory(prefix="denied_cells_") as tmp:
        paths = {name: os.path.join(tmp, name) for name in
                 ("matrix.csv", "roles.json", "mapping.json", "checks.json",
                  "cchecks.json", "reachable.json")}
        with open(paths["matrix.csv"], "w") as raw:
            raw.write(_MATRIX)
        with open(paths["roles.json"], "w") as raw:
            json.dump(_ROLES, raw)
        with open(paths["mapping.json"], "w") as raw:
            json.dump(_MAPPING, raw)

        subprocess.run(
            [sys.executable, "bench/reach_csv_to_checks.py", "--strict",
             "-p", paths["matrix.csv"], "-m", paths["mapping.json"],
             "--roles", paths["roles.json"],
             "-c", paths["checks.json"], "--cchecks", paths["cchecks.json"],
             "-j", paths["reachable.json"]] + list(extra),
            cwd=_FAVE, check=True, capture_output=True,
            env=dict(os.environ, PYTHONPATH=_FAVE))

        with open(paths["checks.json"]) as raw:
            return json.load(raw)


def _negatives(checks):
    return [c for c in checks if c.startswith('!')]


def _probes(checks):
    out = []
    for check in checks:
        out.extend(
            token[len('p=probe.'):] for token in check.split()
            if token.startswith('p=probe.'))
    return out


class TestDeniedCellCoversEveryEndpoint(unittest.TestCase):
    def test_a_denied_cell_names_every_device_of_the_target_role(self):
        """ `Server -> Client` is denied; Client has two devices and Server
        three, so the cell is six checks, not two. """
        denied = [
            c for c in _negatives(_generate())
            if 'source.s' in c and ('probe.c1' in c or 'probe.c2' in c)
        ]
        self.assertEqual(len(denied), 6)
        self.assertEqual(
            sorted(denied),
            sorted('! s=source.%s && EF p=probe.%s' % (s, t)
                   for s in ('s1', 's2', 's3') for t in ('c1', 'c2')))

    def test_the_diagonal_is_denied_at_every_device_too(self):
        """ `Server -> Server` is denied: nine checks over three devices,
        INCLUDING each device against itself -- the denied branch asserts over
        every source, unlike the permitted branch's `_peers`. """
        denied = [c for c in _negatives(_generate()) if 'probe.s' in c]
        self.assertEqual(len(denied), 9)

    def test_a_permitted_cell_still_names_every_device(self):
        """ The branch that always iterated, so the two now agree. """
        permitted = [c for c in _generate() if not c.startswith('!')]
        self.assertEqual(len(permitted), 6)
        self.assertEqual(sorted(set(_probes(permitted))), ['s1', 's2', 's3'])


if __name__ == '__main__':
    unittest.main()
