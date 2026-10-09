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

""" Ad6Adapter refuses the two model changes it would otherwise get wrong.

ad6 rebuilds its whole model from the buffers on every check, so a rule batch
for a NEW table, or a generator added after a check, is simply picked up. Two
changes were not: a second batch for a table that already holds rules REPLACED
the table (and the aggregator hands an engine only the rules being added, so
the earlier ones silently left the model), and `remove_link` edited the
aggregator's bookkeeping rather than the edges the model is built from, so the
link stayed. Both now raise `UpdateRefused` (TODO item 31's incremental axis).

Pure Python: the refusals fire before any translation or solver runs.
"""

import logging
import unittest

from types import SimpleNamespace

from ad6.adapter import Ad6Adapter
from aggregator.abstract_engine import UpdateRefused


def _adapter():
    log = logging.getLogger("test_ad6_update_refused")
    log.setLevel(logging.WARNING)
    return Ad6Adapter(log)


def _batch(node, **tables):
    return SimpleNamespace(node=node, tables=tables)


class TestAd6UpdateRefused(unittest.TestCase):

    def test_a_second_batch_for_a_populated_table_is_refused(self):
        ad6 = _adapter()
        ad6.add_rules(_batch('sw', **{'sw.1': ['r0', 'r1']}))
        with self.assertRaises(UpdateRefused) as ctx:
            ad6.add_rules(_batch('sw', **{'sw.1': ['r2']}))
        self.assertIn('sw.1', str(ctx.exception))
        # Refused, not half-applied: the table still holds what it held.
        self.assertEqual(ad6._tables['sw']['sw.1'], ['r0', 'r1'])

    def test_an_empty_batch_cannot_wipe_a_populated_table_either(self):
        ad6 = _adapter()
        ad6.add_rules(_batch('sw', **{'sw.1': ['r0']}))
        with self.assertRaises(UpdateRefused):
            ad6.add_rules(_batch('sw', **{'sw.1': []}))
        self.assertEqual(ad6._tables['sw']['sw.1'], ['r0'])

    def test_batches_for_different_tables_are_accepted(self):
        # The refusal is per table: a device whose tables arrive in separate
        # batches is not an update, and must keep working.
        ad6 = _adapter()
        ad6.add_rules(_batch('r', **{'r.acl_in': ['a0']}))
        ad6.add_rules(_batch('r', **{'r.routing': ['f0', 'f1']}))
        self.assertEqual(ad6._tables['r'],
                         {'r.acl_in': ['a0'], 'r.routing': ['f0', 'f1']})

    def test_a_table_declared_empty_can_be_filled_later(self):
        ad6 = _adapter()
        ad6.add_rules(_batch('sw', **{'sw.1': []}))
        ad6.add_rules(_batch('sw', **{'sw.1': ['r0']}))
        self.assertEqual(ad6._tables['sw']['sw.1'], ['r0'])

    def test_remove_link_is_refused_and_leaves_the_topology(self):
        ad6 = _adapter()
        ad6.add_link('a.1', 'b.1')
        with self.assertRaises(UpdateRefused):
            ad6.remove_link('a.1', 'b.1')
        self.assertEqual(ad6._raw_edges, [['a.1', 'b.1']])

    def test_update_refused_is_a_not_implemented_error(self):
        # Callers that already treat NotImplementedError as "this backend does
        # not do that" keep doing so.
        self.assertTrue(issubclass(UpdateRefused, NotImplementedError))


if __name__ == '__main__':
    unittest.main()
