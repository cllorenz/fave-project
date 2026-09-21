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

""" `fave_bridge`'s query-condition path must REFUSE what it cannot honour,
never drop it (AD6_PLAN.md §9.23.2a).

Why this file exists. The wl_up cchecks analysis reported a confident,
internally consistent set of figures that turned out to measure nothing,
because a driver passed `cond` as the raw `['related:0']` strings straight out
of cchecks.json instead of the `RuleField.to_json()` dicts. The function
skipped them with a bare `continue`, so all 3,302 stateful checks were silently
answered as though they carried NO condition at all -- and an unconditioned
answer to a stateful question is a plausible-looking wrong number, not an
error. See §9.23.3 for what it cost.

THE PATH IS NOW RECIPE-DRIVEN, and the guarantee is stated differently as a
result. It used to be an allowlist of one field (`related`); it is now whatever
`fave/ad6/translate.query_field_recipes` says THIS model contains, because
which namespace a field lives in is a property of the model rather than of the
field. Three outcomes, and keeping them apart is the whole job:

  * MALFORMED -- the caller's fault. A non-dict entry, a dict with no `name`,
    a node-scoped value that is not an integer, a protocol ad6 cannot name.

  * UNSUPPORTED -- this module's. The translator can turn the field into a
    MATCH but not yet into a forced CONDITION, so it ships `scope:
    unsupported` and the bridge refuses. Absence must never have to stand in
    for "not implemented".

  * VACUOUS -- the model's, and the one case that is HONOURED rather than
    refused. The recipe map is authoritative: a field absent from it is one no
    rule of the model matches or rewrites, so every flow already satisfies a
    condition on it and forcing nothing answers the question that was asked.
    A stateless model against `related:0` is exactly this, and it is what lets
    ad6 run wl_cloud at all (CLOUD_BENCH_PLAN.md §1.7.2).

That third case USED TO BE A REFUSAL, and the change is deliberate: refusing it
conflated "the model says nothing about this field" with "I have no idea what
this field is", which are opposite situations. The bridge announces every
vacuous condition on stderr so a run's own record says which fields it was.
"""

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


#: A stand-in for what `query_field_recipes` emits, covering all three scopes.
_RECIPES = {
    'related': {'scope': 'node', 'field': 'related', 'width': 8},
    'packet.upper.dport': {'scope': 'global', 'kind': 'port',
                           'direction': 'dst'},
    'packet.ipv6.proto': {'scope': 'global', 'kind': 'proto',
                          'names': {'6': 'tcp', '17': 'udp'}},
    'packet.ipv4.destination': {'scope': 'global', 'kind': 'cidr',
                                'direction': 'dst', 'version': '4'},
    'module.limit': {'scope': 'unsupported', 'why': 'module.limit has no '
                                                    'query-condition form'},
}

_NODE = 'probe_node'


def _related(value="1", negated=False):
    return {"name": "related", "value": value, "negated": negated}


def _terms(cond, recipes=_RECIPES):
    return fave_bridge._condition_terms(cond, recipes, _NODE)


class TestWellFormedConditionsAreForced(unittest.TestCase):
    """ The cases that must work, per scope. """

    def test_a_node_scoped_field_yields_one_literal_per_bit(self):
        units, clauses, vacuous = _terms([_related("1")])
        self.assertEqual(len(units), _RECIPES['related']['width'])
        self.assertEqual((clauses, vacuous), ([], []))

    def test_related_zero_and_one_differ(self):
        """ The whole point of the mechanism: the two variants of a `<->>`
        check must not come back identical (§9.23.3). """
        import lxml.etree as et
        as_text = lambda value: sorted(
            et.tostring(l) for l in _terms([_related(value)])[0])
        self.assertNotEqual(as_text("0"), as_text("1"))

    def test_a_node_scoped_field_is_forced_at_the_NODE_it_is_given(self):
        """ The bridge passes the PROBE's node, because that is where FaVe
        evaluates a check's condition -- `_create_compliance_rules` hands the
        vector to the probe, whose incoming flows carry the header as it
        ARRIVES. For a field nothing rewrites the choice is immaterial; for a
        rewritten one only the probe is right. """
        units, _c, _v = _terms([_related("1")])
        for literal in units:
            self.assertIn(_NODE, literal.attrib['name'])

    def test_a_global_port_lands_in_the_SHARED_bit_vector(self):
        """ Not a named alias. A whole-value alias (`dst_port_331`) only
        carries meaning if some rule references that EXACT value, which is
        AD6_PLAN.md §5.1's "bug 2" -- seven of wl_up's eight source addresses
        were free atoms because of it. The per-bit names are what every rule's
        own condition expands into. """
        units, _c, _v = _terms(
            [{'name': 'packet.upper.dport', 'value': '331', 'negated': False}])
        names = [l.attrib['name'] for l in units]
        self.assertEqual(len(names), 16)
        self.assertTrue(all(n.startswith('dst_port_') and '=' in n
                            for n in names), names)

    def test_a_protocol_is_forced_BY_NAME_not_by_number(self):
        """ ad6's `CanonizeProto` looks its table up by name and silently
        returns the no-next-header code on a miss: `CanonizeProto('6')` is 59,
        not 6. A `RuleField` canonicalises `tcp` to `'6'`, so passing the value
        through would force a bit pattern no rule in the model ever matches --
        a wrong answer, not an error. The translator ships the table. """
        from src.xml.xmlutils import XMLUtils
        units, _c, _v = _terms(
            [{'name': 'packet.ipv6.proto', 'value': '6', 'negated': False}])
        by_name = [l.attrib['name']
                   for l in XMLUtils.ConvertProtoToVariables('tcp')]
        self.assertEqual([l.attrib['name'] for l in units], by_name)

    def test_no_condition_is_not_an_error(self):
        for empty in ([], None):
            self.assertEqual(_terms(empty), ([], [], []))


class TestANegatedConditionBecomesOneClause(unittest.TestCase):
    """ `f=!port:331` is "some bit differs" -- a DISJUNCTION, which no list of
    unit assumptions can express. """

    def test_it_is_one_clause_and_no_units(self):
        units, clauses, _v = _terms(
            [{'name': 'packet.upper.dport', 'value': '331', 'negated': True}])
        self.assertEqual(units, [])
        self.assertEqual(len(clauses), 1)
        self.assertEqual(len(clauses[0]), 16)

    def test_every_literal_in_it_is_the_negation_of_the_positive_one(self):
        """ WEAK ON PURPOSE. Asserting "some bit IS the other value" would name
        variables the encoding may not contain, and a fresh variable carries no
        at-most-one exclusion against the one the path forces -- the query
        would come back satisfiable for the wrong reason. Negating exactly the
        literals a positive condition would force uses only variables the model
        already has. """
        positive, _c, _v = _terms(
            [{'name': 'packet.upper.dport', 'value': '331', 'negated': False}])
        _u, clauses, _v = _terms(
            [{'name': 'packet.upper.dport', 'value': '331', 'negated': True}])

        self.assertEqual([l.attrib['name'] for l in clauses[0]],
                         [l.attrib['name'] for l in positive])
        self.assertTrue(all(l.attrib['negated'] == 'true' for l in clauses[0]))

    def test_a_negated_node_scoped_field_also_becomes_a_clause(self):
        _u, clauses, _v = _terms([_related("1", negated=True)])
        self.assertEqual(len(clauses), 1)
        self.assertEqual(len(clauses[0]), 8)


class TestAVacuousConditionIsHONOURED(unittest.TestCase):
    """ THE DELIBERATE CHANGE. A field the model does not constrain is not a
    field the bridge failed to understand. """

    def test_a_field_no_rule_touches_forces_nothing_and_says_so(self):
        units, clauses, vacuous = _terms([_related("0")], recipes={})
        self.assertEqual((units, clauses), ([], []))
        self.assertEqual(vacuous, ['related'])

    def test_it_is_reported_per_field_so_a_run_can_record_which(self):
        """ The distinction between "honoured, there was nothing there" and
        "quietly dropped" only survives into a run's record if the run names
        the fields. """
        _u, _c, vacuous = _terms(
            [_related("0"),
             {'name': 'packet.upper.dport', 'value': '331', 'negated': False}],
            recipes={'packet.upper.dport': _RECIPES['packet.upper.dport']})
        self.assertEqual(vacuous, ['related'])

    def test_a_match_all_value_is_vacuous_too(self):
        """ The field exists, but the value constrains nothing -- ad6's own
        `ConvertCIDRToVariables` returns a constant for a /0. """
        _u, _c, vacuous = _terms([{'name': 'packet.ipv4.destination',
                                   'value': '0.0.0.0/0', 'negated': False}])
        self.assertEqual(vacuous, ['packet.ipv4.destination'])

    def test_a_missing_recipe_MAP_is_still_refused(self):
        """ No map at all is not the same as a map that omits a field: the
        first says nobody knows, the second is a statement. """
        with self.assertRaises(ValueError) as ctx:
            _terms([_related("0")], recipes=None)
        self.assertIn('query_fields', str(ctx.exception))


class TestMalformedConditionsAreRefused(unittest.TestCase):
    """ THE REGRESSION. Each of these silently returned [] before §9.23. """

    def test_raw_string_condition_raises(self):
        """ Exactly the shape that produced §9.23's phantom finding. """
        with self.assertRaises(ValueError) as ctx:
            _terms(["related:0"])
        self.assertIn("related:0", str(ctx.exception))

    def test_dict_without_a_name_raises(self):
        with self.assertRaises(ValueError):
            _terms([{"value": "1"}])

    def test_non_integer_node_scoped_value_raises(self):
        with self.assertRaises(ValueError):
            _terms([_related("ESTABLISHED")])

    def test_missing_value_raises(self):
        with self.assertRaises(ValueError):
            _terms([{"name": "related"}])

    def test_an_unnameable_protocol_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _terms([{'name': 'packet.ipv6.proto', 'value': '47',
                     'negated': False}])
        self.assertIn('47', str(ctx.exception))


class TestUnsupportedConditionFieldsRefused(unittest.TestCase):
    """ A field the translator can MATCH but not yet FORCE. """

    def test_an_unsupported_scope_is_refused_with_its_reason(self):
        with self.assertRaises(ValueError) as ctx:
            _terms([{'name': 'module.limit', 'value': '10', 'negated': False}])
        self.assertIn('query-condition form', str(ctx.exception))

    def test_it_is_refused_even_when_a_honourable_entry_is_also_present(self):
        """ The dangerous shape: enough of the condition is honoured to look
        like it worked. """
        with self.assertRaises(ValueError):
            _terms([{'name': 'module.limit', 'value': '10'}, _related("1")])


class TestContradictoryConditionsRefused(unittest.TestCase):
    """ Two positive conditions pinning one bit to both values.

    Not merely contradictory but WRONGLY SATISFIABLE if left alone: the
    at-most-one constraint exists only between the `=0`/`=1` pair the model
    itself mentions, so a bit no rule pins gets two fresh unrelated variables
    and both can be true. """

    def test_two_different_ports_at_once_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            _terms([{'name': 'packet.upper.dport', 'value': '331'},
                    {'name': 'packet.upper.dport', 'value': '332'}])
        self.assertIn('at once', str(ctx.exception))

    def test_the_same_port_twice_is_fine(self):
        units, _c, _v = _terms(
            [{'name': 'packet.upper.dport', 'value': '331'},
             {'name': 'packet.upper.dport', 'value': '331'}])
        self.assertEqual(len(units), 32)

    def test_two_different_node_scoped_values_are_refused(self):
        with self.assertRaises(ValueError):
            _terms([_related("0"), _related("1")])


if __name__ == "__main__":
    unittest.main()
