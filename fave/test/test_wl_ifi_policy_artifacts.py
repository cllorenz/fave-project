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

""" wl_ifi's compliance artifacts derive from the FPL inventory and policy, and
from nothing else -- and a LOOSE matrix's filled diagonal produces no
self-check.

The sibling of test_wl_up_policy_artifacts.py, and wl_ifi needs it for a reason
wl_up does not: wl_ifi has TWO generation paths. `bench/wl_ifi/benchmark.py`
regenerates the policy matrix from the FPL sources, while
`test/gen_wl_ifi_inputs.sh` uses the committed `reachability.csv`. Both then run
`reach_csv_to_checks`. Nothing checked that they agree, and `checks.json` /
`reachable.json` are gitignored, so whichever ran last silently defined the
ground truth four ad6 gates and two APKeep gates are asserted against. Running
the smoke tier could therefore turn the NEXT fast tier red, with failures that
said nothing about the backend under test (TODO.md item 14).

THE REGRESSION THIS PINS. wl_ifi runs LOOSE -- no `--strict` -- and loose mode
injects a diagonal for every atomic role: all 17 of wl_ifi's roles have `X` on
their own cell although no rule in `reach.txt` names a role reaching itself.
A filled diagonal there is not evidence of anything, so `keep_self` in
`bench/reach_csv_to_checks.py` requires `args.strict` before it will emit a
self-check. When that gate was missing, wl_ifi picked up 16 POSITIVE
self-checks asserting reachability nobody wrote -- 299 checks became 315 -- and
the four red gates that followed were mistaken (by me) for a stale test
expectation rather than a real regression. See APKEEP_BACKEND.md Sec. 10.

So the invariant has two halves, and the second is the one with teeth:

  * whatever sits in `bench/wl_ifi/` is what the FPL sources produce, by BOTH
    paths; and
  * a loose matrix's filled diagonal yields NO self-check, positive or negative.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)
_W = "bench/wl_ifi"

#: The FPL sources of each variant: (inventory, policy, tracked matrix).
_VARIANTS = {
    'stateful': (
        "%s/roles_and_services.txt" % _W,
        "%s/reach.txt" % _W,
        "%s/reachability.csv" % _W,
    ),
    'stateless': (
        "%s/roles_and_services_stateless.txt" % _W,
        "%s/reach_stateless.txt" % _W,
        "%s/reachability_stateless.csv" % _W,
    ),
}

#: Derived artifacts per variant, as `gen_wl_ifi_inputs.sh` names them.
_DERIVED = {
    'stateful': ("checks.json", "cchecks.json", "reachable.json"),
    'stateless': ("checks_stateless.json", "cchecks_stateless.json",
                  "reachable_stateless.json"),
}


def _sources_present():
    return all(
        os.path.isfile(os.path.join(_FAVE, f))
        for paths in _VARIANTS.values() for f in paths
    )


def _run(argv):
    subprocess.run(argv, cwd=_FAVE, check=True, capture_output=True,
                   env=dict(os.environ, PYTHONPATH=_FAVE))


def _self_checks(checks):
    """ Every check whose source and probe are the same role. """
    out = []
    for check in checks:
        tokens = check.split()
        sources = [t[len('s=source.'):] for t in tokens if t.startswith('s=source.')]
        probes = [t[len('p=probe.'):] for t in tokens if t.startswith('p=probe.')]
        if sources and probes and sources[0] == probes[0]:
            out.append(check)
    return out


def _diagonals(csv_path):
    """ {role: its own cell} for every role that has a row and a column. """
    with open(csv_path) as raw:
        rows = list(csv.reader(raw))
    header = rows[0]
    return {
        row[0]: row[header.index(row[0])].strip()
        for row in rows[1:] if row and row[0] in header
    }


@unittest.skipUnless(_sources_present(), "wl_ifi FPL sources not present")
class TestWlIfiPolicyArtifacts(unittest.TestCase):
    """ Regenerate from the FPL sources alone and inspect what comes out. """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="wl_ifi_policy_")
        tmp = cls._tmp.name

        cls.matrices = {}
        cls.artifacts = {}
        for variant, (inventory, policy, _tracked) in _VARIANTS.items():
            matrix = os.path.join(tmp, "%s.csv" % variant)
            roles = os.path.join(tmp, "%s-roles.json" % variant)
            # wl_ifi's own invocation: LOOSE (no --strict), Internet enabled,
            # suffix `.ifi`. GenericBenchmark._generate_policy_matrix builds
            # exactly this for a benchmark constructed without strict=True.
            _run([sys.executable, "../policy_translator/policy_translator.py",
                  "--roles", roles, "--csv", "--out", matrix,
                  os.path.join(_FAVE, inventory), os.path.join(_FAVE, policy)])
            cls.matrices[variant] = matrix

            # Both callers' forms of the derivation. The benchmark passes
            # --roles and the shell generator does not; with no --strict the
            # roles dump cannot produce a self-check either way, so the two
            # MUST agree -- and `test_the_two_generation_paths_agree` is what
            # keeps that true rather than incidental.
            produced = {}
            for label, extra in (('with_roles', ["--roles", roles]),
                                 ('without_roles', [])):
                out = {name: os.path.join(tmp, "%s-%s-%s" % (variant, label, name))
                       for name in _DERIVED[variant]}
                checks, cchecks, reach = _DERIVED[variant]
                _run([sys.executable, "bench/reach_csv_to_checks.py",
                      "-s", ".ifi", "-p", matrix, "-m", "bench/empty.json",
                      "-c", out[checks], "--cchecks", out[cchecks],
                      "-j", out[reach]] + extra)
                produced[label] = {
                    name: json.load(open(path)) for name, path in out.items()
                }
            cls.artifacts[variant] = produced

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- the sources really are the sources ---------------------------------

    def test_the_tracked_matrices_are_what_the_fpl_sources_produce(self):
        """ wl_ifi's matrices are TRACKED inputs (there is a .gitignore
        exemption for them), and the benchmark REGENERATES them. If the two
        ever part company, the benchmark and the shell generator stop
        describing the same workload -- which is precisely how the 299/315
        split went unnoticed. """
        for variant, (_inv, _pol, tracked) in _VARIANTS.items():
            with open(os.path.join(_FAVE, tracked)) as raw:
                committed = list(csv.reader(raw))
            with open(self.matrices[variant]) as raw:
                regenerated = list(csv.reader(raw))
            self.assertEqual(
                committed, regenerated,
                "%s is not what its FPL sources produce -- regenerate it, or "
                "the benchmark and gen_wl_ifi_inputs.sh will disagree" % tracked)

    # -- the loose-mode invariant, which is the one with teeth --------------

    def test_loose_mode_fills_every_diagonal(self):
        """ The precondition of the next test: there IS a filled diagonal to be
        misread. No rule in reach.txt names a role reaching itself. """
        diagonals = _diagonals(self.matrices['stateful'])

        self.assertEqual(len(diagonals), 17)
        self.assertEqual(set(diagonals.values()), {'X'},
                         "loose mode injects a diagonal for every atomic role")

    def test_a_filled_loose_diagonal_produces_no_self_check(self):
        """ THE REGRESSION. 16 positive self-checks once appeared here,
        asserting reachability nobody wrote, and took four ad6 gates red with
        them. `keep_self` requires `--strict`; wl_ifi does not pass it. """
        for variant in _VARIANTS:
            for label, produced in self.artifacts[variant].items():
                checks = produced[_DERIVED[variant][0]]
                self.assertEqual(
                    _self_checks(checks), [],
                    "%s/%s: a loose matrix must yield no self-check, positive "
                    "or negative" % (variant, label))

    def test_no_role_reaches_itself_in_the_oracle(self):
        """ The same invariant read off `reachable.json`, which is what the ad6
        and APKeep reachability gates actually compare against. """
        for variant in _VARIANTS:
            reach = self.artifacts[variant]['with_roles'][_DERIVED[variant][2]]
            self_pairs = sorted(role for role, peers in reach.items()
                                if role in peers)
            self.assertEqual(self_pairs, [], variant)

    def test_the_two_generation_paths_agree(self):
        """ The benchmark passes `--roles`, `gen_wl_ifi_inputs.sh` does not.
        Without `--strict` that cannot change the outcome -- but it did once,
        and nothing said so. """
        for variant in _VARIANTS:
            produced = self.artifacts[variant]
            self.assertEqual(
                produced['with_roles'], produced['without_roles'],
                "%s: --roles changed the artifacts, so the benchmark and the "
                "shell generator no longer describe the same workload" % variant)

    # -- and the tree matches ------------------------------------------------

    def test_the_artifacts_match_the_generated_tree(self):
        """ THE INVARIANT: whatever sits in bench/wl_ifi/ is what the FPL
        sources produce. Skips when the tree has not been generated
        (test/gen_wl_ifi_inputs.sh). """
        for variant in _VARIANTS:
            for name in _DERIVED[variant]:
                in_tree = os.path.join(_FAVE, _W, name)
                if not os.path.isfile(in_tree):
                    self.skipTest("%s/%s not generated" % (_W, name))
                with open(in_tree) as raw:
                    self.assertEqual(
                        json.load(raw),
                        self.artifacts[variant]['without_roles'][name],
                        "%s/%s is not what the FPL sources generate -- "
                        "regenerate with test/gen_wl_ifi_inputs.sh" % (_W, name))


if __name__ == '__main__':
    unittest.main()
