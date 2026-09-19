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

""" wl_example's compliance artifacts derive from the FPL inventory and policy,
and from nothing else -- and wl_example is the workload that carries the SERVICE
vocabulary, so it is where service-conditional derivation is pinned.

The third of the family, after test_wl_up_policy_artifacts.py (self-rules under
`--strict`) and test_wl_ifi_policy_artifacts.py (a loose diagonal must yield no
self-check). wl_example is the smallest of the three and the only one whose
matrix is entirely GENERATED -- `reachability.csv`, `inventory.json`,
`checks.json`, `cchecks.json` and `reachable.json` are all gitignored, and
there is no `test/gen_wl_example_inputs.sh`: `bench/wl_example/benchmark.py` is
the sole producer. Nothing else may quietly become a source of truth for them.

WHAT ONLY THIS WORKLOAD HAS. Every other matrix in the tree is plain `X`/`(X)`
reachability. wl_example's has three service conditions and the tree's ONE
alternative:

    ,Internet,Office,WebServer
    Internet,X,(X),(protocol:tcp;port:80)
    Office,X,X,(protocol:tcp;port:80|protocol:tcp;port:22)
    WebServer,(X),(X),X

That single `|` is load-bearing well outside this workload. Under
`--complement` the cell's negation is `!(80 or 22)` = `!80 and !22` -- two
negated constraints on ONE field, in one check, which is the exact shape
`netplumber/adapter.py`'s `_meet_all` exists for. Without the intersection the
second negation overwrites the first, and the survivor `!22` is a strict
SUPERSET of `!80 and !22`: permitted port 80 then fires a must-not-reach check,
a FALSE VIOLATION rather than a silent weakening.
`test_adapter_negation_intersection.py` says of that shape "`wl_example` has one
today" -- prose, asserted nowhere until here. If the policy ever loses its
alternative, that unit test quietly becomes a fixture about nothing, and this is
what says so.

THE SECOND HALF, shared with wl_ifi: wl_example runs LOOSE -- no `--strict` --
so every atomic role gets an `X` on its own cell although no rule in `reach.txt`
names a role reaching itself. A filled diagonal there is not evidence of
anything, and must produce no self-check, positive or negative (TODO.md item 14,
APKEEP_BACKEND.md Sec. 10).
"""

import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.dirname(_HERE)
_W = "bench/wl_example"

#: The FPL sources. Tracked; everything below is derived from them.
_SOURCES = ["%s/%s" % (_W, f) for f in ("roles_and_services.txt", "reach.txt")]

#: The derived artifacts the benchmark leaves in the tree.
_DERIVED = ("checks.json", "cchecks.json", "reachable.json")

#: role -> the model node standing for it. `topogen.py` instantiates exactly
#: these three, and `inventorygen.py` hardcodes the mapping. The `hosts` names
#: in `roles_and_services.txt` are DNS names with no device behind them, which
#: is the OPPOSITE of wl_up, where the `hosts` names ARE the node names.
_NODES = {'Internet': 'internet', 'WebServer': 'dmz', 'Office': 'office'}


def _sources_present():
    return all(os.path.isfile(os.path.join(_FAVE, f)) for f in _SOURCES)


def _run(argv, cwd=_FAVE):
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True,
                   env=dict(os.environ, PYTHONPATH=_FAVE))


def _load(path):
    with open(path) as raw:
        return json.load(raw)


def _matrix(csv_path):
    with open(csv_path) as raw:
        return [[cell.strip() for cell in row] for row in csv.reader(raw)]


def _cells(csv_path):
    """ {(row role, column role): cell} over the whole matrix. """
    rows = _matrix(csv_path)
    header = rows[0]
    return {(row[0], header[i]): cell
            for row in rows[1:] if row
            for i, cell in enumerate(row) if i}


def _tokens(check):
    return check[2:].split() if check.startswith('! ') else check.split()


def _endpoints(check):
    """ (source node, probe node) of a check, or (None, None). """
    sources = [t[len('s=source.'):] for t in _tokens(check)
               if t.startswith('s=source.')]
    probes = [t[len('p=probe.'):] for t in _tokens(check)
              if t.startswith('p=probe.')]
    return (sources[0] if sources else None, probes[0] if probes else None)


def _self_checks(checks):
    """ Every check whose source and probe are the same node. """
    return [c for c in checks
            if None not in _endpoints(c) and _endpoints(c)[0] == _endpoints(c)[1]]


def _negated_fields(check):
    """ ['port', 'port'] for a check carrying `f=!port:22 f=!port:80`. """
    return [t[len('f=!'):].split(':', 1)[0]
            for t in _tokens(check) if t.startswith('f=!')]


@unittest.skipUnless(_sources_present(), "wl_example FPL sources not present")
class TestWlExamplePolicyArtifacts(unittest.TestCase):
    """ Regenerate from the FPL sources alone and inspect what comes out. """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="wl_example_policy_")
        tmp = cls._tmp.name

        cls.csv_path = os.path.join(tmp, "reachability.csv")
        roles_path = os.path.join(tmp, "roles.json")
        # wl_example's own invocation: LOOSE (no --strict), Internet enabled,
        # no suffix. GenericBenchmark._generate_policy_matrix builds exactly
        # this for a benchmark constructed without strict=True.
        _run([sys.executable, "../policy_translator/policy_translator.py",
              "--roles", roles_path, "--csv", "--out", cls.csv_path]
             + [os.path.join(_FAVE, f) for f in _SOURCES])

        # `inventorygen.py` hardcodes `bench/wl_example/...`, so it is given a
        # throwaway tree holding the tracked source and the matrix JUST built.
        # Running it in place would instead validate against -- and overwrite
        # -- the real one, which is the coupling this test exists to rule out.
        sandbox = os.path.join(tmp, _W)
        os.makedirs(sandbox)
        shutil.copy(os.path.join(_FAVE, _SOURCES[0]),
                    os.path.join(sandbox, "roles_and_services.txt"))
        shutil.copy(cls.csv_path, os.path.join(sandbox, "reachability.csv"))
        _run([sys.executable, os.path.join(_FAVE, _W, "inventorygen.py")], cwd=tmp)
        cls.inventory_path = os.path.join(sandbox, "inventory.json")
        cls.inventory = _load(cls.inventory_path)

        # Both derivations: the benchmark's (no --complement) and the one the
        # complement work added. Only the first defines the tree.
        cls.produced = {}
        for label, extra in (('plain', []), ('complement', ["--complement"])):
            out = {name: os.path.join(tmp, "%s-%s" % (label, name))
                   for name in _DERIVED}
            _run([sys.executable, "bench/reach_csv_to_checks.py",
                  "-p", cls.csv_path, "-m", cls.inventory_path,
                  "--roles", roles_path,
                  "-c", out["checks.json"], "--cchecks", out["cchecks.json"],
                  "-j", out["reachable.json"]] + extra)
            cls.produced[label] = {
                name: _load(path) for name, path in out.items()
            }

        cls.checks = cls.produced['plain']["checks.json"]
        cls.reach = cls.produced['plain']["reachable.json"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- the service vocabulary, which only this workload exercises ----------

    def test_the_matrix_carries_the_tree_s_only_service_alternative(self):
        """ `AllClients <->> WebServer.HTTP` and `Office <->> WebServer.SSH`
        meet in ONE cell, and a role offering two permitted services is the
        only way to write a `|` into a matrix. Guards the premise
        test_adapter_negation_intersection.py states as prose. """
        cell = _cells(self.csv_path)[('Office', 'WebServer')]

        self.assertEqual(cell, "(protocol:tcp;port:80|protocol:tcp;port:22)")
        self.assertEqual(
            [c for c in _cells(self.csv_path).values() if '|' in c], [cell],
            "wl_example must have exactly one alternative cell")

        others = [p for p in sorted(glob.glob("%s/bench/*/reachability*.csv" % _FAVE))
                  if os.path.basename(os.path.dirname(p)) != 'wl_example'
                  and any('|' in c for c in _cells(p).values())]
        self.assertEqual(
            others, [],
            "another workload grew an alternative -- wl_example is no longer "
            "the sole source of the two-negations-on-one-field shape, and "
            "test_adapter_negation_intersection.py's premise needs rewording")

    def test_an_alternative_cell_becomes_two_separate_positive_checks(self):
        """ Two permitted services are a DISJUNCTION, so they cannot share a
        check: `port:80 && port:22` is unsatisfiable and would assert nothing.
        """
        alternatives = [c for c in self.checks
                        if _endpoints(c) == ('office', 'dmz')]

        self.assertEqual(alternatives, [
            "s=source.office && EF p=probe.dmz && f=related:0 "
            "&& f=protocol:tcp && f=port:80",
            "s=source.office && EF p=probe.dmz && f=related:0 "
            "&& f=protocol:tcp && f=port:22",
        ])

    def test_the_complement_negates_one_field_twice_and_only_here(self):
        """ THE SHAPE `_meet_all` EXISTS FOR. `!(80 or 22)` is `!80 and !22`:
        two negated constraints on one field, in one check. Without the
        intersection in `netplumber/adapter.py` the survivor `!22` is a strict
        superset, so permitted port 80 fires this must-not-reach check -- a
        false violation, not a silent weakening. """
        collisions = [c for c in self.produced['complement']["checks.json"]
                      if len(_negated_fields(c)) != len(set(_negated_fields(c)))]

        self.assertEqual(len(collisions), 1, collisions)
        check = collisions[0]
        self.assertTrue(check.startswith('! '), "the complement is must-not-reach")
        self.assertEqual(_endpoints(check), ('office', 'dmz'))
        self.assertEqual(_negated_fields(check), ['port', 'port'])
        self.assertIn('f=!port:22', check)
        self.assertIn('f=!port:80', check)

    def test_the_benchmark_s_own_derivation_emits_no_complement(self):
        """ `--complement` is opt-in, and wl_example's benchmark does not pass
        it -- so the tree holds the positive checks only. The complement half
        of a conditional permission is a separate, sharper question (see
        test_complement_checks.py); this pins which of the two the archived
        wl_example results were measured under. """
        self.assertEqual(len(self.checks), 10)
        self.assertEqual(
            [c for c in self.checks if _negated_fields(c)], [],
            "no field-level negation without --complement")
        self.assertEqual(len(self.produced['complement']["checks.json"]), 14)

    def test_the_stateful_operator_pairs_every_backflow_cell(self):
        """ `<->>` grants the reverse direction only for RELATED traffic, which
        the matrix writes as a parenthesised cell. Each one must produce both
        halves: `related:1` may pass, `related:0` may not. A cell yielding only
        the positive would assert nothing about new connections -- the whole
        point of the operator. """
        backflow = sorted(pair for pair, cell in _cells(self.csv_path).items()
                          if cell == '(X)')
        self.assertEqual(backflow, [('Internet', 'Office'),
                                    ('WebServer', 'Internet'),
                                    ('WebServer', 'Office')])

        for source, target in backflow:
            endpoints = (_NODES[source], _NODES[target])
            got = sorted(c for c in self.checks if _endpoints(c) == endpoints)
            self.assertEqual(got, sorted([
                "s=source.%s && EF p=probe.%s && f=related:1" % endpoints,
                "! s=source.%s && EF p=probe.%s && f=related:0" % endpoints,
            ]), "%s -> %s" % (source, target))

    # -- the loose-mode invariant, shared with wl_ifi ------------------------

    def test_loose_mode_fills_every_diagonal(self):
        """ The precondition of the next test: there IS a filled diagonal to be
        misread. No rule in reach.txt names a role reaching itself. """
        diagonals = {role: cell for (role, column), cell
                     in _cells(self.csv_path).items() if role == column}

        self.assertEqual(sorted(diagonals), ['Internet', 'Office', 'WebServer'])
        self.assertEqual(set(diagonals.values()), {'X'},
                         "loose mode injects a diagonal for every atomic role")

    def test_a_filled_loose_diagonal_produces_no_self_check(self):
        """ Positive self-checks asserting reachability nobody wrote once took
        four ad6 gates red on wl_ifi. `keep_self` in reach_csv_to_checks.py
        requires `--strict`; wl_example does not pass it. """
        for label, produced in self.produced.items():
            self.assertEqual(
                _self_checks(produced["checks.json"]), [],
                "%s: a loose matrix must yield no self-check, positive or "
                "negative" % label)

    def test_no_role_reaches_itself_in_the_oracle(self):
        """ The same invariant read off `reachable.json`, which is what the
        reachability gates compare against. """
        self.assertEqual(
            sorted(node for node, peers in self.reach.items() if node in peers),
            [])

    # -- the superrole and the inventory -------------------------------------

    def test_the_superrole_is_expanded_away_and_grants_both_members(self):
        """ `AllClients` includes Internet and Office. It is not a role a
        packet can be, so it must not reach the matrix -- but the HTTP cell it
        grants must reach BOTH members. """
        rows = _matrix(self.csv_path)

        self.assertNotIn('AllClients', rows[0])
        cells = _cells(self.csv_path)
        self.assertIn('port:80', cells[('Internet', 'WebServer')])
        self.assertIn('port:80', cells[('Office', 'WebServer')])

    def test_every_check_names_a_node_the_topology_instantiates(self):
        """ `roles_and_services.txt` gives Office and WebServer `hosts` lists
        of DNS names, and `topogen.py` instantiates no device for either. A
        check naming one would be unfalsifiable: no source generates it and no
        probe observes it, so it can only ever come back unreachable.

        WHAT MAKES THIS REACHABLE AS A MISTAKE. `inventorygen.py` extends each
        role with its `hosts` list on seeing a line whose first token is `def`
        -- but FPL's grammar accepts `define`, `def`, `describe` and `desc`
        interchangeably (policy_translator/fpl_grammar.py:73), and
        wl_example's source is written with `describe`. So the extension never
        fires here, and the hardcoded mapping is what survives.

        That is a coincidence, not a design, and the two halves of it point
        opposite ways. wl_up and wl_ifi write `def`, their extension DOES
        fire, and it must: their `hosts` names are their model node names.
        wl_example's are decorative. Normalising this source to its siblings'
        `def` style -- a cosmetic edit the grammar says is meaningless --
        silently takes wl_example from 10 checks to 32, of which 22 name
        sources and probes that do not exist, including WebServer's two
        "hosts" cross-checking each other. This test is what says so. """
        named = set()
        for check in self.checks:
            named.update(e for e in _endpoints(check) if e)

        self.assertEqual(named, set(_NODES.values()))
        self.assertEqual(
            {role: self.inventory[role] for role in _NODES},
            {role: [node] for role, node in _NODES.items()},
            "the inventory must map each matrix role to its one model node")

    # -- and the tree matches -------------------------------------------------

    def test_the_artifacts_match_the_generated_tree(self):
        """ THE INVARIANT: whatever sits in bench/wl_example/ is what the FPL
        sources produce. Everything there is gitignored and `benchmark.py` is
        its only producer, so a hand-edit would survive until the next run.
        Skips when the tree has not been generated. """
        in_tree = os.path.join(_FAVE, _W, "reachability.csv")
        if not os.path.isfile(in_tree):
            self.skipTest("%s/reachability.csv not generated" % _W)
        self.assertEqual(
            _matrix(in_tree), _matrix(self.csv_path),
            "%s/reachability.csv is not what its FPL sources produce" % _W)

        for name in _DERIVED:
            in_tree = os.path.join(_FAVE, _W, name)
            if not os.path.isfile(in_tree):
                self.skipTest("%s/%s not generated" % (_W, name))
            with open(in_tree) as raw:
                self.assertEqual(
                    json.load(raw), self.produced['plain'][name],
                    "%s/%s is not what the FPL sources generate -- regenerate "
                    "by running bench/wl_example/benchmark.py" % (_W, name))


if __name__ == '__main__':
    unittest.main()
