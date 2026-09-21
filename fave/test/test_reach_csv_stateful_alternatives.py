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

""" `X` may stand among a cell's alternatives (TODO item 19).

`roles_to_csv` used to print `(X)` for any pair carrying the stateful
condition, dropping every other condition it had. It now writes them all --
`(X|protocol:tcp;port:80|protocol:tcp;port:443)` -- and this is the reader's
half of that.

WHY IT IS NOT COSMETIC. `(X)` means "related traffic, and nothing else", so
this file's own `(X)` branch emits

    ! s=source.c1 && EF p=probe.s1 && f=related:0

For a pair that also permits HTTP that check is the opposite of the policy, and
it is a MUST-NOT-REACH check, so a correct data plane fails it. The old
rendering therefore did not hide information, it inverted a verification claim
-- measured on this fixture: the same policy spelled `(X)` produces that check
and no port checks at all.

A cell that is only `X` still takes the `(X)` branch untouched, which is the
point of keeping that branch: wl_up's 691 stateful cells and wl_ifi's 27 go
through it, and their generated checks are byte-identical across this change
(18,811 checks for wl_up, verified by regenerating both ways).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest


_FAVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MAPPING = {"Client": ["c1"], "Server": ["s1"]}

_ROLES = [
    {"name": "Client", "attributes": {"ipv4": "10.0.0.0/24"}, "services": []},
    {"name": "Server", "attributes": {"ipv4": "10.0.1.0/24"},
     "services": [{"name": "HTTP", "attributes": {"protocol": "tcp", "port": 80}},
                  {"name": "HTTPS", "attributes": {"protocol": "tcp", "port": 443}}]},
]


def _generate(cell, *extra):
    matrix = ",Client,Server\nClient,,%s\nServer,,\n" % cell

    with tempfile.TemporaryDirectory(prefix="stateful_alt_") as tmp:
        paths = {name: os.path.join(tmp, name) for name in
                 ("matrix.csv", "roles.json", "mapping.json", "checks.json",
                  "cchecks.json", "reachable.json")}
        with open(paths["matrix.csv"], "w") as raw:
            raw.write(matrix)
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


def _about(checks, source="c1", target="s1"):
    """ Only the checks about the pair under test. """
    return [c for c in checks
            if "source.%s" % source in c and "probe.%s" % target in c]


_MIXED = "(X|protocol:tcp;port:80|protocol:tcp;port:443)"


class TestAMixedCellAssertsBothHalves(unittest.TestCase):

    def test_the_stateful_alternative_is_asserted(self):
        checks = _about(_generate(_MIXED))

        self.assertIn("s=source.c1 && EF p=probe.s1 && f=related:1", checks)

    def test_each_service_is_asserted_under_related_0(self):
        checks = _about(_generate(_MIXED))

        for port in (80, 443):
            self.assertIn(
                "s=source.c1 && EF p=probe.s1 && f=related:0 && "
                "f=protocol:tcp && f=port:%d" % port, checks)

    def test_the_blanket_must_NOT_reach_is_NOT_emitted(self):
        """ THE INVERSION. `(X)` emits `! ... && f=related:0`, forbidding every
        unrelated packet -- including the HTTP the same cell permits. """
        checks = _about(_generate(_MIXED))

        self.assertNotIn(
            "! s=source.c1 && EF p=probe.s1 && f=related:0", checks)

    def test_the_same_policy_spelled_as_a_bare_X_produces_that_check(self):
        """ The other side of the previous test, so that it cannot pass because
        the fixture stopped reaching the branch at all. """
        checks = _about(_generate("(X)"))

        self.assertIn(
            "! s=source.c1 && EF p=probe.s1 && f=related:0", checks)
        self.assertFalse(
            [c for c in checks if "port:80" in c],
            "the bare `(X)` spelling asserts nothing about the services")


class TestTheComplementSkipsTheStatefulAlternative(unittest.TestCase):
    """ Each complement term is asserted under `related:0`, where the stateful
    alternative permits nothing. Complementing `X` along with the services
    would negate a token that is not a field at all. """

    def test_the_complement_is_taken_over_the_services_only(self):
        checks = [c for c in _about(_generate(_MIXED, "--complement"))
                  if c.startswith("!")]

        self.assertTrue(checks, "no complement checks were generated")
        for check in checks:
            self.assertNotIn("f=!X", check)
        self.assertIn(
            "! s=source.c1 && EF p=probe.s1 && f=related:0 && f=!protocol:tcp",
            checks)

    def test_the_complement_still_forbids_a_third_port(self):
        """ The complement's job: these services and nothing else. """
        checks = [c for c in _about(_generate(_MIXED, "--complement"))
                  if c.startswith("!")]

        self.assertIn(
            "! s=source.c1 && EF p=probe.s1 && f=related:0 && "
            "f=!port:443 && f=!port:80", checks)


class TestAServiceOnlyCellIsUnchanged(unittest.TestCase):
    """ The shape every workload in the tree actually uses. """

    def test_a_cell_without_X_behaves_as_before(self):
        checks = _about(_generate("(protocol:tcp;port:80)"))

        self.assertIn(
            "s=source.c1 && EF p=probe.s1 && f=related:0 && "
            "f=protocol:tcp && f=port:80", checks)
        self.assertFalse(
            [c for c in checks if "related:1" in c],
            "a cell with no `X` must assert nothing about related traffic")


if __name__ == '__main__':
    unittest.main()
