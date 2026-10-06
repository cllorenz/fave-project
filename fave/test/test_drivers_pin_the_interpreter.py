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

""" ONE INTERPRETER PER MEASUREMENT, enforced on every driver that spawns one.

Every shell script in this tree opens with `PYTHON="${PYTHON:-python3}"`, so a
driver that launches one without exporting `PYTHON` runs that half of its
measurement on the SYSTEM interpreter. In a venv checkout the result is
`ModuleNotFoundError: No module named 'filelock'`, which arrives from
`scripts/start_aggr.sh` four frames away from anything that names an
interpreter -- `generic_benchmark` reports it as "could not connect to fave".

It has cost two runs. `bench/cell_run.py` learned it and wrote the reason down;
`bench/cloud_bdd_measure.py` applies it. `bench/deltanet/eval/` did neither, and
phase B of the V5 campaign died 0.1 s into its first generation step on
2026-10-06, recording `status: error` at k=30 -- an ENVIRONMENT failure that
`MEASUREMENT_RUN_PLAN.md` §8.1 says must not be read as a result about the
engine.

So this is a guard over the SET of drivers rather than a test of one: the next
driver to spawn a script is the one that matters.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'bench', 'deltanet', 'eval'))

from bench import cell_run                                   # noqa: E402

#: Every driver that launches a subprocess for a MEASURED run. A new one
#: belongs here; that is the point of listing them rather than testing one.
_DRIVERS = (
    'bench/cell_run.py',
    'bench/cloud_bdd_measure.py',
    'bench/deltanet/eval/engine_run.py',
    'bench/deltanet/eval/berkeley_drill.py',
)


def _fave_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(cell_run.__file__)))


class TestEveryDriverPinsTheInterpreter(unittest.TestCase):

    def test_each_one_exports_PYTHON(self):
        for driver in _DRIVERS:
            with self.subTest(driver=driver):
                with open(os.path.join(_fave_dir(), driver)) as handle:
                    source = handle.read()
                self.assertIn(
                    'PYTHON', source,
                    "%s spawns a measured run and must export PYTHON, or the "
                    "aggregator starts on the system interpreter" % driver)
                self.assertTrue(
                    "PYTHON': sys.executable" in source
                    or 'PYTHON=sys.executable' in source,
                    "%s sets PYTHON to something other than sys.executable; "
                    "the point is ONE interpreter throughout" % driver)

    def test_cell_run_really_puts_it_in_the_environment(self):
        """ The source check above cannot tell a comment from an assignment, so
        the one driver whose environment is returnable is checked for real. """
        import argparse
        args = argparse.Namespace(
            workload='wl_ifi', backend='netplumber', apkeep_engine='ndd',
            vf_fields='4+10', engine_options='', jvm_xmx=None, keep_every=None,
            reuse_inputs=False, mutate=False, mutate_cell='s1,s8',
            invert_lpm=False)
        _argv, env, _stamps = cell_run.build_command(args)
        self.assertEqual(env['PYTHON'], sys.executable)

    def test_the_berkeley_drill_hands_it_to_the_generator(self):
        """ The step that actually failed: the generation subprocess. """
        import berkeley_drill
        captured = {}

        class _Proc:
            pid = os.getpid()

            @staticmethod
            def wait(timeout=None):            # pylint: disable=unused-argument
                return 0

        def _popen(argv, **kwargs):
            captured['argv'] = argv
            captured['env'] = kwargs.get('env')
            return _Proc()

        out = tempfile.mkdtemp(prefix='drill_')
        with mock.patch.object(subprocess, 'Popen', _popen):
            berkeley_drill._generate(out, 30, 1800, 2000)

        self.assertIn('test/gen_deltanet_inputs.sh', captured['argv'])
        self.assertIsNotNone(
            captured['env'], 'the generator inherited the caller env wholesale')
        self.assertEqual(captured['env']['PYTHON'], sys.executable)


if __name__ == '__main__':
    unittest.main()
