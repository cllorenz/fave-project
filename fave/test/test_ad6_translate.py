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

""" AD6_PLAN.md §9 Phase 1: tests for the structural translator's field layer.

Written before the implementation, from hand-built `rule_model` objects, with
no model build and no benchmark -- which is the point: the translator's
correctness is decidable at this granularity, so it should be decided here
rather than inferred later from a reachability matrix that moved. """

import unittest

import lxml.etree as et

from ad6 import translate
from ad6.translate import (
    UnsupportedField, field_to_match, rewrite_field_for, rewritten_fields,
    supported_fields,
)
from rule.rule_model import Forward, Rewrite, Rule, RuleField, Match


def _xml(element):
    return et.tostring(element).decode() if element is not None else None


class TestFieldCoverage(unittest.TestCase):
    """ The table has to cover what the real benchmarks actually use. """

    # MEASURED 2026-09-12 by replaying wl_ifi, wl_up, wl_i2 and wl_stanford
    # through a recording Ad6Adapter subclass and counting every match field
    # (AD6_PLAN.md §9.6). Kept as a literal so this test fails when a
    # benchmark starts using a field the translator cannot represent -- the
    # cheapest possible warning, and it fires before any model is built.
    _MEASURED = {
        'in_port', 'out_port',
        'packet.ether.vlan',
        'packet.ipv4.source', 'packet.ipv4.destination',
        'packet.ipv6.source', 'packet.ipv6.destination',
        'packet.ipv6.proto', 'packet.ipv6.icmpv6.type',
        'packet.upper.sport', 'packet.upper.dport', 'packet.upper.tcp.flags',
        'module.limit', 'module.ipv6header.header',
        'module.ipv6header.rt.type', 'module.ipv6header.rt.segsleft',
        'related',
    }

    def test_every_field_the_benchmarks_use_is_representable(self):
        missing = sorted(self._MEASURED - supported_fields())
        self.assertEqual(missing, [],
                         "fields used by a real benchmark with no ad6 representation: %s"
                         % missing)

    def test_every_measured_field_translates_without_a_mutable_set(self):
        """ Coverage by NAME is not coverage: a field reachable only when it
        happens to be in the model's mutable set would raise on a model that
        never rewrote it. Each one must translate on its own. """
        for name in sorted(self._MEASURED):
            with self.subTest(field=name):
                self.assertIsNotNone(_xml(field_to_match(RuleField(name, '1'))))


class TestImmutableFieldsUseTypedPrimitives(unittest.TestCase):
    """ A field nothing rewrites resolves against ad6's global alias -- correct
    and much cheaper than a node-scoped SSA copy. """

    def test_ipv4_destination_becomes_a_dst_v4_address(self):
        self.assertEqual(_xml(field_to_match(RuleField('packet.ipv4.destination',
                                                       '10.0.0.0/8'))),
                         '<ip version="4" direction="dst"><address>10.0.0.0/8</address></ip>')

    def test_ipv4_source_becomes_a_src_v4_address(self):
        self.assertIn('direction="src"',
                      _xml(field_to_match(RuleField('packet.ipv4.source', '10.0.0.1/32'))))

    def test_ipv6_addresses_carry_version_6(self):
        for name in ('packet.ipv6.source', 'packet.ipv6.destination'):
            with self.subTest(field=name):
                self.assertIn('version="6"', _xml(field_to_match(RuleField(name, '2001:db8::/32'))))

    def test_transport_ports_carry_their_direction(self):
        self.assertEqual(_xml(field_to_match(RuleField('packet.upper.dport', '80'))),
                         '<port direction="dst">80</port>')
        self.assertEqual(_xml(field_to_match(RuleField('packet.upper.sport', '1024'))),
                         '<port direction="src">1024</port>')

    def test_icmpv6_type_and_tcp_flags(self):
        self.assertIn('icmp6-type', _xml(field_to_match(
            RuleField('packet.ipv6.icmpv6.type', 'echo-request'))))
        self.assertIn('tcp-flags', _xml(field_to_match(
            RuleField('packet.upper.tcp.flags', '1xxxxxxx'))))


class TestProtocolRoundTrip(unittest.TestCase):
    """ A silent wrong-answer hazard, found 2026-09-12 by these tests BEFORE
    any model was built, and the reason the field layer is tested at this
    granularity at all.

    FaVe canonicalises a protocol at RuleField construction ('tcp' -> '6').
    ad6's XMLUtils.CanonizeProto looks its IANA table up BY NAME and silently
    returns the no-next-header code (59) on a miss, under a `# TODO: error
    handling` comment -- so '6' and a typo produce byte-identical output and
    every tcp/udp/icmp match would quietly become a no-next-header match. """

    _SEEN = {'6': 'tcp', '17': 'udp', '58': 'icmp6'}   # measured across the benchmarks

    def test_fave_canonicalises_protocol_names_to_numbers(self):
        """ The premise. If this ever stops holding, the inverse map below is
        the wrong fix and this test says so first. """
        self.assertEqual(RuleField('packet.ipv6.proto', 'tcp').value, '6')

    def test_every_protocol_survives_the_round_trip_through_ad6(self):
        """ The property that matters: what ad6 finally encodes must be the
        protocol FaVe meant. Asserted against CanonizeProto itself, not against
        the name -- the name is only the means. """
        from src.xml.xmlutils import XMLUtils
        for number, name in sorted(self._SEEN.items()):
            with self.subTest(proto=number):
                element = field_to_match(RuleField('packet.ipv6.proto', number))
                self.assertEqual(element.text, name)
                bits = XMLUtils.CanonizeProto(element.text).replace(' ', '')
                self.assertEqual(int(bits, 2), int(number),
                                 "ad6 encodes %s as %d, not %s" % (name, int(bits, 2), number))

    def test_passing_the_raw_number_through_would_have_been_silently_wrong(self):
        """ The negative control that justifies the map's existence. Pinned so
        that if PySAT-style 'it was fixed upstream' ever happens to ad6, the
        map can be retired on evidence rather than on hope. """
        from src.xml.xmlutils import XMLUtils
        nonext = XMLUtils.CanonizeProto('nonsense')
        self.assertEqual(XMLUtils.CanonizeProto('6'), nonext,
                         "a numeric protocol is still indistinguishable from a typo")
        self.assertNotEqual(XMLUtils.CanonizeProto('tcp'), nonext)

    def test_a_protocol_ad6_cannot_name_is_refused_not_guessed(self):
        with self.assertRaises(UnsupportedField):
            field_to_match(RuleField('packet.ipv6.proto', '47'))     # GRE

    def test_negation_survives_the_name_translation(self):
        self.assertIn('negated="true"', _xml(field_to_match(
            RuleField('packet.ipv6.proto', '6', negated=True))))


class TestMutableFieldsUseFieldmatch(unittest.TestCase):
    """ The correctness requirement from §9 Phase 1: a field rewritten ANYWHERE
    in the model must be matched node-scoped EVERYWHERE, because it then holds
    different values at different points along one path. """

    def test_a_rewritten_field_switches_from_typed_primitive_to_fieldmatch(self):
        field = RuleField('packet.ipv4.destination', '10.0.0.0/8')
        self.assertIn('<ip ', _xml(field_to_match(field)))
        self.assertIn('<fieldmatch ',
                      _xml(field_to_match(field, mutable={'packet.ipv4.destination'})),
                      "a field some rule rewrites must not resolve against the "
                      "model-wide global alias")

    def test_vlan_uses_ad6s_own_field_name(self):
        """ <fieldmatch field="vlan"> must agree with <action rewrite_field="vlan">
        or a rewrite writes a field no match ever reads. """
        self.assertEqual(_xml(field_to_match(RuleField('packet.ether.vlan', '10'),
                                             mutable={'packet.ether.vlan'})),
                         '<fieldmatch field="vlan">10</fieldmatch>')
        self.assertEqual(rewrite_field_for('packet.ether.vlan'), 'vlan')

    def test_ports_and_related_are_always_node_scoped(self):
        for name in ('in_port', 'out_port', 'related'):
            with self.subTest(field=name):
                self.assertIn('<fieldmatch ', _xml(field_to_match(RuleField(name, '1'))))

    def test_related_is_a_plain_field_not_a_state_element(self):
        """ §9.2(a): FaVe's interweaving strips conntrack and re-emits `related`
        as an ordinary header field. Translating it back into ad6's <state>
        would re-introduce the state semantics the whole design drops. """
        self.assertNotIn('<state', _xml(field_to_match(RuleField('related', '1'))))


class TestMatchAllSuppression(unittest.TestCase):
    """ A match-all address constrains nothing. Phase 0.1 pinned that a rule
    with no condition shadows everything after it, exactly as an explicit /0
    does -- so the two must translate to the same thing. """

    def test_default_routes_produce_no_element(self):
        for value in ('0.0.0.0/0', '::/0', '0::0/0'):
            with self.subTest(value=value):
                name = ('packet.ipv4.destination' if value == '0.0.0.0/0'
                        else 'packet.ipv6.destination')
                self.assertIsNone(field_to_match(RuleField(name, value)))

    def test_a_constrained_prefix_is_not_suppressed(self):
        self.assertIsNotNone(field_to_match(RuleField('packet.ipv4.destination',
                                                      '10.0.0.0/8')))
        self.assertIsNotNone(field_to_match(RuleField('packet.ipv4.destination',
                                                      '0.0.0.0/1')))

    def test_a_NEGATED_match_all_is_kept(self):
        """ !0.0.0.0/0 is the EMPTY set, not the universe. Dropping it would
        turn an unsatisfiable rule into an unconditional one -- the single most
        dangerous direction for a soundness bug to go. """
        element = field_to_match(RuleField('packet.ipv4.destination', '0.0.0.0/0',
                                           negated=True))
        self.assertIsNotNone(element, "a negated match-all must not be suppressed")
        self.assertIn('negated="true"', _xml(element))


class TestNegation(unittest.TestCase):
    """ No benchmark currently emits a negated match (measured: 0 of ~95k
    rules), which is exactly why it is tested here rather than discovered
    later on the first workload that does. """

    def test_negation_survives_every_representation(self):
        cases = [
            ('packet.ipv4.destination', '10.0.0.0/8'),
            ('packet.upper.dport', '80'),
            ('packet.ipv6.proto', 'tcp'),
            ('related', '1'),
            ('packet.ether.vlan', '10'),
        ]
        for name, value in cases:
            with self.subTest(field=name):
                self.assertIn('negated="true"',
                              _xml(field_to_match(RuleField(name, value, negated=True))))

    def test_absence_of_negation_emits_no_attribute(self):
        self.assertNotIn('negated',
                         _xml(field_to_match(RuleField('packet.upper.dport', '80'))))


class TestUnsupportedFieldsRaise(unittest.TestCase):
    """ The rule this module is strictest about: never drop a constraint. """

    def test_an_unknown_field_raises(self):
        with self.assertRaises(UnsupportedField):
            field_to_match(RuleField('packet.ether.source', '00:11:22:33:44:55'))

    def test_the_error_names_the_field_and_says_what_to_do(self):
        try:
            field_to_match(RuleField('packet.ether.type', '0x800'))
        except UnsupportedField as error:
            message = str(error)
            self.assertIn('packet.ether.type', message)
            self.assertIn('test', message.lower())
        else:
            self.fail("expected UnsupportedField")

    def test_an_unknown_field_is_not_silently_rescued_by_the_mutable_set(self):
        """ `mutable` must not become a back door that makes any field
        translate -- a field only reaches fieldmatch by being a field the model
        genuinely rewrites, and an unknown name in that set is still a bug. """
        with self.assertRaises(UnsupportedField):
            field_to_match(RuleField('packet.ether.source', '00:11:22:33:44:55'),
                           mutable={'packet.ipv4.destination'})


class TestRewrittenFields(unittest.TestCase):
    """ The model-wide mutable set. """

    @staticmethod
    def _rule(actions):
        return Rule('dev', 1, 0, in_ports=['dev.1'], match=Match([]), actions=actions)

    def test_no_rewrites_gives_an_empty_set(self):
        self.assertEqual(rewritten_fields([self._rule([Forward(['dev.2'])])]), set())

    def test_a_rewrite_contributes_its_fields(self):
        rule = self._rule([Rewrite([RuleField('packet.ether.vlan', '10')]),
                           Forward(['dev.2'])])
        self.assertEqual(rewritten_fields([rule]), {'packet.ether.vlan'})

    def test_multi_field_rewrites_contribute_all_of_them(self):
        """ Measured: 187 rules across wl_ifi and wl_up rewrite more than one
        field at once. """
        rule = self._rule([Rewrite([RuleField('in_port', '1'),
                                    RuleField('out_port', '2')])])
        self.assertEqual(rewritten_fields([rule]), {'in_port', 'out_port'})

    def test_the_set_is_collected_across_the_WHOLE_model(self):
        """ A field rewritten on ONE device is mutable for every match of it
        anywhere -- collecting per device would make the same field node-scoped
        on one device and globally aliased on another, which is incoherent. """
        rules = [
            self._rule([Rewrite([RuleField('packet.ether.vlan', '10')])]),
            self._rule([Rewrite([RuleField('out_port', '2')])]),
            self._rule([Forward(['dev.2'])]),
        ]
        self.assertEqual(rewritten_fields(rules), {'packet.ether.vlan', 'out_port'})

    def test_rules_without_actions_are_tolerated(self):
        """ Measured: 2,315 wl_up rules and 690 wl_stanford rules have no
        actions at all. """
        self.assertEqual(rewritten_fields([self._rule([]), self._rule(None)]), set())


class TestPurity(unittest.TestCase):
    """ §9's structural discipline, asserted rather than trusted: nothing in
    this module may branch on a device name, a table name or a benchmark. """

    def test_the_module_mentions_no_stage_prefix_or_benchmark_name(self):
        with open(translate.__file__.replace('.pyc', '.py')) as handle:
            source = handle.read()
        # Only the docstring may name a workload (it cites the measurement);
        # no CODE line may.
        code = [line for line in source.split('\n')
                if line.strip() and not line.strip().startswith('#')]
        body = '\n'.join(code)
        body = body.split('"""', 2)[-1] if body.count('"""') >= 2 else body
        for forbidden in ("'in.", "'mid.", "'out.", 'wl_stanford', 'wl_i2', 'wl_ifi',
                          'wl_up', '.acl_in', '.routing'):
            self.assertNotIn(forbidden, body,
                             "structural translation must not branch on %r" % forbidden)


if __name__ == '__main__':
    unittest.main()
