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

""" A generated input reaches a tier, and the gate on it can open (TODO item 36).

Two halves of one defect. They failed independently, and either alone is enough
to leave a differential green without having run.

ONE -- a generator that runs in no tier. `gen_wl_cloud_inputs.sh` was the sixth
of six `gen_wl_*_inputs.sh` and the only one `test.sh` never invoked, so
`bench/wl_cloud/`'s derived model existed only on a machine where someone had
run the script by hand.

TWO -- an availability gate that pre-empts the generation it guards. Both
wl_cloud differentials gated, at IMPORT time, on that DERIVED model, while the
thing that creates it is each class's own `setUpClass`. So the gate could never
open on a clean checkout: inputs missing -> class skips -> `setUpClass` never
runs -> inputs stay missing. Eight tests, collected in every run, executed in
none, and `FAVE_REQUIRE_BACKENDS=1` could only turn that into an error nothing
was able to clear.

THE RULE THIS PINS: an availability gate may name only data a clean checkout
already has. Anything else makes the gate's precondition some other step's side
effect -- at best an ordering dependency between tiers (TODO item 37), at worst,
as here, a cycle.

Pure Python. It reads `test.sh`, imports the two modules for the actual gate
inputs (0.02 s each, no backend), and asks git what a clean checkout contains.
"""

import glob
import importlib
import os
import re
import subprocess
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FAVE = os.path.abspath(os.path.join(_HERE, '..'))
_ROOT = os.path.abspath(os.path.join(_FAVE, '..'))

#: Modules whose class-level availability gate must be satisfiable on a clean
#: checkout. Named rather than discovered: a module belongs here because its
#: `setUpClass` DERIVES what it needs, which is a property of the test, not
#: something a glob can see.
#:
#: SURVEYED 2026-10-01, and these are the only two in `fave/test/`. Plenty of
#: other classes gate on generated inputs -- wl_ifi, wl_i2, wl_stanford, wl_up,
#: the Delta-net workloads -- but the generator that satisfies them is a step in
#: the tier, so the gate waits on something that genuinely runs first. That is
#: an ordering dependency, and only a cycle when the test is also the generator.
#: `test_backend_differential.py` is the near miss: it carries a `GENERATOR`
#: attribute, but uses it only to name the script in the skip message.
_SELF_DERIVING = (
    'test_apkeep_cloud_differential',
    'test_ad6_cloud_differential',
)


def _tracked(paths):
    """ Those of `paths` (relative to `fave/`) that git has under version
    control -- which is exactly "present in a clean checkout". """
    proc = subprocess.run(
        ['git', '-C', _FAVE, 'ls-files', '--'] + list(paths),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise unittest.SkipTest(
            "not a git work tree, so a clean checkout cannot be consulted")
    return set(proc.stdout.decode().split('\n')) - {''}


class TestEveryInputGeneratorRunsInATier(unittest.TestCase):
    """ A generator nothing calls is a workload nothing tests. """

    def test_no_generator_is_orphaned(self):
        generators = sorted(os.path.basename(p) for p in
                            glob.glob(os.path.join(_HERE, 'gen_*_inputs.sh')))
        self.assertTrue(
            generators, "no gen_*_inputs.sh found -- this test's glob is wrong")

        with open(os.path.join(_ROOT, 'test.sh')) as raw:
            runner = raw.read()

        # INVOKED, not merely mentioned: test.sh's header names the generators
        # as a glob when it explains why PYTHON is exported, and a comment is
        # not a tier. So the match is a `bash .../<name>` line.
        orphaned = [g for g in generators
                    if not re.search(r'^\s*bash\s+\S*%s' % re.escape(g),
                                     runner, re.MULTILINE)]
        self.assertEqual(
            orphaned, [],
            "these generators are invoked by no tier in test.sh, so the tests "
            "that consume their output can only ever skip: %s" % orphaned)


class TestASelfDerivingGateOpensOnACleanCheckout(unittest.TestCase):
    """ The gate names raw data; `setUpClass` derives the rest. """

    def test_every_gated_path_is_tracked(self):
        for name in _SELF_DERIVING:
            with self.subTest(module=name):
                gated = list(importlib.import_module('test.%s' % name)._RAW)

                # `all(... for f in [])` is True, so an empty gate is one that
                # always opens -- vacuous rather than wrong, and invisible.
                self.assertTrue(
                    gated, "%s gates on no file at all, so the gate is "
                           "vacuously open" % name)

                untracked = sorted(set(gated) - _tracked(gated))
                self.assertEqual(
                    untracked, [],
                    "%s gates on files a clean checkout does not have: %s. If "
                    "its own setUpClass is what generates them, the gate can "
                    "never open -- condition on the raw data instead "
                    "(TODO item 36)." % (name, untracked))


if __name__ == '__main__':
    unittest.main()
