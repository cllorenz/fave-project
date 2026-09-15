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

""" `fave_bridge._structural_state_literals` must REFUSE a condition it cannot
honour, never drop it (AD6_PLAN.md §9.23.2a).

Why this file exists. The wl_up cchecks analysis reported a confident,
internally consistent set of figures that turned out to measure nothing,
because a driver passed `cond` as the raw `['related:0']` strings straight out
of cchecks.json instead of the `RuleField.to_json()` dicts. The function
skipped them with a bare `continue`, so all 3,302 stateful checks were silently
answered as though they carried NO condition at all -- and an unconditioned
answer to a stateful question is a plausible-looking wrong number, not an
error. See §9.23.3 for what it cost.

Two distinct silent drops are closed here, and they are worth separating:

  * MALFORMED -- the caller's fault. A non-dict entry, a dict with no `name`,
    or a `related` value that is not an integer.

  * UNSATISFIABLE -- the model's. The condition is well-formed, but the
    structural model declares no `related` field for it to bind to, so nothing
    can be forced. Outcome identical to the bug above, hence the same refusal.

A well-formed condition naming some OTHER field (`protocol`, `port` --
wl_example carries these alongside `related`) is refused too. Neither query
path can force a generic field, so honouring the request is not on the table;
the only choice is between refusing and answering a different question, and
answering a different question is what this whole file exists to prevent.
Nothing routes wl_example through ad6 today, so this costs no working run.

Both query paths are covered: `_state_literals` (semantic, ad6 `<state>`
variables) and `_structural_state_literals` (structural, node-scoped field
bits). They shared the same `continue`, and the semantic one had a second
silent drop of its own -- a `related` value outside `_RELATED_STATE`. """

import os
import sys
import unittest

# ad6/ must go on sys.path for `fave_bridge` (and its own `src.*` imports) to
# resolve -- but APPENDED, never prepended. `ad6.translate` prepends it, and
# ad6/ has a `test/` package of its own which then SHADOWS fave's, breaking
# `from test.backend_gate import ...` in every module collected after this one.
_AD6 = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ad6'))
if _AD6 not in sys.path:
    sys.path.append(_AD6)

import fave_bridge


_WIDTHS = {"in_port": 12, "out_port": 12, "related": 8}


def _related(value="1"):
    return {"name": "related", "value": value, "negated": False}


class TestStructuralStateLiteralsAccepts(unittest.TestCase):
    """ The well-formed cases must keep working unchanged. """

    def test_related_condition_yields_one_literal_per_bit(self):
        literals = fave_bridge._structural_state_literals(
            [_related("1")], _WIDTHS, "node")
        self.assertEqual(len(literals), _WIDTHS["related"])

    def test_related_zero_and_one_differ(self):
        """ The whole point of the mechanism: the two variants of a `<->>`
        check must not come back identical (§9.23.3). """
        import lxml.etree as et
        as_text = lambda cond: sorted(
            et.tostring(l) for l in
            fave_bridge._structural_state_literals([cond], _WIDTHS, "node"))
        self.assertNotEqual(as_text(_related("0")), as_text(_related("1")))

    def test_no_condition_is_not_an_error(self):
        for empty in ([], None):
            self.assertEqual(
                fave_bridge._structural_state_literals(empty, _WIDTHS, "node"), [])

    def test_no_condition_is_not_an_error_even_without_a_related_field(self):
        """ wl_ifi's structural model declares no `related` width at all, and
        sweeps it with empty conds. That must stay silent -- there is nothing
        to honour and nothing to lose. """
        self.assertEqual(
            fave_bridge._structural_state_literals([], {"in_port": 7}, "node"), [])



class TestStructuralStateLiteralsRefusesMalformed(unittest.TestCase):
    """ THE REGRESSION. Each of these silently returned [] before. """

    def test_raw_string_condition_raises(self):
        """ Exactly the shape that produced §9.23's phantom finding. """
        with self.assertRaises(ValueError) as ctx:
            fave_bridge._structural_state_literals(
                ["related:0"], _WIDTHS, "node")
        self.assertIn("related:0", str(ctx.exception))

    def test_dict_without_a_name_raises(self):
        with self.assertRaises(ValueError):
            fave_bridge._structural_state_literals(
                [{"value": "1"}], _WIDTHS, "node")

    def test_non_integer_related_value_raises(self):
        with self.assertRaises(ValueError):
            fave_bridge._structural_state_literals(
                [_related("ESTABLISHED")], _WIDTHS, "node")

    def test_missing_related_value_raises(self):
        with self.assertRaises(ValueError):
            fave_bridge._structural_state_literals(
                [{"name": "related"}], _WIDTHS, "node")


class TestUnsupportedConditionFieldsRefused(unittest.TestCase):
    """ wl_example emits `protocol`/`port` next to `related`. Neither path can
    force a generic field, so both must refuse rather than answer the
    unconditioned question. """

    def test_structural_refuses_an_unsupported_field(self):
        with self.assertRaises(ValueError) as ctx:
            fave_bridge._structural_state_literals(
                [{"name": "protocol", "value": "tcp", "negated": False}],
                _WIDTHS, "node")
        self.assertIn("protocol", str(ctx.exception))

    def test_semantic_refuses_an_unsupported_field(self):
        with self.assertRaises(ValueError) as ctx:
            fave_bridge._state_literals(
                [{"name": "port", "value": "80", "negated": False}])
        self.assertIn("port", str(ctx.exception))

    def test_structural_refuses_even_when_a_related_entry_is_also_present(self):
        """ The dangerous shape: enough of the condition is honoured to look
        like it worked. """
        with self.assertRaises(ValueError):
            fave_bridge._structural_state_literals(
                [{"name": "protocol", "value": "tcp"}, _related("1")],
                _WIDTHS, "node")

    def test_semantic_refuses_even_when_a_related_entry_is_also_present(self):
        with self.assertRaises(ValueError):
            fave_bridge._state_literals(
                [{"name": "protocol", "value": "tcp"}, _related("1")])


class TestSemanticStateLiterals(unittest.TestCase):
    """ `_state_literals` -- the semantic path's counterpart. Same `continue`,
    plus a silent drop of its own: `_RELATED_STATE` maps only "0"/"1", and
    anything else used to vanish. """

    def test_related_condition_yields_state_literals(self):
        self.assertTrue(fave_bridge._state_literals([_related("1")]))

    def test_related_zero_and_one_differ(self):
        import lxml.etree as et
        as_text = lambda v: sorted(
            et.tostring(l) for l in fave_bridge._state_literals([_related(v)]))
        self.assertNotEqual(as_text("0"), as_text("1"))

    def test_no_condition_is_not_an_error(self):
        for empty in ([], None):
            self.assertEqual(fave_bridge._state_literals(empty), [])

    def test_raw_string_condition_raises(self):
        with self.assertRaises(ValueError) as ctx:
            fave_bridge._state_literals(["related:0"])
        self.assertIn("related:0", str(ctx.exception))

    def test_dict_without_a_name_raises(self):
        with self.assertRaises(ValueError):
            fave_bridge._state_literals([{"value": "1"}])

    def test_unmapped_related_value_raises(self):
        """ THE SECOND SILENT DROP. Only "0"/"1" are in _RELATED_STATE; "2" and
        "ESTABLISHED" both used to return [] and answer the unconditioned
        question. """
        for bad in ("2", "ESTABLISHED", None):
            with self.assertRaises(ValueError) as ctx:
                fave_bridge._state_literals([_related(bad)])
            self.assertIn("related", str(ctx.exception))


class TestStructuralStateLiteralsRefusesUnsatisfiable(unittest.TestCase):
    """ A well-formed `related` condition against a model that has no such
    field cannot be honoured; answering the unconditioned question instead is
    the §9.23.2a failure mode, so it must refuse too. """

    def test_related_condition_without_a_declared_width_raises(self):
        for widths in ({"in_port": 7}, {}, None):
            with self.assertRaises(ValueError) as ctx:
                fave_bridge._structural_state_literals(
                    [_related("1")], widths, "node")
            self.assertIn("related", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
