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

""" wl_up's compliance artifacts derive from the FPL inventory and policy, and
from nothing else -- and a role's SELF-rule survives that derivation when, and
only when, it says something.

The invariant: `checks.json`, `cchecks.json` and `reachable.json` are generated
from the tracked `roles_and_services.txt` + `reach.txt` (via the policy
translator's matrix). They are gitignored, so nothing else may quietly become a
source of truth for them.

The self-rule handling this pins (APKEEP_BACKEND.md, the wl_up headline entry):

  * `Wifi <--> Wifi` (reach.txt:17) produces a real check. `Wifi` is an IPv6 /64
    with NO `hosts` list -- a subnet role whose single model node stands for
    every client device in it -- so the rule says wifi clients may reach each
    other, which is how wifi networks work and is an ordinary compliance
    question. It used to be dropped, costing the wl_up headline one pair.
  * `Internet` never does. It is external, outside the administrative reach of
    whoever writes the policy, so its self-reachability is not answerable. FPL
    carries it as a builtin role, so it appears in nearly every policy.
  * a single-host role does not either. wl_up's eight `DMZ*` diagonals used to
    be filled by `DMZ <--> DMZ` superrole expansion, although no rule names a
    member reaching itself; strict mode now suppresses that, so each member is
    an ordinary empty diagonal carrying a negative self-check.
  * a role whose diagonal is EMPTY keeps its negative self-check. This was
    always the behaviour and is what shows self-reachability was never exempt
    from compliance -- the old filter suppressed it only where the policy
    GRANTED it, which is the asymmetry the fix removes.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)
_W = "bench/wl_up"
# The FPL sources. Tracked; everything below is derived from them.
_SOURCES = ["%s/%s" % (_W, f) for f in ("roles_and_services.txt", "reach.txt")]

_WIFI = "clients.wifi.uni-potsdam.de"
_DMZ_SERVER = "file.uni-potsdam.de"          # DMZFileServer: one named host


def _sources_present():
    return all(os.path.isfile(os.path.join(_FAVE, f)) for f in _SOURCES)


def _diagonal(csv_path, role):
    """ The role's own cell in the policy matrix, '' when the policy is empty. """
    with open(csv_path) as raw:
        rows = [line.rstrip('\n').split(',') for line in raw]
    column = rows[0].index(role)
    for row in rows[1:]:
        if row and row[0] == role:
            return row[column].strip()
    raise AssertionError("role %s not in the matrix" % role)


def _self_checks(checks, host):
    """ Checks with `host` as both source and probe, positive and negative. """
    out = []
    for check in checks:
        tokens = check.split()
        if ("s=source.%s" % host) in tokens and ("p=probe.%s" % host) in tokens:
            out.append(check)
    return out


@unittest.skipUnless(_sources_present(), "wl_up FPL sources not present")
class TestWlUpPolicyArtifacts(unittest.TestCase):
    """ Regenerate from the FPL sources alone and inspect what comes out. """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="wl_up_policy_")
        tmp = cls._tmp.name
        env = dict(os.environ, PYTHONPATH=_FAVE)

        def run(argv):
            subprocess.run(argv, cwd=_FAVE, check=True, capture_output=True, env=env)

        csv_path = os.path.join(tmp, "reachability.csv")
        roles_path = os.path.join(tmp, "roles.json")
        # Same invocation as test/gen_wl_up_inputs.sh and wl_up/benchmark.py
        # (--strict, Internet role enabled, no suffix).
        run([sys.executable, "../policy_translator/policy_translator.py",
             "--strict", "--csv", "--out", csv_path, "--roles", roles_path]
            + [os.path.join(_FAVE, f) for f in _SOURCES])
        cls.csv_path, cls.roles_path = csv_path, roles_path

        # inventorygen reads the matrix, so it runs against the one just built.
        run([sys.executable, "%s/inventorygen.py" % _W])

        cls.checks_path = os.path.join(tmp, "checks.json")
        cls.reach_path = os.path.join(tmp, "reachable.json")
        run([sys.executable, "bench/reach_csv_to_checks.py",
             "-p", csv_path, "-m", "%s/inventory.json" % _W,
             "--roles", roles_path,
             "-c", cls.checks_path, "--cchecks", os.path.join(tmp, "cchecks.json"),
             "-j", cls.reach_path])

        with open(cls.checks_path) as raw:
            cls.checks = json.load(raw)
        with open(cls.reach_path) as raw:
            cls.reach = json.load(raw)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_subnet_roles_self_rule_produces_a_check(self):
        """ `Wifi <--> Wifi`, the pair the headline used to lose. """
        checks = _self_checks(self.checks, _WIFI)
        self.assertEqual(len(checks), 1, checks)
        self.assertFalse(checks[0].startswith('! '),
                         "the rule GRANTS reachability, so the check is positive")
        self.assertIn(_WIFI, self.reach.get(_WIFI, []),
                      "reachable.json must list the pair the policy asserts")

    def test_the_internet_never_gets_a_self_check(self):
        """ External entity: not in administrative reach, so not answerable. """
        self.assertEqual(_self_checks(self.checks, 'internet'), [])
        self.assertNotIn('internet', self.reach.get('internet', []))

    def test_superrole_expansion_writes_no_member_diagonal(self):
        """ `DMZ <--> DMZ` connects the eight members without granting any of
        them self-reachability: strict mode needs an explicit rule for that,
        and no rule in reach.txt names a DMZ member reaching itself. """
        self.assertEqual(_diagonal(self.csv_path, 'DMZFileServer'), '',
                         "superrole expansion must not fill a member diagonal")
        self.assertNotEqual(_diagonal(self.csv_path, 'Wifi'), '',
                            "the explicit `Wifi <--> Wifi` rule must survive")

    def test_a_single_host_role_gets_a_negative_self_check(self):
        """ With its spurious diagonal gone, a DMZ member is an ordinary empty
        diagonal, and empty diagonals have always produced a must-not-reach
        check. """
        checks = _self_checks(self.checks, _DMZ_SERVER)
        self.assertEqual(len(checks), 1, checks)
        self.assertTrue(checks[0].startswith('! '),
                        "no rule grants it, so the check is negative")
        self.assertNotIn(_DMZ_SERVER, self.reach.get(_DMZ_SERVER, []))

    def test_an_empty_diagonal_still_yields_a_negative_self_check(self):
        """ Pre-existing behaviour, kept: self-reachability was never exempt
        from compliance -- which is why suppressing it only where the policy
        granted it was an asymmetry rather than a convention. """
        negatives = [c for c in self.checks
                     if c.startswith('! ') and _self_checks([c[2:]], 'clients.api.uni-potsdam.de')]
        self.assertTrue(negatives, "expected a must-not-reach self-check")

    def test_the_artifacts_match_the_generated_tree(self):
        """ THE INVARIANT: whatever sits in bench/wl_up/ is what the FPL sources
        produce. Skips when the tree has not been generated
        (test/gen_wl_up_inputs.sh). """
        in_tree = os.path.join(_FAVE, _W, "checks.json")
        if not os.path.isfile(in_tree):
            self.skipTest("bench/wl_up/checks.json not generated")
        with open(in_tree) as raw:
            self.assertEqual(json.load(raw), self.checks,
                             "bench/wl_up/checks.json is not what the FPL sources "
                             "generate -- regenerate with test/gen_wl_up_inputs.sh")
        with open(os.path.join(_FAVE, _W, "reachable.json")) as raw:
            self.assertEqual(json.load(raw), self.reach)


if __name__ == '__main__':
    unittest.main()
