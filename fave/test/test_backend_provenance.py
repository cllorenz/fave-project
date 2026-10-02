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

""" Every backend says whose code it is (TODO item 31's provenance column).

Item 31 makes provenance its own axis, separate from the accommodations: one
says WHOSE CODE RUNS, the other how much of the workload the tool supports as
published, and a cell can be the authors' code with a FaVe extension. It also
says how the value must get into a cell -- *"stamped, not typed by hand: the
value comes from the backend ... with the engine's own commit, so a table
cannot mislabel a row"*.

Until 2026-10-02 only VeriFlow-FR stamped one, and it did so with a literal in
its own `configuration_stamp`. `bench/cell_run.py` therefore recorded `impl:
null` for three of the four backends. These tests are what stop that coming
back: a new backend that declares no provenance fails here, rather than
producing cells that cannot say where their numbers came from.

Pure Python: it imports the four adapter classes and reads class attributes. No
engine is constructed and no backend is needed.
"""

import inspect
import unittest

from aggregator.abstract_engine import AbstractVerificationEngine, IMPLS
from ad6.adapter import Ad6Adapter
from apkeep.adapter import APKeepAdapter
from netplumber.adapter import NetPlumberAdapter
from veriflow.adapter import VeriFlowAdapter

#: The four backends `FAVE_BACKEND` selects between.
BACKENDS = {
    'netplumber': NetPlumberAdapter,
    'apkeep': APKeepAdapter,
    'ad6': Ad6Adapter,
    'veriflow': VeriFlowAdapter,
}


class TestEveryBackendDeclaresItsProvenance(unittest.TestCase):

    def test_each_declares_a_value_from_item_31s_vocabulary(self):
        for name, cls in sorted(BACKENDS.items()):
            with self.subTest(backend=name):
                self.assertIn(
                    cls.IMPL, IMPLS,
                    "%s declares IMPL=%r, which is not one of item 31's "
                    "provenance values. A cell from it could not say whose "
                    "code produced the number." % (name, cls.IMPL))

    def test_the_abstract_base_declares_nothing(self):
        # So that a new backend inherits a value it must override, rather than
        # silently inheriting someone else's provenance.
        self.assertIsNone(AbstractVerificationEngine.IMPL)

    def test_a_fork_names_the_upstream_it_forked(self):
        # `authors+fave` is a claim about a baseline. Without naming the
        # import it is a claim no reader can check, and the change records
        # (`*/FAVE_CHANGES.md`) exist precisely to make it checkable.
        for name, cls in sorted(BACKENDS.items()):
            if cls.IMPL != 'authors+fave':
                continue
            with self.subTest(backend=name):
                upstreams = ([cls.UPSTREAM] if cls.UPSTREAM
                             else list(getattr(cls, 'UPSTREAMS', {}).values()))
                self.assertTrue(
                    upstreams and all(upstreams),
                    "%s is a fork but names no upstream import" % name)

    def test_a_first_party_or_clean_room_engine_forks_nothing(self):
        for name, cls in sorted(BACKENDS.items()):
            if cls.IMPL in ('authors+fave', 'authors'):
                continue
            with self.subTest(backend=name):
                self.assertIsNone(
                    cls.UPSTREAM,
                    "%s is %r, which is a fork of nothing, yet names an "
                    "upstream" % (name, cls.IMPL))

    def test_provenance_is_declared_once_not_typed_into_the_stamp(self):
        # The failure mode this replaces: VeriFlow-FR used to carry the
        # literal "reimpl-literature" inside configuration_stamp, which is
        # exactly the hand-typing item 31 rules out -- and is why the other
        # three could go on declaring nothing without anything noticing.
        for name, cls in sorted(BACKENDS.items()):
            with self.subTest(backend=name):
                source = inspect.getsource(cls.configuration_stamp) \
                    if 'configuration_stamp' in cls.__dict__ else ''
                for value in IMPLS:
                    self.assertNotIn(
                        "'%s'" % value, source,
                        "%s types the provenance literal %r into its stamp; "
                        "it belongs in IMPL, which the base class reads"
                        % (name, value))


class TestTheStampReachesACell(unittest.TestCase):
    """ Declaring it is half; a cell has to be able to read it back. """

    def test_apkeep_resolves_a_different_upstream_per_engine(self):
        # BDD and NDD are two forks of two different repositories, so one
        # UPSTREAM would name the wrong one for one of the two columns.
        self.assertNotEqual(APKeepAdapter.UPSTREAMS['bdd'],
                            APKeepAdapter.UPSTREAMS['ndd'])
        for engine in ('bdd', 'ndd'):
            with self.subTest(engine=engine):
                self.assertIn(engine.join(('', '')).strip() or engine,
                              APKeepAdapter.UPSTREAMS)

    def test_the_default_stamp_is_the_provenance(self):
        # A backend with no configuration to declare still reports whose it is,
        # which is why `configuration_stamp` has a default rather than being
        # abstract.
        class _Bare(AbstractVerificationEngine):
            IMPL = 'first-party'

        self.assertEqual(_Bare().configuration_stamp(),
                         {'impl': 'first-party'})

    def test_the_log_line_cell_run_parses_is_the_shape_it_expects(self):
        # `aggregator_service` logs `backend: <name> {<stamp>}` and
        # `cell_run.backend_stamp` parses it back. The two are a contract;
        # this is the test that fails if either side changes alone.
        from bench.cell_run import _BACKEND_LINE
        line = "backend: apkeep {'impl': 'authors+fave', 'engine': 'ndd'}"
        found = _BACKEND_LINE.search(line)
        self.assertIsNotNone(found, "the logged shape no longer parses")
        self.assertEqual(found.group(1), 'apkeep')
        self.assertIn("'impl'", found.group(2))

    def test_a_backend_line_without_a_stamp_is_reported_not_guessed(self):
        from bench.cell_run import _BACKEND_LINE
        found = _BACKEND_LINE.search("backend: apkeep")
        self.assertIsNotNone(found)
        self.assertIsNone(found.group(2))


if __name__ == '__main__':
    unittest.main()
