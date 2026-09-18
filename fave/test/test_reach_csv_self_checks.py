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

""" A filled diagonal only means something when the matrix came from STRICT mode.

`policy_translator` in its default (loose) mode gives every atomic role an
implicit self-reachability policy (`policy_builder.build_policies`), so in a
loose matrix EVERY diagonal is filled whether or not the policy asked for one.
A positive self-check read off such a diagonal asserts reachability nobody
wrote -- and the data plane does not deliver it, so it fails.

That is not hypothetical: wl_ifi's roles are all subnets, so once the generator
learned to keep a subnet role's self-check (the wl_up `Wifi` fix), regenerating
wl_ifi produced 16 of them and its ad6 gates went red. The discriminator cannot
see the difference from the matrix, so the caller states it: `--strict`.

Both directions are pinned here, on a synthetic matrix rather than a workload,
so the rule is tested where it is decided.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)

# One role whose single node stands for a /24 -- exactly the shape the
# self-check rule is about -- with its diagonal filled.
_MATRIX = ",Subnet\nSubnet,X\n"
_ROLES = [{"name": "Subnet", "attributes": {"ipv4": "10.0.0.0/24"}}]


def _generate(strict):
    """ Run the generator on the synthetic matrix; return its checks. """
    with tempfile.TemporaryDirectory(prefix="self_checks_") as tmp:
        paths = {name: os.path.join(tmp, name) for name in
                 ("matrix.csv", "roles.json", "checks.json",
                  "cchecks.json", "reachable.json")}
        with open(paths["matrix.csv"], "w") as raw:
            raw.write(_MATRIX)
        with open(paths["roles.json"], "w") as raw:
            json.dump(_ROLES, raw)

        subprocess.run(
            [sys.executable, "bench/reach_csv_to_checks.py",
             "-p", paths["matrix.csv"], "-m", "bench/empty.json",
             "--roles", paths["roles.json"],
             "-c", paths["checks.json"], "--cchecks", paths["cchecks.json"],
             "-j", paths["reachable.json"]] + (["--strict"] if strict else []),
            cwd=_FAVE, check=True, capture_output=True,
            env=dict(os.environ, PYTHONPATH=_FAVE))

        with open(paths["checks.json"]) as raw:
            checks = json.load(raw)
        with open(paths["reachable.json"]) as raw:
            reach = json.load(raw)
    return checks, reach


class TestSelfCheckNeedsStrictMode(unittest.TestCase):

    def test_strict_keeps_the_self_check(self):
        """ The diagonal was written by an FPL rule, so it is asserted. """
        checks, reach = _generate(strict=True)
        self.assertEqual(checks, ["s=source.Subnet && EF p=probe.Subnet"])
        self.assertIn("Subnet", reach.get("Subnet", []))

    def test_loose_does_not(self):
        """ The diagonal is injected for every role, so it asserts nothing. """
        checks, reach = _generate(strict=False)
        self.assertEqual(checks, [])
        self.assertNotIn("Subnet", reach.get("Subnet", []))


if __name__ == '__main__':
    unittest.main()
