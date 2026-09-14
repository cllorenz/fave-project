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
    """ A stand-in jump resolver, so the rule layer can be tested without a
    port graph. Names the port's egress NODE, as the real one does. """
    return 'T_' + str(port).replace('.', '_') + '_out'


_PORT_IDS = {}


def _port_id(port):
    """ A stand-in dense id map, so the rule layer stays testable without a
    port graph. Stable within a run, like the real one. """
    return _PORT_IDS.setdefault(str(port), len(_PORT_IDS) + 1)


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

    # Names that would mean the translator had learned a workload's shape.
    _FORBIDDEN = ('in.', 'mid.', 'out.', 'acl_in', 'acl_out', 'routing',
                  'pre_routing', 'post_routing', 'input_filter', 'forward_filter',
                  'wl_stanford', 'wl_i2', 'wl_ifi', 'wl_up')

    def test_no_STRING_LITERAL_in_the_code_names_a_workload_shape(self):
        """ Parsed rather than grepped. An earlier version of this test scanned
        the raw source and tripped over prose in docstrings -- which are exactly
        where naming a benchmark is legitimate, since that is where the
        MEASUREMENTS are cited. What must stay clean is executable code, so this
        walks the AST and inspects only string constants that are not
        docstrings. """
        import ast

        with open(translate.__file__.replace('.pyc', '.py')) as handle:
            tree = ast.parse(handle.read())

        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    docstrings.add(doc)

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in docstrings:
                continue
            for forbidden in self._FORBIDDEN:
                if forbidden in node.value:
                    offenders.append((node.lineno, node.value[:60], forbidden))

        self.assertEqual(offenders, [],
                         "structural translation must not branch on a workload's "
                         "own vocabulary: %s" % offenders)

    def test_the_check_would_actually_catch_a_violation(self):
        """ A purity test that cannot fail is decoration. """
        import ast
        tree = ast.parse("stage = 'mid.'\n")
        found = [n.value for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and any(f in n.value for f in self._FORBIDDEN)]
        self.assertEqual(found, ['mid.'])


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
        return _xml(rule_to_ad6(rule, 'k', _target, _port_id, mutable=mutable,
                               position=position))

    def test_a_forward_becomes_a_jump_to_the_resolved_target(self):
        out = self._xml_of(self._rule(actions=[Forward(['dev.2'])]))
        self.assertIn('<action type="jump" target="T_dev_2_out"/>', out)

    def test_each_fanout_port_gets_ITS_OWN_action(self):
        """ ad6 reads every <action> as its own TRUE edge (§9.7.2 option B), so
        N ports must produce N actions -- wl_stanford fans out to as many as
        16, and emitting one would silently drop 15 egresses. """
        out = self._xml_of(self._rule(actions=[Forward(['dev.2', 'dev.3', 'dev.4'])]))
        self.assertEqual(out.count('<action '), 3)
        for target in ('T_dev_2_out', 'T_dev_3_out', 'T_dev_4_out'):
            self.assertIn(target, out)

    def test_a_shared_rewrite_rides_on_every_fanout_action(self):
        """ Measured: no rule carries more than one Rewrite, so a fanning-out
        rule's single rewrite applies to all its targets. kripke.py folds the
        repeats into one per-node entry and refuses disagreement. """
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('packet.ether.vlan', '10')]),
                     Forward(['dev.2', 'dev.3'])]),
            mutable={'packet.ether.vlan'})
        self.assertEqual(out.count('<rewrite field="vlan" value="10"/>'), 2)

    def test_a_rule_that_forwards_nowhere_gets_no_action(self):
        """ ad6 reads an action-less rule as "matches, goes nowhere" -- a drop
        (kripketest.MultiActionRuleTest pins that). FaVe produces thousands of
        these (2,315 in wl_up), so they must translate, not raise. """
        out = self._xml_of(self._rule(
            match=[RuleField('packet.ipv4.destination', '10.0.0.0/8')], actions=[]))
        self.assertNotIn('<action', out)
        self.assertIn('<address>10.0.0.0/8</address>', out)

    def test_in_ports_emit_NO_condition(self):
        """ §9.12.2. An <interface> condition would be UNSOUND: ad6 makes it a
        free variable tied to nothing, so the solver may assert a packet came in
        on whichever port suits it -- which on wl_ifi let a packet fire a rule
        written for the Internet uplink, relabel its VLAN and walk past the deny
        meant for it. Ingress discrimination is structural instead: each
        entering port gets its own chain (PortGraph.chains). """
        out = self._xml_of(self._rule(in_ports=['dev.1'], actions=[Forward(['dev.2'])]))
        self.assertNotIn('<interface', out)
        self.assertIn('<action ', out)

    def test_several_in_ports_still_emit_no_condition(self):
        out = self._xml_of(self._rule(in_ports=['dev.1', 'dev.2']))
        self.assertNotIn('<interface', out)

    def test_a_port_MATCH_becomes_a_fieldmatch_on_its_dense_id(self):
        """ §9.10.2 option 1. An <interface> condition would be wrong for
        out_port -- it says "the path went through this egress", which is
        circular for the rule that LEADS to that egress. """
        out = self._xml_of(self._rule(
            match=[RuleField('in_port', 'dev.1_ingress')]))
        self.assertIn('<fieldmatch field="in_port">', out)
        self.assertNotIn('<interface direction="in">dev', out)

    def test_out_port_matches_the_same_way_as_in_port(self):
        out = self._xml_of(self._rule(match=[RuleField('out_port', 'dev.1_egress')]))
        self.assertIn('<fieldmatch field="out_port">', out)

    def test_a_port_REWRITE_carries_the_ports_id(self):
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('out_port', 'dev.9_egress')]),
                     Forward(['dev.2'])]))
        self.assertIn('<rewrite field="out_port" value=', out)

    def test_a_WILDCARD_port_rewrite_becomes_a_CLEAR(self):
        """ FaVe's post_routing clears both port fields before a packet leaves
        a device, spelled as an all-`x` mask. A clear carries no value: the
        field becomes unconstrained downstream, which a reserved value could
        not express (instantiatortest.ClearedFieldTest). """
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('in_port', 'x' * 32),
                              RuleField('out_port', 'x' * 32)]),
                     Forward(['dev.2'])]))
        self.assertIn('<rewrite field="in_port"/>', out)
        self.assertIn('<rewrite field="out_port"/>', out)
        self.assertNotIn('value=', out.split('<action')[1])

    def test_several_fields_are_rewritten_by_one_action(self):
        """ wl_ifi's routing rules set out_port AND vlan together. """
        out = self._xml_of(self._rule(
            actions=[Rewrite([RuleField('out_port', 'dev.9_egress'),
                              RuleField('packet.ether.vlan', '10')]),
                     Forward(['dev.2'])]),
            mutable={'packet.ether.vlan', 'out_port'})
        self.assertIn('<rewrite field="out_port" value=', out)
        self.assertIn('<rewrite field="vlan" value="10"/>', out)

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
        table = table_to_ad6('dev', 't', 'dev.1', self._rules(3), _target, _port_id)
        keys = [r.get('key') for r in table]
        self.assertEqual(keys, [rule_key('dev', 't', 'dev.1', i) for i in range(3)])

    def test_rule_names_are_positional(self):
        table = table_to_ad6('dev', 't', 'dev.1', self._rules(3), _target, _port_id)
        self.assertEqual([r.get('name') for r in table], ['r0', 'r1', 'r2'])

    def test_rules_are_ordered_by_ASCENDING_idx_not_by_list_position(self):
        """ `Rule.idx` is a PRIORITY, and FaVe hands rules out in an order that
        often disagrees with it -- 4 of wl_ifi's 38 tables, 138 of wl_up's
        1,134. Lower index wins: 65535 is FaVe's max-priority default rule, and
        np_preparation._reprioritise_fib_lpm repairs a FIB by reassigning
        indices in descending prefix-length order. Since ad6 evaluates a table
        first-match-wins in DOCUMENT order, emitting the list as handed over
        would run a default rule before the specific rule it backs up. """
        rules = self._rules(3)
        rules[0].idx, rules[1].idx, rules[2].idx = 65535, 1, 768
        table = table_to_ad6('dev', 't', 'dev.1', rules, _target, _port_id)
        emitted = [r.xpath('.//address')[0].text for r in table]
        self.assertEqual(emitted, ['10.0.1.0/24', '10.0.2.0/24', '10.0.0.0/24'],
                         "expected idx order 1, 768, 65535")

    def test_an_unindexed_table_keeps_the_order_it_was_given(self):
        rules = self._rules(3)
        for rule in rules:
            rule.idx = None
        table = table_to_ad6('dev', 't', 'dev.1', rules, _target, _port_id)
        self.assertEqual([r.xpath('.//address')[0].text for r in table],
                         ['10.0.0.0/24', '10.0.1.0/24', '10.0.2.0/24'])

    def test_a_DUPLICATE_idx_is_refused(self):
        """ Two rules sharing an index leave the evaluation order genuinely
        ambiguous. Measured: no table in any benchmark has one. """
        rules = self._rules(3)
        rules[1].idx = rules[0].idx
        with self.assertRaises(ValueError):
            table_to_ad6('dev', 't', 'dev.1', rules, _target, _port_id)

    def test_a_PARTIALLY_indexed_table_is_refused(self):
        """ There is no defensible place to interleave an unindexed rule among
        prioritised ones. """
        rules = self._rules(3)
        rules[1].idx = None
        with self.assertRaises(ValueError):
            table_to_ad6('dev', 't', 'dev.1', rules, _target, _port_id)

    def test_an_empty_table_translates_to_an_empty_table(self):
        self.assertEqual(len(table_to_ad6('dev', 't', None, [], _target, _port_id)), 0)

    def test_table_and_rule_keys_are_deterministic_and_dot_safe(self):
        self.assertEqual(rule_key('in.bbra_rtr', 'acl_in', None, 4),
                         'fw_in_bbra_rtr_acl_in_r4')


class TestPortGraph(unittest.TestCase):
    """ Resolution from DECLARED structure only -- a rule's own in_ports, a
    device's own wiring, the topology's own links. Nothing reads a name. """

    @staticmethod
    def _rule(in_ports=None, forwards=None, idx=0, match=None):
        return Rule('d', 't', idx, in_ports=in_ports, match=Match(match or []),
                    actions=[Forward(forwards)] if forwards else [])

    @staticmethod
    def _dev(name, rules, ports=(), wiring=()):
        return {'tables': {name + '.t0': list(rules)},
                'ports': list(ports), 'wiring': list(wiring)}

    def _graph(self, devices, links=()):
        from ad6.translate import PortGraph
        return PortGraph(devices, links)

    def test_a_port_splits_against_the_declared_device_set(self):
        graph = self._graph({'adm.uni-potsdam.de': self._dev('adm.uni-potsdam.de', [])})
        self.assertEqual(graph.split('adm.uni-potsdam.de.1_egress'),
                         ('adm.uni-potsdam.de', '1_egress'))

    def test_splitting_is_not_a_convention_but_a_lookup(self):
        """ A device name containing no dot and a port name containing one are
        indistinguishable by parsing -- so an unknown port must raise rather
        than be guessed at. """
        graph = self._graph({'a': self._dev('a', [])})
        with self.assertRaises(KeyError):
            graph.split('somewhere.else.1')

    def test_a_forward_target_is_the_ports_egress_node(self):
        graph = self._graph({'a': self._dev('a', [])})
        self.assertEqual(graph.target('a.out'), 'favenet_a_out_out')

    def test_an_interface_condition_key_carries_no_suffix(self):
        """ The jump key and the condition key must differ: naming the '_out'
        node in a condition would reference a node that exists but is never on
        the ingress path, making the rule quietly unsatisfiable. """
        graph = self._graph({'a': self._dev('a', [])})
        self.assertEqual(graph.interface('a.out'), 'favenet_a_out')
        self.assertNotEqual(graph.interface('a.out'), graph.target('a.out'))

    def test_entry_is_rule_zero_of_the_table_that_port_enters(self):
        graph = self._graph({'a': self._dev('a', [self._rule(in_ports=['a.in'])])})
        self.assertEqual(graph.entry('a.in'), rule_key('a', 'a.t0', 'a.in', 0))

    def test_entry_is_none_for_a_port_no_table_declares(self):
        graph = self._graph({'a': self._dev('a', [], ports=['out'])})
        self.assertIsNone(graph.entry('a.out'))

    def test_a_port_entering_two_tables_is_REFUSED(self):
        """ `port -> table` being a function is what lets a jump resolve in one
        pass; measured true on every benchmark, and checked rather than
        assumed. """
        device = {'tables': {'a.t0': [self._rule(in_ports=['a.in'])],
                             'a.t1': [self._rule(in_ports=['a.in'])]},
                  'ports': [], 'wiring': []}
        with self.assertRaises(ValueError):
            self._graph({'a': device})

    def test_duplicate_wiring_is_tolerated(self):
        """ FaVe replays a device's wiring once per add_wiring call -- wl_ifi's
        router arrives twice -- so duplicates are expected, not exceptional. """
        device = self._dev('a', [], wiring=[('a.x', 'a.y'), ('a.x', 'a.y')])
        self.assertIsNotNone(self._graph({'a': device}))

    def test_contradictory_wiring_is_REFUSED(self):
        device = self._dev('a', [], wiring=[('a.x', 'a.y'), ('a.x', 'a.z')])
        with self.assertRaises(ValueError):
            self._graph({'a': device})

    def test_edges_chain_egress_to_ingress_to_entry(self):
        devices = {'a': self._dev('a', [self._rule(in_ports=['a.in'],
                                                   forwards=['a.out'])],
                                  ports=['in', 'out']),
                   'b': self._dev('b', [self._rule(in_ports=['b.in'])],
                                  ports=['in'])}
        edges = self._graph(devices, [('a.out', 'b.in')]).edges()
        self.assertIn(('favenet_a_out_out', 'favenet_b_in_in'), edges)
        self.assertIn(('favenet_b_in_in', rule_key('b', 'b.t0', 'b.in', 0)), edges)

    def test_intra_device_wiring_produces_the_same_shape_as_a_link(self):
        """ wl_up declares its pipeline as wiring, wl_stanford spreads the same
        pipeline across devices joined by links. Both must resolve identically
        or the translator would be workload-shaped after all. """
        devices = {'a': self._dev('a', [self._rule(in_ports=['a.mid'])],
                                  wiring=[('a.x', 'a.mid')])}
        edges = self._graph(devices).edges()
        self.assertIn(('favenet_a_x_out', 'favenet_a_mid_in'), edges)
        self.assertIn(('favenet_a_mid_in', rule_key('a', 'a.t0', 'a.mid', 0)), edges)

    def test_edges_are_deduplicated(self):
        devices = {'a': self._dev('a', [self._rule(in_ports=['a.in'])])}
        edges = self._graph(devices, [('a.out', 'a.in'), ('a.out', 'a.in')]).edges()
        self.assertEqual(len(edges), len(set(edges)))

    def test_a_referenced_but_undeclared_port_still_gets_an_interface(self):
        """ FaVe names a router's pipeline ports without listing them in
        `ports`. A jump to a node that does not exist is a dead end that looks
        exactly like a legitimate refutation, so they are included. """
        devices = {'a': self._dev('a', [self._rule(in_ports=['a.in'],
                                                   forwards=['a.undeclared'])])}
        self.assertIn('undeclared', self._graph(devices).ports_of('a'))


class TestModelToConfig(unittest.TestCase):
    """ The whole model, asserted by BUILDING it and solving -- the first point
    in the translator where a verdict, rather than a shape, is available. """

    @staticmethod
    def _dev(name, rules, ports=(), wiring=()):
        return {'tables': {name + '.t0': list(rules)},
                'ports': list(ports), 'wiring': list(wiring)}

    @staticmethod
    def _fwd(name, dst, out, idx=0):
        return Rule(name, name + '.t0', idx, in_ports=[name + '.in'],
                    match=Match([RuleField('packet.ipv4.destination', dst)]
                                if dst else []),
                    actions=[Forward([out])] if out else [])

    def _chain(self, b_dst):
        """ a --10.0.0.0/8--> b --<b_dst>--> c """
        devices = {
            'a': self._dev('a', [self._fwd('a', '10.0.0.0/8', 'a.out')], ['in', 'out']),
            'b': self._dev('b', [self._fwd('b', b_dst, 'b.out')], ['in', 'out']),
            'c': self._dev('c', [self._fwd('c', None, None)], ['in']),
        }
        from ad6.translate import model_to_config, instantiate_base
        from src.core.instantiator import Instantiator
        from src.solver.pycosat import PycoSATAdapter
        from src.xml.xmlutils import XMLUtils
        config, edges = model_to_config(devices, [('a.out', 'b.in'), ('b.out', 'c.in')])
        XMLUtils.deannotate(config)
        kripke, encoding = instantiate_base(config, edges, inits=['favenet_a_in_in'])
        solver = PycoSATAdapter()
        return lambda target: bool(solver.Solve(
            Instantiator.InstantiateReach(kripke, encoding, target)))

    def test_a_consistent_chain_is_reachable_end_to_end(self):
        reaches = self._chain('10.0.0.0/24')
        for device in ('a', 'b', 'c'):
            with self.subTest(device=device):
                self.assertTrue(reaches(rule_key(device, device + '.t0', device + '.in', 0)))

    def test_a_chain_with_DISJOINT_matches_is_REFUTED(self):
        """ The test that matters. Any translator can make things reachable --
        dropping a constraint does it. This asserts the model still says NO
        when the two hops cannot agree on a packet. """
        reaches = self._chain('192.168.0.0/16')
        self.assertTrue(reaches(rule_key('a', 'a.t0', 'a.in', 0)))
        self.assertFalse(reaches(rule_key('c', 'c.t0', 'c.in', 0)),
                         "c must be unreachable: no packet matches both "
                         "10.0.0.0/8 and 192.168.0.0/16")

    def test_a_missing_link_refutes(self):
        """ Reachability must come from the declared topology, not from nodes
        happening to exist in one config. """
        devices = {
            'a': self._dev('a', [self._fwd('a', '10.0.0.0/8', 'a.out')], ['in', 'out']),
            'b': self._dev('b', [self._fwd('b', None, None)], ['in']),
        }
        from ad6.translate import model_to_config, instantiate_base
        from src.core.instantiator import Instantiator
        from src.solver.pycosat import PycoSATAdapter
        from src.xml.xmlutils import XMLUtils
        config, edges = model_to_config(devices, [])        # no link at all
        XMLUtils.deannotate(config)
        kripke, encoding = instantiate_base(config, edges, inits=['favenet_a_in_in'])
        solver = PycoSATAdapter()
        self.assertFalse(bool(solver.Solve(
            Instantiator.InstantiateReach(kripke, encoding,
                                          rule_key('b', 'b.t0', 'b.in', 0)))))

    def test_the_config_declares_a_firewall_and_a_node_per_device(self):
        devices = {'a': self._dev('a', [self._fwd('a', None, None)], ['in'])}
        from ad6.translate import model_to_config
        config, _edges = model_to_config(devices, [])
        self.assertEqual(len(config.xpath('//*[local-name()="firewall"][@key]')), 1)
        self.assertEqual(len(config.xpath('//*[local-name()="node"]')), 1)

    def test_the_mutable_set_is_computed_across_EVERY_device(self):
        """ A field rewritten on one device must be matched node-scoped on all
        of them, or the same field resolves against a global alias in one place
        and an SSA copy in another (§9.6). """
        rewriter = Rule('a', 'a.t0', 0, in_ports=['a.in'], match=Match([]),
                        actions=[Rewrite([RuleField('packet.ether.vlan', '10')]),
                                 Forward(['a.out'])])
        matcher = Rule('b', 'b.t0', 0, in_ports=['b.in'],
                       match=Match([RuleField('packet.ether.vlan', '10')]),
                       actions=[])
        devices = {'a': self._dev('a', [rewriter], ['in', 'out']),
                   'b': self._dev('b', [matcher], ['in'])}
        from ad6.translate import model_to_config
        config, _edges = model_to_config(devices, [('a.out', 'b.in')])
        xml = et.tostring(config).decode()
        self.assertIn('<fieldmatch field="vlan">10</fieldmatch>', xml,
                      "b's VLAN match must be node-scoped because a REWRITES vlan")


class TestGeneratorsAndProbes(unittest.TestCase):
    """ Neither gets a mechanism of its own: a generator is a device with one
    rule that forwards to its own port, a probe a device with one terminal
    rule, and the topology's existing links carry both. These tests assert that
    -- and then assert the model still REFUTES, which is the only way to tell a
    correct translation from a permissive one. """

    @staticmethod
    def _router(dst=None, vlan_admit=None):
        match = []
        if dst:
            match.append(RuleField('packet.ipv4.destination', dst))
        if vlan_admit is not None:
            match.append(RuleField('packet.ether.vlan', str(vlan_admit)))
        return {'tables': {'r.t0': [Rule('r', 'r.t0', 0, in_ports=['r.in'],
                                         match=Match(match),
                                         actions=[Forward(['r.out'])])]},
                'ports': ['in', 'out'], 'wiring': []}

    def _reaches(self, devices, links, source, probe):
        from ad6.translate import (model_to_config, instantiate_base,
                                   generator_entry_key, probe_entry_key)
        from src.core.instantiator import Instantiator
        from src.solver.pycosat import PycoSATAdapter
        from src.xml.xmlutils import XMLUtils
        config, edges = model_to_config(devices, links)
        XMLUtils.deannotate(config)
        kripke, encoding = instantiate_base(
            config, edges, inits=[generator_entry_key(source)],
            mutable_fields={'vlan': 12})
        solver = PycoSATAdapter()
        return bool(solver.Solve(Instantiator.InstantiateReach(
            kripke, encoding, probe_entry_key(probe))))

    def _wire(self, generator, probe, router=None):
        from ad6.translate import generator_device, probe_device
        devices = {'r': router if router is not None else self._router()}
        devices['source.a'] = generator
        devices['probe.b'] = probe
        return devices, [('source.a.1', 'r.in'), ('r.out', 'probe.b.1')]

    # --- shape ---------------------------------------------------------

    def test_a_generator_has_no_in_ports(self):
        """ Load-bearing, not incidental: ad6's INIT exemption only applies to
        a node with NO predecessors, and every real device entry point has one
        once the topology is wired. A generator that could be pointed into
        would not be usable as a query source at all. """
        from ad6.translate import generator_device
        device = generator_device('source.a')
        rule = list(device['tables'].values())[0][0]
        self.assertFalse(rule.in_ports)

    def test_a_generator_forwards_to_its_own_port(self):
        from ad6.translate import generator_device
        device = generator_device('source.a')
        rule = list(device['tables'].values())[0][0]
        self.assertEqual([p for a in rule.actions
                          for p in (getattr(a, 'ports', None) or [])],
                         ['source.a.1'])

    def test_a_probe_receives_on_its_own_port_and_terminates(self):
        """ Owner decision 2026-09-13: a probe ACCEPTS ANY incoming traffic.
        Filtering can come later, when a benchmark needs it -- and
        probe_device's docstring records what adding it requires, because a
        condition on a terminal rule would be silently ignored
        (instantiatortest.TerminalConditionTest). """
        from ad6.translate import probe_device
        device = probe_device('probe.b')
        rule = list(device['tables'].values())[0][0]
        self.assertEqual(rule.in_ports, ['probe.b.1'])
        self.assertEqual(rule.match, [])
        self.assertEqual(rule.actions, [])

    def test_a_probe_takes_no_field_arguments(self):
        """ Filtering is deliberately absent rather than accidentally missing:
        passing fields must fail loudly, not be silently ignored. """
        from ad6.translate import probe_device
        with self.assertRaises(TypeError):
            probe_device('probe.b', {'packet.ipv4.destination': []})

    # --- verdicts ------------------------------------------------------

    def test_a_consistent_source_to_probe_path_is_reachable(self):
        from ad6.translate import generator_device, probe_device
        devices, links = self._wire(generator_device('source.a'),
                                    probe_device('probe.b'),
                                    self._router(dst='10.0.0.0/8'))
        self.assertTrue(self._reaches(devices, links, 'source.a', 'probe.b'))

    def test_a_generator_constraint_DISJOINT_from_the_path_is_REFUTED(self):
        """ The generator's own match has to constrain the packet, not decorate
        it: a source that may only emit 192.168/16 cannot reach a probe behind
        a router that forwards only 10/8. """
        from ad6.translate import generator_device, probe_device
        generator = generator_device('source.a', {'packet.ipv4.destination': [
            RuleField('packet.ipv4.destination', '192.168.0.0/16')]})
        devices, links = self._wire(generator, probe_device('probe.b'),
                                    self._router(dst='10.0.0.0/8'))
        self.assertFalse(self._reaches(devices, links, 'source.a', 'probe.b'))

    def test_a_probe_accepts_whatever_the_network_delivers(self):
        """ The probe itself never refutes. Every refutation in this suite comes
        from the PATH -- a generator's own constraint, a device's match, a
        missing link -- which is what "the probe accepts any incoming traffic"
        means operationally. """
        from ad6.translate import generator_device, probe_device
        devices, links = self._wire(generator_device('source.a'),
                                    probe_device('probe.b'),
                                    self._router(dst='10.0.0.0/8'))
        self.assertTrue(self._reaches(devices, links, 'source.a', 'probe.b'))

    def test_a_generators_MUTABLE_field_is_rewritten_not_merely_matched(self):
        """ AD6_PLAN.md §5.4 B2, the subtlest thing here. A source declaring
        VLAN 48 against a device admitting only VLAN 10 must be REFUTED. If the
        generator's VLAN were an ordinary match, it would leave the field a free
        SSA variable that the admission check could satisfy by picking 10 --
        silently reporting reachable. The rewrite is what pins it. """
        from ad6.translate import generator_device, probe_device
        # `mutable` is what the caller computed over the whole model; the
        # router below rewrites nothing, so VLAN is mutable only because the
        # generator sets it -- exactly the case that must still work.
        generator = generator_device(
            'source.a',
            {'packet.ether.vlan': [RuleField('packet.ether.vlan', '48')]},
            mutable={'packet.ether.vlan'})
        devices, links = self._wire(generator, probe_device('probe.b'),
                                    self._router(vlan_admit=10))
        self.assertFalse(self._reaches(devices, links, 'source.a', 'probe.b'),
                         "a source tagged 48 must not reach a device admitting "
                         "only 10 -- the generator's VLAN is not pinned")

    def test_a_matching_mutable_field_still_reaches(self):
        """ The control for the test above: pinning must refute the wrong tag
        without refuting the right one. """
        from ad6.translate import generator_device, probe_device
        generator = generator_device(
            'source.a',
            {'packet.ether.vlan': [RuleField('packet.ether.vlan', '10')]},
            mutable={'packet.ether.vlan'})
        devices, links = self._wire(generator, probe_device('probe.b'),
                                    self._router(vlan_admit=10))
        self.assertTrue(self._reaches(devices, links, 'source.a', 'probe.b'))

    def test_an_unconstrained_generator_field_adds_no_condition(self):
        """ FaVe spells "any source address" as 0.0.0.0/0 (every benchmark's
        generators do), which must not become a real constraint. """
        from ad6.translate import generator_device, probe_device, model_to_config
        generator = generator_device('source.a', {'packet.ipv4.source': [
            RuleField('packet.ipv4.source', '0.0.0.0/0')]})
        devices, links = self._wire(generator, probe_device('probe.b'),
                                    self._router(dst='10.0.0.0/8'))
        config, _edges = model_to_config(devices, links)
        generator_xml = et.tostring(
            config.xpath('//*[local-name()="firewall"][@key="fw_source_a"]')[0]).decode()
        self.assertNotIn('<address>', generator_xml)
        self.assertTrue(self._reaches(devices, links, 'source.a', 'probe.b'))

    def test_a_probe_with_no_link_is_unreachable(self):
        from ad6.translate import generator_device, probe_device
        devices, _links = self._wire(generator_device('source.a'),
                                     probe_device('probe.b'),
                                     self._router(dst='10.0.0.0/8'))
        self.assertFalse(self._reaches(devices, [('source.a.1', 'r.in')],
                                       'source.a', 'probe.b'))
