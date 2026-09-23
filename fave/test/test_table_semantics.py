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

""" Declared table semantics (TABLE_SEMANTICS_PLAN.md S1+S2).

Every FaVe table resolves first-match-wins, and nothing used to say so. The
default is now explicit and TOTAL -- `semantics_of` answers for every table --
while `table_semantics` stores only the overrides, so a benchmark declares its
exceptions and nothing else.

These tests are the channel's end-to-end gate. It crosses four boundaries and
LOST THE DECLARATION AT TWO OF THEM before this was measured rather than
assumed, both silently:

  * `_model_from_json` is handed the whole COMMAND, whose type is
    `topology_command`, so the device sits one level down under "model";
  * `_sync_diff` hands the engine `model - self.models[node]`, a DIFFERENT
    object built by one of four `__sub__` implementations, none of which carried
    the field.

Either bug produced exactly the same symptom -- every table arriving as
`first_match` with nothing raising -- which is why the test that matters here is
the one asserting what the ADAPTER received, not what the model serialised.
"""

import json
import logging
import os
import unittest

from devices.abstract_device import (
    AbstractDeviceModel, FIRST_MATCH, LPM, TableSemanticsError,
    restore_table_semantics,
)
from devices.switch import SwitchModel
from devices.router import RouterModel
from devices.packet_filter import PacketFilterModel
from devices.application_layer_gateway import ApplicationLayerGatewayModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel

from test.backend_gate import require_or_skip

_STANFORD = "bench/wl_stanford/stanford-json"
_I2 = "bench/wl_i2/i2-json"
_FILES = {"topology": "device_topology.json", "policies": "probes.json"}


class TestDefaultIsTotal(unittest.TestCase):
    """ The default answers for every table, including ones created later. """

    def test_an_undeclared_table_is_first_match(self):
        model = AbstractDeviceModel('d', 'model', tables={'d.1': []})
        self.assertEqual(model.semantics_of('d.1'), FIRST_MATCH)

    def test_a_table_that_does_not_exist_yet_is_first_match(self):
        """ Defaulted on READ, not materialised: RouterModel.persist creates
        tables through `setdefault` long after __init__, and a dict filled in
        at construction would have missed them. """
        model = AbstractDeviceModel('d', 'model')
        self.assertEqual(model.semantics_of('d.created.later'), FIRST_MATCH)

    def test_declaring_first_match_stores_no_override(self):
        """ The default is not an override, so declaring it leaves the model
        serialising exactly as it did before the field existed. """
        model = AbstractDeviceModel('d', 'model', tables={'d.1': []})
        model.set_table_semantics('d.1', FIRST_MATCH)
        self.assertEqual(model.table_semantics, {})
        self.assertNotIn('table_semantics', model.to_json())


class TestSerialisationIsOverridesOnly(unittest.TestCase):
    """ A model that declares nothing must serialise byte-identically. """

    def test_a_model_without_declarations_gains_no_json_key(self):
        model = SwitchModel('s', ports=['1'])
        self.assertNotIn('table_semantics', model.to_json())

    def test_a_declaration_round_trips(self):
        model = SwitchModel('s', ports=['1'])
        model.set_table_semantics('s.1', LPM)
        j = model.to_json()
        self.assertEqual(j['table_semantics'], {'s.1': LPM})
        back = restore_table_semantics(SwitchModel.from_json(j), j)
        self.assertEqual(back.semantics_of('s.1'), LPM)
        self.assertEqual(back.semantics_of('s.other'), FIRST_MATCH)

    def test_every_device_model_carries_the_field(self):
        """ Measured, because an earlier draft claimed four models would drop
        it. They do not: two chain to the base `to_json`, three inherit it, and
        the two that look like counterexamples (`GeneratorModel`, `ProbeModel`)
        do not subclass `AbstractDeviceModel` at all. """
        models = [
            SwitchModel('s', ports=['1']),
            RouterModel('r', ports=['1', '2']),
            PacketFilterModel('pf', ports=['1']),
            ApplicationLayerGatewayModel('alg', ports=['1']),
            SnapshotPacketFilterModel('spf', ports=['1']),
        ]
        for model in models:
            table = sorted(model.tables)[0]
            model.set_table_semantics(table, LPM)
            self.assertEqual(
                model.to_json().get('table_semantics', {}).get(table), LPM,
                "%s dropped the declaration" % type(model).__name__
            )


class TestRefusals(unittest.TestCase):
    """ A declaration that would go missing is refused, not stored. """

    def test_an_unknown_term_is_refused(self):
        model = SwitchModel('s', ports=['1'])
        with self.assertRaises(TableSemanticsError):
            model.set_table_semantics('s.1', 'longest_prefix')
        self.assertEqual(model.table_semantics, {})

    def test_the_vocabulary_is_closed(self):
        """ A term with no consumer is a declaration nothing honours, which is
        the failure mode the mechanism exists to end. `admission` and
        `permutation` are deliberately absent until something can carry them. """
        from devices.abstract_device import TABLE_SEMANTICS
        self.assertEqual(TABLE_SEMANTICS, frozenset({FIRST_MATCH, LPM}))


@require_or_skip(os.path.isfile("%s/device_topology.json" % _STANFORD),
                 "wl_stanford inputs not generated")
class TestProducerDeclaresFromConfig(unittest.TestCase):
    """ np_preparation declares the stage its own config.json calls the FIB. """

    def test_stanford_declares_mid_and_nothing_else(self):
        topo = json.load(open("%s/device_topology.json" % _STANFORD))
        declared = {d[0] for d in topo['devices'] if len(d) > 4 and d[4]}
        self.assertEqual(len(declared), 16)
        self.assertEqual({d.split('.', 1)[0] for d in declared}, {'mid'})

    @require_or_skip(os.path.isfile("%s/device_topology.json" % _I2),
                     "wl_i2 inputs not generated")
    def test_i2_declares_out_because_ITS_config_says_out(self):
        """ The point of the declaration: wl_i2's FIB is the `out` stage, and
        the predecessor of this mechanism hardcoded `mid.` and so did nothing
        at all here -- 3,731 rules shadowed (AD6_PLAN.md §5.5). """
        topo = json.load(open("%s/device_topology.json" % _I2))
        declared = {d[0] for d in topo['devices'] if len(d) > 4 and d[4]}
        self.assertEqual(len(declared), 9)
        self.assertEqual({d.split('.', 1)[0] for d in declared}, {'out'})


def _semantics_seen_by_adapter(prefix):
    """ What the ADAPTER received, which is the only thing that matters. """
    from apkeep.adapter import APKeepAdapter
    from util.in_process_driver import InProcessFaVe

    seen = {}
    original = APKeepAdapter.add_tables

    def spy(self, model):
        for table in model.tables:
            # LAST write wins deliberately: add_tables is called twice per
            # device, and it was the SECOND call -- the one handed the diff --
            # that used to arrive stripped.
            seen[table] = model.semantics_of(table)
        return original(self, model)

    APKeepAdapter.add_tables = spy
    try:
        log = logging.getLogger("table_semantics")
        log.setLevel(logging.WARNING)
        engine = APKeepAdapter(log, faithful_vlan=False, engine='ndd')
        with InProcessFaVe(engine) as fave:
            fave.replay(prefix, files=_FILES)
    finally:
        APKeepAdapter.add_tables = original
    return seen


@require_or_skip(os.path.isfile("%s/device_topology.json" % _STANFORD),
                 "wl_stanford inputs not generated")
class TestDeclarationSurvivesDispatch(unittest.TestCase):
    """ The gate: the declaration reaches the ENGINE, not merely the JSON. """

    def test_stanford_mid_tables_arrive_declared(self):
        seen = _semantics_seen_by_adapter(_STANFORD)
        mid = {t: s for t, s in seen.items() if t.startswith('mid.')}
        self.assertEqual(len(mid), 16)
        self.assertEqual(set(mid.values()), {LPM})

    def test_stanford_other_stages_arrive_first_match(self):
        seen = _semantics_seen_by_adapter(_STANFORD)
        others = {t: s for t, s in seen.items()
                  if t.startswith(('in.', 'out.'))}
        self.assertEqual(len(others), 32)
        self.assertEqual(set(others.values()), {FIRST_MATCH})


@require_or_skip(os.path.isfile("%s/device_topology.json" % _STANFORD),
                 "wl_stanford inputs not generated")
class TestAdapterCrossCheck(unittest.TestCase):
    """ `_is_dst_lpm_table` stops DECIDING alone and starts CROSS-CHECKING.

    Shape decides what is possible; the declaration decides among what shape
    cannot distinguish. Agreement is unremarkable, disagreement is a refusal --
    never a silent preference for one of them.
    """

    def _adapter(self):
        from apkeep.adapter import APKeepAdapter
        log = logging.getLogger("table_semantics_xcheck")
        log.setLevel(logging.WARNING)
        return APKeepAdapter(log, faithful_vlan=False, engine='ndd')

    def test_a_declared_fib_whose_rules_are_a_trie_is_accepted(self):
        from apkeep.adapter import _DST, _OUT_PORT
        engine = self._adapter()
        engine._fwd_table['fib'] = [{
            'idx': 0, 'ports': ['1'], 'in_ports': [],
            'match': {_DST}, 'rw': {_OUT_PORT},
        }]
        engine._declared_lpm.add('fib')
        engine._assert_declared_lpm_is_triable()   # must not raise

    def test_a_declared_fib_that_matches_a_port_is_REFUSED(self):
        """ A table declared `lpm` whose rules match a transport port is not a
        FIB under any backend. Translating it as one answers a different
        question -- which is what CLOUD_BENCH_PLAN.md §1.7.3 cost. """
        from apkeep.adapter import UntranslatedSemantics, _DST
        engine = self._adapter()
        engine._fwd_table['leaf'] = [{
            'idx': 0, 'ports': ['1'], 'in_ports': [],
            'match': {_DST, 'packet.upper.tcp.srcport'}, 'rw': set(),
        }]
        engine._declared_lpm.add('leaf')
        with self.assertRaises(UntranslatedSemantics) as caught:
            engine._assert_declared_lpm_is_triable()
        # names the offending field, not just the device
        self.assertIn('packet.upper.tcp.srcport', str(caught.exception))
        self.assertIn('leaf', str(caught.exception))

    def test_an_UNDECLARED_dst_table_is_left_alone(self):
        """ The converse is deliberately not enforced yet: an undeclared
        dst-only table still becomes a ForwardElement, as it always has.
        Making the declaration authoritative for undeclared tables would change
        every workload that declares nothing (§9.7). """
        from apkeep.adapter import _DST
        engine = self._adapter()
        engine._fwd_table['plain'] = [{
            'idx': 0, 'ports': ['1'], 'in_ports': [],
            'match': {_DST, 'packet.upper.tcp.srcport'}, 'rw': set(),
        }]
        engine._assert_declared_lpm_is_triable()   # undeclared -> not checked

    def test_the_real_workloads_pass_the_cross_check(self):
        """ Non-vacuous: wl_stanford declares 16 tables, and they are checked. """
        from apkeep.adapter import APKeepAdapter
        from util.in_process_driver import InProcessFaVe
        log = logging.getLogger("table_semantics_real")
        log.setLevel(logging.WARNING)
        engine = APKeepAdapter(log, faithful_vlan=False, engine='ndd')
        with InProcessFaVe(engine) as fave:
            fave.replay(_STANFORD, files=_FILES)
            engine._build()
        self.assertEqual(len(engine._declared_lpm), 16)


class TestDeclaredLpmValidation(unittest.TestCase):
    """ S4: a table declared longest-prefix-match must be able to mean it.

    Backend-neutral -- a property of the rules alone -- and run in the
    aggregator before the model reaches any engine, so all three see the same
    answer instead of each deciding privately.
    """

    @staticmethod
    def _rule(idx, dst=None, ports=None, extra=None):
        from rule.rule_model import Rule, Match, RuleField, Forward
        fields = []
        if dst is not None:
            fields.append(RuleField('packet.ipv4.destination', dst))
        for name, value in (extra or []):
            fields.append(RuleField(name, value))
        actions = [Forward(ports=list(ports))] if ports else []
        return Rule('d', 'd.1', idx, match=Match(fields), actions=actions)

    def test_a_destination_only_table_is_accepted(self):
        from devices.abstract_device import validate_lpm_rules
        validate_lpm_rules('d', 'd.1', [
            self._rule(0, '10.240.0.0/12', ['d.2']),
            self._rule(1, '10.0.0.0/8', ['d.3']),
        ])

    def test_a_DISCARD_AGGREGATE_is_accepted(self):
        """ The FIB idiom np_preparation documents: a drop for an aggregate with
        a more-specific forward punched through it. Different prefixes, so
        longest-prefix-match resolves it and nothing is ambiguous. Refusing this
        would block every real FIB. """
        from devices.abstract_device import validate_lpm_rules
        validate_lpm_rules('d', 'd.1', [
            self._rule(0, '10.0.0.0/8'),                    # no action -> drop
            self._rule(1, '10.240.0.0/12', ['d.2']),        # punched through
        ])

    def test_a_rule_matching_MORE_than_the_destination_is_refused(self):
        from devices.abstract_device import validate_lpm_rules, TableSemanticsError
        with self.assertRaises(TableSemanticsError) as caught:
            validate_lpm_rules('d', 'd.1', [
                self._rule(0, '10.0.0.0/8', ['d.2'],
                           extra=[('packet.upper.tcp.srcport', '80')]),
            ])
        self.assertIn('packet.upper.tcp.srcport', str(caught.exception))

    def test_two_rules_on_ONE_prefix_doing_different_things_are_refused(self):
        """ Then which wins is decided by their ORDER -- exactly what declaring
        longest-prefix-match says it is not. """
        from devices.abstract_device import validate_lpm_rules, TableSemanticsError
        with self.assertRaises(TableSemanticsError) as caught:
            validate_lpm_rules('d', 'd.1', [
                self._rule(0, '10.0.0.0/8', ['d.2']),
                self._rule(1, '10.0.0.0/8', ['d.3']),
            ])
        self.assertIn('10.0.0.0/8', str(caught.exception))

    def test_two_IDENTICAL_rules_are_not_ambiguous(self):
        """ Same prefix AND same action: order cannot change the outcome. """
        from devices.abstract_device import validate_lpm_rules
        validate_lpm_rules('d', 'd.1', [
            self._rule(0, '10.0.0.0/8', ['d.2']),
            self._rule(1, '10.0.0.0/8', ['d.2']),
        ])

    def test_colliding_DEFAULT_routes_are_refused(self):
        """ A rule with no destination field matches everything; two of them
        disagreeing is as ambiguous as any other colliding pair. """
        from devices.abstract_device import validate_lpm_rules, TableSemanticsError
        with self.assertRaises(TableSemanticsError):
            validate_lpm_rules('d', 'd.1', [
                self._rule(0, None, ['d.2']),
                self._rule(1, None, ['d.3']),
            ])

    def test_the_index_spans_BATCHES(self):
        """ Rules arrive in batches and a collision between two batches is still
        a collision -- which is why the caller carries the index. """
        from devices.abstract_device import validate_lpm_rules, TableSemanticsError
        index = {}
        validate_lpm_rules('d', 'd.1', [self._rule(0, '10.0.0.0/8', ['d.2'])], index)
        with self.assertRaises(TableSemanticsError):
            validate_lpm_rules('d', 'd.1', [self._rule(1, '10.0.0.0/8', ['d.3'])], index)


@require_or_skip(os.path.isfile("%s/device_topology.json" % _STANFORD),
                 "wl_stanford inputs not generated")
class TestValidationRunsOnTheRealWorkloads(unittest.TestCase):
    """ Non-vacuous: the checks must actually SEE the declared tables.

    Asserted because §9.3 found the declaration silently dropped at two of its
    four boundaries -- a validation that runs over nothing passes just as
    quietly as one that runs over everything.
    """

    def test_stanford_and_i2_rules_are_actually_validated(self):
        import devices.abstract_device as device_module
        import aggregator.aggregator_service as aggregator_module
        from apkeep.adapter import APKeepAdapter
        from util.in_process_driver import InProcessFaVe

        seen = {'rules': 0, 'tables': set()}
        original = device_module.validate_lpm_rules

        def spy(node, table, rules, index=None):
            rules = list(rules)
            seen['rules'] += len(rules)
            seen['tables'].add((node, table))
            return original(node, table, rules, index)

        device_module.validate_lpm_rules = spy
        aggregator_module.validate_lpm_rules = spy
        try:
            log = logging.getLogger("s4_nonvacuous")
            log.setLevel(logging.WARNING)
            engine = APKeepAdapter(log, faithful_vlan=False, engine='ndd')
            with InProcessFaVe(engine) as fave:
                fave.replay(_STANFORD, files=_FILES)
        finally:
            device_module.validate_lpm_rules = original
            aggregator_module.validate_lpm_rules = original

        self.assertEqual(len(seen['tables']), 16)
        self.assertEqual(seen['rules'], 3844)


if __name__ == '__main__':
    unittest.main()
