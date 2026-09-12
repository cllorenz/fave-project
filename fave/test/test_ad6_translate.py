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
    UnsupportedAction, UnsupportedField, field_to_match, rewrite_field_for,
    rewritten_fields, rule_key, rule_to_ad6, split_port_direction,
    supported_fields, table_to_ad6,
)
from rule.rule_model import Forward, Miss, Rewrite, Rule, RuleField, Match


# Port provenance is structural in ad6, so these two are handled by rule_to_ad6
# as <interface> conditions, never by field_to_match as values.
_STRUCTURAL = {'in_port', 'out_port'}


def _target(port):
    """ A stand-in port resolver, so the rule layer can be tested without a
    port graph. """
    return 'T_' + str(port).replace('.', '_')


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
        missing = sorted((self._MEASURED - _STRUCTURAL) - supported_fields())
        self.assertEqual(missing, [],
                         "fields used by a real benchmark with no ad6 representation: %s"
                         % missing)

    def test_every_measured_field_translates_without_a_mutable_set(self):
        """ Coverage by NAME is not coverage: a field reachable only when it
        happens to be in the model's mutable set would raise on a model that
        never rewrote it. Each one must translate on its own. """
        for name in sorted(self._MEASURED - _STRUCTURAL):
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

    def test_related_is_node_scoped(self):
        self.assertIn('<fieldmatch ', _xml(field_to_match(RuleField('related', '1'))))

    def test_port_fields_are_REFUSED_by_the_field_layer(self):
        """ Ports are structural in ad6 (real interface nodes), so there must be
        exactly ONE representation of a port in the model -- an <interface>
        condition emitted by rule_to_ad6 -- rather than two that could
        disagree. field_to_match refusing them is what enforces that. """
        for name in sorted(_STRUCTURAL):
            with self.subTest(field=name):
                with self.assertRaises(UnsupportedField):
                    field_to_match(RuleField(name, 'dev.1_ingress'))

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


class TestPortNames(unittest.TestCase):
    def test_router_suffixes_are_split_off(self):
        self.assertEqual(split_port_direction('ifi.10_egress'), ('ifi.10', 'out'))
        self.assertEqual(split_port_direction('ifi.10_ingress'), ('ifi.10', 'in'))

    def test_an_unsuffixed_port_keeps_its_name_and_has_no_direction(self):
        self.assertEqual(split_port_direction('dev.1'), ('dev.1', None))

    def test_a_port_whose_name_merely_contains_the_word_is_not_split(self):
        self.assertEqual(split_port_direction('ingress.dev.1'), ('ingress.dev.1', None))


class TestRuleTranslation(unittest.TestCase):
    """ The rule layer. Every case is built by hand, so what is asserted is the
    emitted ad6 XML rather than a downstream verdict. """

    @staticmethod
    def _rule(match=None, actions=None, in_ports=None, idx=0):
        return Rule('dev', 't', idx, in_ports=in_ports,
                    match=Match(match or []), actions=actions or [])

    def _xml_of(self, rule, mutable=(), position=0):
        return _xml(rule_to_ad6(rule, 'k', _target, mutable=mutable, position=position))

    def test_a_forward_becomes_a_jump_to_the_resolved_target(self):
        out = self._xml_of(self._rule(actions=[Forward(['dev.2'])]))
        self.assertIn('<action type="jump" target="T_dev_2"/>', out)

    def test_each_fanout_port_gets_ITS_OWN_action(self):
        """ ad6 reads every <action> as its own TRUE edge (§9.7.2 option B), so
        N ports must produce N actions -- wl_stanford fans out to as many as
        16, and emitting one would silently drop 15 egresses. """
        out = self._xml_of(self._rule(actions=[Forward(['dev.2', 'dev.3', 'dev.4'])]))
        self.assertEqual(out.count('<action '), 3)
        for target in ('T_dev_2', 'T_dev_3', 'T_dev_4'):
            self.assertIn(target, out)

    def test_a_shared_rewrite_rides_on_every_fanout_action(self):
        """ Measured: no rule carries more than one Rewrite, so a fanning-out
        rule's single rewrite applies to all its targets. kripke.py folds the
        repeats into one per-node entry and refuses disagreement. """
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('packet.ether.vlan', '10')]),
                     Forward(['dev.2', 'dev.3'])]),
            mutable={'packet.ether.vlan'})
        self.assertEqual(out.count('rewrite_field="vlan"'), 2)
        self.assertEqual(out.count('rewrite_value="10"'), 2)

    def test_a_rule_that_forwards_nowhere_gets_no_action(self):
        """ ad6 reads an action-less rule as "matches, goes nowhere" -- a drop
        (kripketest.MultiActionRuleTest pins that). FaVe produces thousands of
        these (2,315 in wl_up), so they must translate, not raise. """
        out = self._xml_of(self._rule(
            match=[RuleField('packet.ipv4.destination', '10.0.0.0/8')], actions=[]))
        self.assertNotIn('<action', out)
        self.assertIn('<address>10.0.0.0/8</address>', out)

    def test_in_ports_become_interface_conditions(self):
        out = self._xml_of(self._rule(in_ports=['dev.1'], actions=[Forward(['dev.2'])]))
        self.assertIn('<interface direction="in">T_dev_1</interface>', out)

    def test_several_in_ports_all_appear(self):
        """ kripke.py ORs repeated <interface> elements of one direction, which
        is the right reading of a rule reachable from several ports. """
        out = self._xml_of(self._rule(in_ports=['dev.1', 'dev.2']))
        self.assertEqual(out.count('<interface direction="in">'), 2)

    def test_a_port_MATCH_becomes_an_interface_condition_not_a_value(self):
        out = self._xml_of(self._rule(
            match=[RuleField('in_port', 'dev.1_ingress')]))
        self.assertIn('<interface direction="in">', out)
        self.assertNotIn('fieldmatch', out)

    def test_an_out_port_match_carries_the_out_direction(self):
        out = self._xml_of(self._rule(match=[RuleField('out_port', 'dev.1_egress')]))
        self.assertIn('direction="out"', out)

    def test_port_REWRITES_emit_nothing(self):
        """ They are NetPlumber bookkeeping, not a forwarding decision: every
        rule carrying one also carries the Forward that actually decides, and
        half of them set a 32-wide wildcard that ad6 could not store anyway. """
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('in_port', 'x' * 32),
                              RuleField('out_port', 'x' * 32)]),
                     Forward(['dev.2'])]))
        self.assertNotIn('rewrite_field', out)
        self.assertIn('target="T_dev_2"', out)

    def test_a_match_all_address_contributes_no_condition(self):
        out = self._xml_of(self._rule(
            match=[RuleField('packet.ipv4.destination', '0.0.0.0/0')],
            actions=[Forward(['dev.2'])]))
        self.assertNotIn('<address>', out)
        self.assertIn('<action ', out)

    def test_duplicate_forward_ports_are_emitted_once(self):
        out = self._xml_of(self._rule(actions=[Forward(['dev.2']), Forward(['dev.2'])]))
        self.assertEqual(out.count('<action '), 1)

    def test_a_non_integer_rewrite_is_refused(self):
        with self.assertRaises(UnsupportedAction):
            self._xml_of(self._rule(
                actions=[Rewrite([RuleField('packet.ether.vlan', 'not-a-number')])]))

    def test_two_disagreeing_non_port_rewrites_are_refused(self):
        with self.assertRaises(UnsupportedAction):
            self._xml_of(self._rule(actions=[
                Rewrite([RuleField('packet.ether.vlan', '10')]),
                Rewrite([RuleField('packet.ether.vlan', '20')])]))

    def test_a_miss_action_is_accepted_and_forwards_nowhere(self):
        out = self._xml_of(self._rule(actions=[Miss()]))
        self.assertNotIn('<action', out)


class TestTableTranslation(unittest.TestCase):
    """ The table layer, whose single job is to NOT disturb order. """

    @staticmethod
    def _rules(count):
        return [Rule('dev', 't', i, in_ports=['dev.1'],
                     match=Match([RuleField('packet.ipv4.destination',
                                            '10.0.%d.0/24' % i)]),
                     actions=[Forward(['dev.2'])]) for i in range(count)]

    def test_rules_keep_their_given_order(self):
        table = table_to_ad6('dev', 't', self._rules(3), _target)
        keys = [r.get('key') for r in table]
        self.assertEqual(keys, [rule_key('dev', 't', i) for i in range(3)])

    def test_rule_names_are_positional(self):
        table = table_to_ad6('dev', 't', self._rules(3), _target)
        self.assertEqual([r.get('name') for r in table], ['r0', 'r1', 'r2'])

    def test_a_reordered_rule_list_is_REFUSED(self):
        """ Order IS the semantics -- FaVe's interwoven rulesets encode their
        state purely as rule position (§9.2a). A list whose positions disagree
        with its own indices has already lost information, so this fails rather
        than silently producing a different model. """
        rules = self._rules(3)
        rules[0], rules[2] = rules[2], rules[0]
        with self.assertRaises(ValueError):
            table_to_ad6('dev', 't', rules, _target)

    def test_an_empty_table_translates_to_an_empty_table(self):
        self.assertEqual(len(table_to_ad6('dev', 't', [], _target)), 0)

    def test_table_and_rule_keys_are_deterministic_and_dot_safe(self):
        self.assertEqual(rule_key('in.bbra_rtr', 'acl_in', 4),
                         'fw_in_bbra_rtr_acl_in_r4')
