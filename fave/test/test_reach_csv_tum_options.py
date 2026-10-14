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

""" Two options of `bench/reach_csv_to_checks.py` made for wl_tum's derived
policy (owner, 2026-10-14; bench/wl_tum/WORKLOAD.md), on a synthetic matrix:

**`--deny-unpermitted-services`.** A cell permitting some services asserts
them reachable and nothing else: a service the target OFFERS and the cell does
not permit went unasserted, so an engine letting it through passed. With the
option, each such service is a must-not-reach check, as a positive term --
unlike `--complement`, which negates the permitted ones and so forbids every
port the policy does not enumerate.

**`--only-with ROLE`.** Only the cells ROLE takes part in become checks:
wl_tum states the traffic between the Internet and its inside roles and
nothing between inside roles, whose cells would otherwise read as denied.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)

_MATRIX = (
    ",Internet,Web,Mail\n"
    "Internet,,(X|protocol:tcp;port:80),(X)\n"
    "Web,X,,\n"
    "Mail,X,,\n"
)

_MAPPING = {"Internet": ["internet"], "Web": ["web"], "Mail": ["mail"]}

_ROLES = [
    {"name": "Web", "attributes": {"ipv4": "10.0.0.1/32"},
     "services": [{"name": "HTTP", "attributes": {"protocol": "tcp", "port": 80}},
                  {"name": "SSH", "attributes": {"protocol": "tcp", "port": 22}},
                  {"name": "ICMP", "attributes": {"protocol": "icmp"}}]},
    {"name": "Mail", "attributes": {"ipv4": "10.0.0.2/32"},
     "services": [{"name": "SMTP", "attributes": {"protocol": "tcp", "port": 25}}]},
]


def _generate(*extra):
    with tempfile.TemporaryDirectory(prefix="tum_options_") as tmp:
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


class TestDenyUnpermittedServices(unittest.TestCase):

    def test_off_an_unpermitted_service_goes_unasserted(self):
        checks = _generate()
        self.assertFalse([c for c in checks if c.startswith('! s=source.internet && EF p=probe.web')])

    def test_on_each_offered_unpermitted_service_is_must_not_reach(self):
        checks = _generate('--deny-unpermitted-services')
        web = sorted(c for c in checks if c.startswith('! s=source.internet && EF p=probe.web'))
        self.assertEqual(web, [
            '! s=source.internet && EF p=probe.web && f=related:0 && f=protocol:icmp',
            '! s=source.internet && EF p=probe.web && f=related:0 && f=protocol:tcp && f=port:22',
        ])
        # the permitted service stays a must-reach check, and is not denied
        self.assertIn('s=source.internet && EF p=probe.web && f=related:0 '
                      '&& f=protocol:tcp && f=port:80', checks)
        self.assertFalse([c for c in checks if 'f=!' in c], "no negated term")

    def test_a_cell_without_services_keeps_its_blanket_form(self):
        # Mail's cell is stateful only: a blanket must-not-reach for NEW traffic
        checks = _generate('--deny-unpermitted-services')
        self.assertEqual(sorted(c for c in checks if c.startswith('! s=source.internet && EF p=probe.mail')),
                         ['! s=source.internet && EF p=probe.mail && f=related:0'])

    def test_needs_roles(self):
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.run([sys.executable, "bench/reach_csv_to_checks.py",
                            "--deny-unpermitted-services", "-p", "/dev/null"],
                           cwd=_FAVE, check=True, capture_output=True,
                           env=dict(os.environ, PYTHONPATH=_FAVE))


class TestOnlyWith(unittest.TestCase):

    def test_drops_the_cells_between_other_roles(self):
        every = _generate()
        only = _generate('--only-with', 'Internet')
        between = [c for c in every if 'internet' not in c]
        self.assertTrue(between, "the matrix has cells between inside roles")
        self.assertEqual(sorted(only), sorted(c for c in every if 'internet' in c))


if __name__ == '__main__':
    unittest.main()
