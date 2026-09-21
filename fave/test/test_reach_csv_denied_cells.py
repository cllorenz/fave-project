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

""" What a DENIED matrix cell asserts (CLOUD_BENCH_PLAN.md §1.9.6).

Two properties of `bench/reach_csv_to_checks.py`'s denied-cell branch, both
found while building wl_cloud's policy and both tested on a synthetic matrix
rather than a workload, so the rule is pinned where it is decided.

**1. A denied cell covers EVERY endpoint of the target role.** It did not. The
branch used the bare `target`, which the `for target in targets` loop above it
had left bound to the LAST element -- so a role mapping to several devices was
asserted unreachable at one of them and silently unasserted at the rest. Every
workload before wl_cloud maps each role to one device in the cases that
mattered, so the two spellings agreed; wl_up's 40 multi-device roles did not,
and regenerating it moved the check set from 11,911 to 18,811. The 6,900 that
had been missing all PASS, so nothing was hiding behind them -- but they were
not being asked.

**2. `--deny-per-service`, off by default.** A denied cell normally denies ALL
traffic to the target, which is right where a role is a subnet. Where a role is
a SERVICE, two roles can name the same machines -- wl_cloud's services 2 and 3
are both 10.0.17.0/25, separated only by TCP port -- and the blanket reading
makes such a matrix self-contradictory rather than merely strict: a row
permitting service 2 and denying service 3 asks for a packet to arrive at those
hosts and not arrive at them. Probe-side filtering would be the other way to
resolve it, but `netplumber/adapter.py` has `filter_fields` commented out, so
the qualification lives in the check.
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
    {"name": "Client", "attributes": {"ipv4": "10.0.0.0/24"}, "services": []},
    {"name": "Server", "attributes": {"ipv4": "10.0.1.0/24"},
     "services": [{"name": "HTTP",
                   "attributes": {"protocol": "tcp", "port": 80}}]},
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
    """ Property 1. """

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


class TestDenyPerService(unittest.TestCase):
    """ Property 2. """

    def test_off_by_default_the_denial_is_unconditional(self):
        for check in _negatives(_generate()):
            self.assertNotIn('&& f=', check)

    def test_on_the_denial_names_the_targets_offered_services(self):
        checks = _negatives(_generate('--deny-per-service'))
        into_server = [c for c in checks if 'probe.s' in c]
        self.assertEqual(len(into_server), 9)
        for check in into_server:
            self.assertTrue(check.endswith(' && f=protocol:tcp && f=port:80'),
                            "%r does not name Server's service" % check)

    def test_a_target_offering_nothing_keeps_the_blanket_denial(self):
        """ `Client` offers no service, so there is nothing to qualify. Falling
        back is the only safe option -- emitting nothing would DELETE the
        check, which is a silently weaker gate. """
        checks = _negatives(_generate('--deny-per-service'))
        # Ten: Server's three devices plus Client's own two (the diagonal is
        # denied too), against Client's two.
        into_client = [c for c in checks if 'probe.c' in c]
        self.assertEqual(len(into_client), 10)
        for check in into_client:
            self.assertNotIn('&& f=', check)

    def test_the_flag_does_not_touch_permitted_cells(self):
        self.assertEqual(
            [c for c in _generate() if not c.startswith('!')],
            [c for c in _generate('--deny-per-service') if not c.startswith('!')])

    def test_the_flag_refuses_to_run_without_roles(self):
        """ Without `--roles` there are no offered services to name, so every
        denial would quietly fall back to the blanket form -- the behaviour the
        flag exists to change. """
        with tempfile.TemporaryDirectory(prefix="denied_cells_") as tmp:
            matrix = os.path.join(tmp, "matrix.csv")
            mapping = os.path.join(tmp, "mapping.json")
            with open(matrix, "w") as raw:
                raw.write(_MATRIX)
            with open(mapping, "w") as raw:
                json.dump(_MAPPING, raw)

            done = subprocess.run(
                [sys.executable, "bench/reach_csv_to_checks.py", "--strict",
                 "--deny-per-service", "-p", matrix, "-m", mapping,
                 "-c", os.path.join(tmp, "c.json"),
                 "--cchecks", os.path.join(tmp, "cc.json"),
                 "-j", os.path.join(tmp, "r.json")],
                cwd=_FAVE, check=False, capture_output=True,
                env=dict(os.environ, PYTHONPATH=_FAVE))

        self.assertNotEqual(done.returncode, 0)
        self.assertIn('--deny-per-service needs --roles', done.stderr.decode())


if __name__ == '__main__':
    unittest.main()
