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

""" wl_ifi's STATELESS policy variant (APKEEP_BACKEND.md, owner proposal
2026-09-18).

wl_ifi pairs a policy that asks for stateful reachability (`<->>`) with a model
that cannot express it: its Cisco ACLs are state-blind, and `related` occurs
nowhere in topology.json/routes.json/policies.json -- only in the queries. The
honest consequence is that the 27 `related:0` "must not reach" checks are
VIOLATED, by NetPlumber and APKeep alike, and that is the benchmark's real
oracle.

That makes wl_ifi a poor regression gate (a nonzero expected-violation set) and
a poor discriminator (a tool that silently DROPS the condition scores exactly
like one that honours it, because on a state-blind model conditioning cannot
change reachability).

The variant replaces `<->>` with `<-->` -- "statefully" with "bidirectionally",
both already in the FPL grammar (`policy_translator/fpl_grammar.py:133`). The
policy then asks only for what the model can express, and a correct tool must
report ZERO violations. Running both configurations exercises a tool's ability
to process stateful AND stateless policies, and separates a tool that REFUSES a
condition it cannot honour (ad6) from one that answers anyway.

These tests are pure data checks on the tracked policy and matrix; the
end-to-end zero-violation gate lives in the integration tier.
"""

import csv
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_W = os.path.join(os.path.dirname(_HERE), "bench", "wl_ifi")

# The translator CONCATENATES its positional files and parses the result, so
# both carry policy text and both have to change. wl_ifi's `roles_and_services`
# file holds its own copy of the same four rules (lines 172-181) -- editing
# `reach.txt` alone changes nothing at all, which is what
# `test_the_policy_block_is_duplicated` pins.
_STATEFUL_POLICIES = [os.path.join(_W, f)
                      for f in ("roles_and_services.txt", "reach.txt")]
_STATELESS_POLICIES = [os.path.join(_W, f)
                       for f in ("roles_and_services_stateless.txt",
                                 "reach_stateless.txt")]
_STATEFUL_CSV = os.path.join(_W, "reachability.csv")
_STATELESS_CSV = os.path.join(_W, "reachability_stateless.csv")


def _cells(path):
    """ {(row, column): flag} for every non-empty cell of a policy matrix. """
    with open(path) as raw:
        rows = list(csv.reader(raw))
    header = rows[0][1:]
    out = {}
    for row in rows[1:]:
        if not row:
            continue
        for col, flag in zip(header, row[1:]):
            if flag.strip():
                out[(row[0], col)] = flag.strip()
    return out


class TestStatelessPolicySource(unittest.TestCase):

    def test_both_variant_files_exist(self):
        for path in _STATELESS_POLICIES:
            with self.subTest(path=os.path.basename(path)):
                self.assertTrue(os.path.isfile(path), "%s is missing" % path)

    def test_each_differs_from_its_original_only_in_the_operator(self):
        """ Same roles, same services, same rules, same order -- otherwise the
        two configurations would differ in more than the question asked. """
        for stateful, stateless in zip(_STATEFUL_POLICIES, _STATELESS_POLICIES):
            with self.subTest(path=os.path.basename(stateful)):
                self.assertEqual(open(stateful).read().replace('<->>', '<-->'),
                                 open(stateless).read())

    def test_the_variant_asks_no_stateful_question(self):
        for path in _STATELESS_POLICIES:
            with self.subTest(path=os.path.basename(path)):
                self.assertNotIn('<->>', open(path).read())

    def test_the_original_still_does(self):
        """ The variant is an ADDITION. wl_ifi's stateful configuration is the
        one that documents the policy/model mismatch, and it stays. """
        self.assertTrue(any('<->>' in open(p).read() for p in _STATEFUL_POLICIES))

    def test_the_policy_block_is_duplicated_across_both_files(self):
        """ Found while building the variant, and pinned because it wastes the
        next person's afternoon: `reach.txt` is NOT the source of wl_ifi's
        policy matrix. `roles_and_services.txt` carries the same four rules, the
        translator concatenates both positional files before parsing, and so
        deleting a rule from `reach.txt` alone leaves the generated matrix
        byte-identical. Any change to wl_ifi's policy must touch both files --
        as the variant does. """
        rules = lambda t: sorted(l.split('#')[0].strip() for l in t.splitlines()
                                 if '<->>' in l or '<-->' in l)
        roles_rules, reach_rules = (rules(open(p).read()) for p in _STATEFUL_POLICIES)
        self.assertEqual(roles_rules, reach_rules,
                         "if these ever diverge, the duplication has become a "
                         "conflict and the concatenation order decides silently")


class TestStatelessPolicyMatrix(unittest.TestCase):
    """ The matrix is what `bench/reach_csv_to_checks.py` actually reads: an
    `X` cell emits one unconditioned "must reach" check, an `(X)` cell emits
    the stateful pair (`related:1` must-reach + `related:0` must-not-reach). """

    def test_the_matrix_exists(self):
        self.assertTrue(os.path.isfile(_STATELESS_CSV),
                        "%s is missing" % _STATELESS_CSV)

    def test_no_cell_is_stateful(self):
        self.assertEqual(
            sorted(k for k, v in _cells(_STATELESS_CSV).items() if v == '(X)'),
            [])

    def test_every_stateful_cell_became_a_plain_one(self):
        """ The semantic claim of the whole variant, checked cell by cell:
        nothing gained, nothing lost, `(X)` -> `X`. """
        stateful = _cells(_STATEFUL_CSV)
        stateless = _cells(_STATELESS_CSV)
        self.assertEqual(set(stateful), set(stateless),
                         "the two matrices must cover the same role pairs")
        expected = {k: ('X' if v == '(X)' else v) for k, v in stateful.items()}
        self.assertEqual(stateless, expected)

    def test_the_original_matrix_has_the_stateful_cells(self):
        self.assertTrue(
            any(v == '(X)' for v in _cells(_STATEFUL_CSV).values()),
            "wl_ifi's stateful configuration must still carry (X) cells")


class TestGeneratedCheckSets(unittest.TestCase):
    """ What `bench/reach_csv_to_checks.py` makes of each matrix. Derived here
    from the TRACKED csv files into a temp dir, so this needs none of the
    generated benchmark inputs and stays in the fast tier. """

    @classmethod
    def setUpClass(cls):
        import json
        import subprocess
        import sys
        import tempfile

        fave = os.path.dirname(_HERE)
        cls._tmp = tempfile.TemporaryDirectory(prefix="wl_ifi_checks_")
        cls.sets = {}
        for name, csv_path in (("stateful", _STATEFUL_CSV),
                               ("stateless", _STATELESS_CSV)):
            out = os.path.join(cls._tmp.name, name)
            subprocess.run(
                [sys.executable, "bench/reach_csv_to_checks.py",
                 "-s", ".ifi", "-p", csv_path, "-m", "bench/empty.json",
                 "-c", out + ".checks.json", "--cchecks", out + ".cchecks.json",
                 "-j", out + ".reach.json"],
                cwd=fave, check=True, capture_output=True,
                env=dict(os.environ, PYTHONPATH=fave))
            with open(out + ".cchecks.json") as raw:
                cchecks = json.load(raw)
            with open(out + ".reach.json") as raw:
                reach = json.load(raw)
            flat = [(outer, inner, valid, tuple(cond or ()))
                    for outer, entries in cchecks.items()
                    for inner, valid, cond in entries]
            cls.sets[name] = {"checks": flat, "reach": reach}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_stateful_set_is_the_one_measured(self):
        """ 299 checks, 54 of them conditioned -- 27 `related:1` must-reach and
        27 `related:0` must-not-reach. The 27 are the violations both
        NetPlumber and APKeep report. """
        flat = self.sets["stateful"]["checks"]
        self.assertEqual(len(flat), 299)
        conditioned = [c for c in flat if c[3]]
        self.assertEqual(len(conditioned), 54)
        self.assertEqual(
            sorted({c[3] for c in conditioned}),
            [('related:0',), ('related:1',)])

    def test_the_stateless_set_asks_nothing_about_state(self):
        flat = self.sets["stateless"]["checks"]
        self.assertEqual([c for c in flat if c[3]], [])

    def test_the_stateless_set_replaces_each_pair_with_one_plain_check(self):
        """ 299 - 54 + 27 = 272: the 27 stateful PAIRS collapse to 27 plain
        must-reach checks, and nothing else moves. """
        self.assertEqual(len(self.sets["stateless"]["checks"]), 272)

    def test_both_expect_the_same_reachability(self):
        """ The variant changes only what is ASKED, never what the network is
        expected to do -- so the reachability oracle is untouched and the two
        configurations remain comparable. """
        self.assertEqual(self.sets["stateful"]["reach"],
                         self.sets["stateless"]["reach"])


if __name__ == '__main__':
    unittest.main()
