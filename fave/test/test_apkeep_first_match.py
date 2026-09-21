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

""" A forwarding table decides which APKeep element it becomes, by its RULES.

THE DEFECT THIS PINS. APKeep's ForwardElement is a destination-prefix trie, and
`_translate_fwd_rule` translated every forwarding table into one -- dropping any
source, protocol or port the rules matched, dropping any header rewrite, and
replacing the rule ORDER with the prefix length. On a pure FIB that is exactly
right. On wl_cloud's leaves, whose tables read

    1  dst=10.0.6.128/25, proto=6, dport=332  -> forward to the hosts
    2  dst=10.0.6.128/25                      -> drop
    3  (default)                              -> forward upstream

it produced a forward and a drop on the same prefix at the same priority, and
which one survived was the engine's business rather than the policy's. It kept
the drop: nothing in the datacenter reached anything, and the run still reported
a number (CLOUD_BENCH_PLAN.md §1.7.3).

WHY THESE TESTS AND NOT A REACHABILITY RUN. The differential against NetPlumber
(`test_apkeep_cloud_differential.py`) is what says the answers are right; these
say WHY, one property at a time, so a regression names its own cause. They also
cover the two refusals, which no reachability run can reach -- a refusal has no
number to compare.
"""

import unittest

from types import SimpleNamespace

from rule.rule_model import Rule, Match, RuleField, Forward, Rewrite
from apkeep.adapter import APKeepAdapter, available, _is_dst_lpm_table
from test.backend_gate import require_or_skip

_DST = 'packet.ipv4.destination'
_SRC = 'packet.ipv4.source'
_PROTO = 'packet.ipv6.proto'
_DPORT = 'packet.upper.dport'
_SPORT = 'packet.upper.sport'
_RELATED = 'related'


def _logger():
    import logging
    log = logging.getLogger("test_apkeep_first_match")
    log.setLevel(logging.WARNING)
    return log


def _rule(device, idx, match, actions):
    return Rule(device, device + '.1', idx, [device + '.1'],
                Match(match), actions)


def _leaf():
    """ wl_cloud's leaf-ingress table, in miniature: permit one service into the
    prefix, deny the rest of the prefix, default upstream. """
    return SimpleNamespace(node='leaf', tables={'leaf.1': [
        _rule('leaf', 1, [RuleField(_DST, '10.0.6.128/25'),
                          RuleField(_PROTO, 6),
                          RuleField(_DPORT, 332)], [Forward(['leaf.9001'])]),
        _rule('leaf', 2, [RuleField(_DST, '10.0.6.128/25')], []),
        _rule('leaf', 3, [], [Forward(['leaf.9002'])]),
    ]})


def _gateway():
    """ A DNAT: one public /32 on one port, rewritten onto a whole subnet. """
    return SimpleNamespace(node='gw', tables={'gw.1': [
        _rule('gw', 1, [RuleField(_SRC, '10.0.0.0/8')], []),
        _rule('gw', 2, [RuleField(_DST, '121.140.254.1/32'),
                        RuleField(_PROTO, 6),
                        RuleField(_DPORT, 332)],
              [Rewrite([RuleField(_DST, '10.0.4.0/22')]),
               Forward(['gw.8001'])]),
    ]})


def _fib():
    """ A pure destination FIB -- the shape the ForwardElement is for. """
    return SimpleNamespace(node='core', tables={'core.1': [
        _rule('core', 1, [RuleField(_DST, '10.0.4.0/25')], [Forward(['core.1'])]),
        _rule('core', 2, [RuleField(_DST, '10.0.0.0/22')], [Forward(['core.2'])]),
    ]})


def _adapter(*models):
    adapter = APKeepAdapter(_logger(), faithful_vlan=False, engine='bdd')
    for model in models:
        adapter.add_tables(model)
        adapter.add_rules(model)
    return adapter


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestWhichElementATableBecomes(unittest.TestCase):
    """ Decided by what the rules match, never by what the device is called. """

    def test_a_table_matching_only_the_destination_is_a_FIB(self):
        adapter = _adapter(_fib())
        self.assertTrue(_is_dst_lpm_table(adapter._fwd_table['core']))
        self.assertEqual(adapter._first_match_devices(), set())

    def test_a_table_matching_a_protocol_or_port_is_NOT_a_FIB(self):
        adapter = _adapter(_leaf())
        self.assertFalse(_is_dst_lpm_table(adapter._fwd_table['leaf']))
        self.assertEqual(adapter._first_match_devices(), {'leaf'})

    def test_a_table_that_rewrites_an_address_is_NOT_a_FIB(self):
        adapter = _adapter(_gateway())
        self.assertFalse(_is_dst_lpm_table(adapter._fwd_table['gw']))
        self.assertEqual(adapter._first_match_devices(), {'gw'})

    def test_the_decision_is_per_device(self):
        """ A model may hold both kinds, and each keeps its own element: the
        leaf tables carry ACLs, the cores are plain FIBs, and turning the cores
        into first-match lists as well would cost the trie for nothing. """
        adapter = _adapter(_fib(), _leaf(), _gateway())
        self.assertEqual(adapter._first_match_devices(), {'leaf', 'gw'})

    def test_an_HSA_STAGE_keeps_its_own_treatment(self):
        """ The one exemption. wl_stanford's and wl_i2's in./mid./out. tables
        carry VLAN matches and are rewritten by the collapse paths, which is a
        decision taken elsewhere; a second treatment here would conflict with
        it. Independent of `faithful_vlan`, because the plain path claims the
        same tables. """
        staged = _leaf()
        staged.node = 'in.bbra_rtr'
        staged.tables = {'in.bbra_rtr.1': [
            _rule('in.bbra_rtr', r.idx, list(r.match), r.actions)
            for r in staged.tables['leaf.1']]}
        adapter = _adapter(staged)
        self.assertFalse(_is_dst_lpm_table(adapter._fwd_table['in.bbra_rtr']))
        self.assertEqual(adapter._first_match_devices(), set())

    def test_renaming_the_devices_changes_nothing(self):
        """ The property this whole change exists for. §1.7.3 diagnosed the
        original failure as device-name coupling, and a name-keyed fix would
        have been the same defect with a longer list of prefixes. """
        leaf = _leaf()
        leaf.node = 'mysterious'
        leaf.tables = {'mysterious.1': [
            _rule('mysterious', r.idx, list(r.match), r.actions)
            for r in leaf.tables['leaf.1']]}
        adapter = _adapter(leaf)
        self.assertEqual(adapter._first_match_devices(), {'mysterious'})


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestTheRuleOrderSurvives(unittest.TestCase):
    """ The point of a first-match table: rule 1 outranks rule 2. """

    @classmethod
    def setUpClass(cls):
        adapter = _adapter(_leaf())
        cls.rules, cls.nats, cls.nat_rules = adapter._build_first_match_tables(
            {'leaf'})

    def test_every_rule_is_emitted(self):
        self.assertEqual(len(self.rules), 3)

    def test_the_permit_outranks_the_deny_on_the_same_prefix(self):
        """ Both match 10.0.6.128/25. Under the dst-LPM translation they had
        the same priority (the prefix length) and the drop won. """
        by_out = dict((r.split()[5], int(r.split()[16])) for r in self.rules)
        self.assertGreater(by_out['9001'], by_out['__drop__'])

    def test_the_default_route_ranks_last(self):
        priorities = [int(r.split()[16]) for r in self.rules]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_the_matched_fields_are_all_carried(self):
        """ proto 6, dport 332 and the destination prefix, in the one rule that
        had them -- the three the dst-LPM translation dropped. """
        permit = [r for r in self.rules if r.split()[5] == '9001'][0]
        tokens = permit.split()
        self.assertEqual((tokens[6], tokens[7]), ('6', '6'))       # proto
        self.assertEqual((tokens[12], tokens[13]),
                         ('10.0.6.128', '0.0.0.127'))              # dst /25
        self.assertEqual((tokens[14], tokens[15]), ('332', '332'))  # dport

    def test_a_rule_with_no_forward_action_drops(self):
        deny = [r for r in self.rules if r.split()[5] == '__drop__'][0]
        self.assertEqual(deny.split()[12], '10.0.6.128')


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestAnAddressRewriteBecomesANAT(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        adapter = _adapter(_gateway())
        cls.rules, cls.nats, cls.nat_rules = adapter._build_first_match_tables(
            {'gw'})

    def test_the_nat_sits_on_the_egress_port(self):
        self.assertEqual(self.nats, {'gw': {'8001'}})

    def test_it_names_the_field_it_rewrites_and_the_value(self):
        self.assertEqual(len(self.nat_rules), 1)
        tokens = self.nat_rules[0].split()
        self.assertEqual(tokens[:8],
                         ['+', 'nat', 'gw', '8001', 'match', 'dst',
                          '10.0.4.0', '22'])

    def test_it_is_keyed_on_the_WHOLE_match_not_the_address(self):
        """ Two of wl_cloud's source rewrites leave the same port with the same
        source /24 and differ only in tcp_src. Keyed on the address alone they
        would be one rule twice, rewriting to two different public addresses,
        and which won would be an accident. """
        body = self.nat_rules[0].split(' ', 8)[8].split()
        self.assertEqual((body[3], body[4]), ('6', '6'))            # proto
        self.assertEqual((body[11], body[12]), ('332', '332'))      # dport
        self.assertEqual(body[9], '121.140.254.1')                  # dst /32

    def test_a_dropping_rule_gets_no_nat(self):
        """ The gateway's anti-spoofing rule rewrites nothing and forwards
        nowhere; a NAT on the drop sink would rewrite traffic that is gone. """
        self.assertNotIn('__drop__', [r.split()[3] for r in self.nat_rules])


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestWhatItCannotExpressIsRefused(unittest.TestCase):
    """ Never emitted without the part that could not be carried. """

    def test_an_unexpressible_match_is_refused(self):
        model = SimpleNamespace(node='odd', tables={'odd.1': [
            _rule('odd', 1, [RuleField(_PROTO, 6),
                             RuleField('packet.ether.source', '00:11:22:33:44:55')],
                  [Forward(['odd.2'])]),
        ]})
        adapter = _adapter(model)
        with self.assertRaises(ValueError) as caught:
            adapter._build_first_match_tables({'odd'})
        self.assertIn('packet.ether.source', str(caught.exception))

    def test_an_unexpressible_rewrite_is_refused(self):
        model = SimpleNamespace(node='odd', tables={'odd.1': [
            _rule('odd', 1, [RuleField(_PROTO, 6)],
                  [Rewrite([RuleField(_DPORT, 8080)]), Forward(['odd.2'])]),
        ]})
        adapter = _adapter(model)
        with self.assertRaises(ValueError) as caught:
            adapter._build_first_match_tables({'odd'})
        self.assertIn(_DPORT, str(caught.exception))


def _generator(node, **fields):
    return SimpleNamespace(
        node=node,
        fields=dict((name, [RuleField(name, value)])
                    for name, value in fields.items()))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestASourceEmitsWhatItsGeneratorInjects(unittest.TestCase):
    """ A generator states what the source emits, and the query has to ask about
    that traffic and no more.

    The seed element used to carry the source ADDRESS alone, which sufficed
    while every workload injected only that. wl_cloud's matrix phase injects
    `tcp_src` too -- one per service endpoint -- and its leaf tables match on it,
    so ignoring it asked a broader question and reported **1,608 violations
    against NetPlumber's 1,315**, every one of the 293 an invented pair. """

    def _seed_rule(self, generator):
        adapter = _adapter(_fib())
        adapter.add_generator(generator)
        adapter.add_link('%s.1' % generator.node, 'core.1')
        _edges, elems, rules = adapter._source_seed_filters(adapter._edges)
        return elems, rules

    def test_an_injected_source_port_reaches_the_seed(self):
        elems, rules = self._seed_rule(_generator(
            'source.svc', **{_SRC: '10.0.0.0/25', _SPORT: 350}))
        self.assertEqual(elems, ['source.svc.sf'])
        tokens = rules[0].split()
        self.assertEqual((tokens[8], tokens[9]), ('10.0.0.0', '0.0.0.127'))
        self.assertEqual((tokens[10], tokens[11]), ('350', '350'))

    def test_a_full_space_address_constrains_nothing(self):
        """ wl_stanford's generators inject `ipv4_dst=0.0.0.0/0`, and the
        internet's source is unconstrained on purpose. Splicing an element for
        those would cost a partition split to say nothing. """
        elems, rules = self._seed_rule(_generator(
            'source.internet', **{_DST: '0.0.0.0/0'}))
        self.assertEqual((elems, rules), ([], []))

    def test_an_injected_field_it_cannot_express_is_refused(self):
        adapter = _adapter(_fib())
        with self.assertRaises(ValueError) as caught:
            adapter.add_generator(_generator(
                'source.odd', **{'packet.ether.source': '00:11:22:33:44:55'}))
        self.assertIn('packet.ether.source', str(caught.exception))


@require_or_skip(available(), "JPype or the APKeep jar is unavailable")
class TestACheckConditionIsForcedOrRefused(unittest.TestCase):
    """ The conditions an FPL check set carries beyond `related`. """

    def test_a_protocol_and_a_port_become_arrival_constraints(self):
        adapter = _adapter(_fib())
        related, conds = adapter._query_conditions(
            [RuleField(_PROTO, 6), RuleField(_DPORT, 332)], 's', 'p')
        self.assertIsNone(related)
        self.assertEqual([negated for _r, negated in conds], [False, False])
        proto, dport = (r.split() for r, _n in conds)
        self.assertEqual((proto[6], proto[7]), ('6', '6'))
        self.assertEqual((dport[14], dport[15]), ('332', '332'))

    def test_a_negated_condition_keeps_its_negation(self):
        adapter = _adapter(_fib())
        field = RuleField(_DPORT, 331)
        field.negated = True
        _related, conds = adapter._query_conditions([field], 's', 'p')
        self.assertEqual([negated for _r, negated in conds], [True])

    def test_related_still_goes_its_own_way(self):
        adapter = _adapter(_fib())
        related, conds = adapter._query_conditions(
            [RuleField(_RELATED, 0), RuleField(_PROTO, 6)], 's', 'p')
        self.assertEqual(related, 0)
        self.assertEqual(len(conds), 1)

    def test_a_condition_on_a_field_THIS_MODEL_REWRITES_is_refused(self):
        """ The condition is forced on the traffic ARRIVING at the probe, which
        is the check as written only while nothing rewrites the field. The
        gateway rewrites the destination, so a destination-conditioned check on
        this model is a different question and is refused rather than answered. """
        adapter = _adapter(_gateway())
        with self.assertRaises(ValueError) as caught:
            adapter._query_conditions([RuleField(_DST, '10.0.4.1/32')], 's', 'p')
        self.assertIn('REWRITES', str(caught.exception))

    def test_a_field_neither_engine_carries_is_refused(self):
        adapter = _adapter(_fib())
        with self.assertRaises(ValueError) as caught:
            adapter._query_conditions(
                [RuleField('packet.ether.vlan', 7)], 's', 'p')
        self.assertIn('packet.ether.vlan', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
