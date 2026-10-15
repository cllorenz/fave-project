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

""" util/incremental.py's verdict cache, from-zero oracle and model readers,
and util/in_process_driver.py's `replay`, on a recording engine -- pure
Python, no backend.

The workload is a tiny one written to a temporary directory by this file
(two switches, one route each, a source and a probe), so `replay` runs the
real topology.py/switch.py model building and the real aggregator. What is
pinned is what reaches the engine, and how verdicts are attributed to checks.
test_incremental_util.py covers the streams, rounds and the withholding
wrapper alone.
"""

import json
import logging
import os
import tempfile
import unittest

from types import SimpleNamespace
from unittest import mock

from aggregator.abstract_engine import UpdateRefused
from util import incremental as inc
from util.in_process_driver import InProcessFaVe


_WORKLOAD = {
    'topology.json': {
        'devices': [['sw1', 'switch', 2],
                    ['sw2', 'switch', 2]],
        'links': [['sw1.2', 'sw2.1', False]],
    },
    'routes.json': [
        ['sw1', 1, 1, ['ipv6_dst=2001:db8::1'], ['fd=sw1.2'], []],
        ['sw2', 1, 1, ['ipv6_dst=2001:db8::1'], ['fd=sw2.2'], []],
    ],
    'policies.json': {
        'devices': [['probe.p', 'probe', 'universal', None, None, None, None]],
        'links': [['sw2.2', 'probe.p.1', False]],
    },
    'sources.json': {
        'devices': [['source.s', 'generator', ['ipv6_src=2001:db8::5']]],
        'links': [['source.s.1', 'sw1.1', False]],
    },
}

_CHECK = 's=source.s && EF p=probe.p'


def _engine(violated=()):
    """ A recording engine: every call is a MagicMock call, and a compliance
    check reports `violated` (source, probe) names. """
    engine = mock.MagicMock(name='engine')
    # stable indices are on by default (§8.1): the engine declares a budget
    engine.max_rule_index.return_value = 2**20 - 1
    state = {'results': []}
    engine.check_compliance.side_effect = lambda _rules: state.__setitem__(
        'results', [(s, p, True, []) for s, p in violated])
    engine.clear_results.side_effect = lambda: state.__setitem__('results', [])
    engine.get_compliance_results.side_effect = lambda: list(state['results'])
    return engine


class _WorkloadCase(unittest.TestCase):
    """ Writes the workload to a temporary directory for the class. """

    @classmethod
    def setUpClass(cls):
        logging.getLogger('AggregatorService').setLevel(logging.CRITICAL)
        cls._tmp = tempfile.TemporaryDirectory()
        cls.prefix = cls._tmp.name
        for name, content in _WORKLOAD.items():
            with open(os.path.join(cls.prefix, name), 'w', encoding='utf-8') as out:
                json.dump(content, out)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestReplay(_WorkloadCase):
    """ `InProcessFaVe.replay` builds the workload's real models and blocks
    until the engine has them; the model readers see the built model. """

    def test_replay_builds_the_models_and_links(self):
        engine = _engine()
        with InProcessFaVe(engine) as fave:
            fave.replay(self.prefix)
            self.assertEqual(sorted(fave._agg.models), ['sw1', 'sw2'])
            rules = inc.model_rules(fave)
            links = inc.model_links(fave)

        self.assertEqual([key for key, _rule in rules],
                         [('sw1', 'sw1.1', 1), ('sw2', 'sw2.1', 1)])
        self.assertEqual([r.actions[0].ports for _k, r in rules], [['sw1.2'], ['sw2.2']])
        self.assertEqual(links, [('source.s.1', 'sw1.1'), ('sw1.2', 'sw2.1'),
                                 ('sw2.2', 'probe.p.1')])
        self.assertEqual(sorted(c.args for c in engine.add_link.call_args_list), links)
        self.assertEqual(engine.add_probe.call_args.args[0].node, 'probe.p')
        self.assertEqual([g.node for g in engine.add_generators_bulk.call_args.args[0]],
                         ['source.s'])

    def test_a_failed_device_fails_the_replay(self):
        """ The build's messages carry no barrier; a device the aggregator
        failed on used to be logged and left out, and the engine answered
        for another network. """
        engine = _engine()
        engine.add_rules.side_effect = [RuntimeError('boom')] + [None] * 100
        with InProcessFaVe(engine) as fave:
            with self.assertRaisesRegex(RuntimeError, 'failed: RuntimeError: boom'):
                fave.replay(self.prefix)

    def test_files_override_the_default_names(self):
        os.rename(os.path.join(self.prefix, 'policies.json'),
                  os.path.join(self.prefix, 'probes.json'))
        self.addCleanup(os.rename, os.path.join(self.prefix, 'probes.json'),
                        os.path.join(self.prefix, 'policies.json'))
        engine = _engine()
        with InProcessFaVe(engine) as fave:
            fave.replay(self.prefix, files={'policies': 'probes.json'})
        engine.add_probe.assert_called_once()

    def test_the_transport_is_restored_on_stop(self):
        import topology.topology as topo_mod
        before = topo_mod.fave_sendmsg
        with InProcessFaVe(_engine()):
            self.assertIsNot(topo_mod.fave_sendmsg, before)
        self.assertIs(topo_mod.fave_sendmsg, before)


class TestFromZero(_WorkloadCase):
    """ The oracle builds the CURRENT model on a fresh engine -- deleted rules
    and downed links withheld -- and asks every check once. """

    def test_withholds_and_answers(self):
        engine = _engine(violated=[('source.s', 'probe.p')])
        like = SimpleNamespace(prepare_twin=mock.MagicMock())
        verdicts = inc.from_zero(
            lambda: engine, self.prefix, [inc.Check(_CHECK)],
            deleted={('sw2', 'sw2.1', 1)}, down={('sw1.2', 'sw2.1')}, like=like)

        self.assertEqual(verdicts, {_CHECK: True})
        engine.track_affected.assert_called_once_with(True)
        like.prepare_twin.assert_called_once_with(engine)
        engine.release.assert_called_once_with()

        built = {m.node: m for m in (c.args[0] for c in engine.add_rules.call_args_list)}
        self.assertEqual([r.idx for r in built['sw1'].tables['sw1.1']], [1])
        self.assertEqual(built['sw2'].tables['sw2.1'], [])
        self.assertNotIn(('sw1.2', 'sw2.1'),
                         [c.args for c in engine.add_link.call_args_list])
        engine.check_compliance.assert_called_once()
        asked = engine.check_compliance.call_args.args[0]
        self.assertEqual(json.loads(json.dumps(asked)),
                         {'probe.p': [['source.s', False, []]]})

    def test_no_violation_reported_is_a_pass(self):
        verdicts = inc.from_zero(_engine, self.prefix,
                                 [inc.Check(_CHECK)], set(), set())
        self.assertEqual(verdicts, {_CHECK: False})


class TestModelReaders(unittest.TestCase):
    """ Single-rule updates never touch a whole-table (pre/post-routing). """

    def test_whole_tables_are_skipped(self):
        rule = SimpleNamespace(idx=3)
        model = SimpleNamespace(tables={'fw.post_routing': [rule], 'fw.pre_routing': [rule],
                                        'fw.routing': [rule]})
        fave = SimpleNamespace(_agg=SimpleNamespace(models={'fw': model}))
        self.assertEqual(inc.model_rules(fave), [(('fw', 'fw.routing', 3), rule)])

    def test_the_withholding_wrapper_writes_through(self):
        engine = SimpleNamespace()
        inc._Withholding(engine, set(), set()).global_port = 7
        self.assertEqual(engine.global_port, 7)


class TestViolatedPairs(unittest.TestCase):
    """ Engines reporting node IDS are translated back to names. """

    def test_names_pass_through(self):
        engine = SimpleNamespace(get_compliance_results=lambda: [('s', 'p', 1, [])])
        self.assertEqual(inc.violated_pairs(engine), {('s', 'p')})

    def test_ids_are_mapped_and_unknown_ids_dropped(self):
        engine = SimpleNamespace(
            get_compliance_results=lambda: [(7, 9, 1, []), (8, 9, 1, [])],
            generators={'source.s': (None, 7)}, probes={'probe.p': (None, 9)})
        self.assertEqual(inc.violated_pairs(engine), {('source.s', 'probe.p')})

    def test_nothing_reported(self):
        engine = SimpleNamespace(get_compliance_results=lambda: [])
        self.assertEqual(inc.violated_pairs(engine), set())


class _FakeFave:
    """ Answers check_compliance by setting the engine's results to the
    currently violated pairs among those asked. """

    def __init__(self, engine):
        self.engine = engine
        self.violated = set()
        self.asked = []

    def check_compliance(self, rules):
        self.asked.append(rules)
        self.engine.results = [(src, probe, True, [])
                               for probe, entries in rules.items()
                               for src, _neg, _cond in entries
                               if (src, probe) in self.violated]


class TestVerdictCache(unittest.TestCase):
    """ A verdict per check line, re-verified fully or selectively. """

    def setUp(self):
        self.engine = SimpleNamespace(results=[])
        self.engine.clear_results = lambda: setattr(self.engine, 'results', [])
        self.engine.get_compliance_results = lambda: self.engine.results
        self.fave = _FakeFave(self.engine)
        self.checks = [inc.Check(line) for line in (
            's=source.a && EF p=probe.x && f=related:0',
            's=source.a && EF p=probe.x && f=related:1',
            's=source.b && EF p=probe.x',
        )]
        self.cache = inc.VerdictCache(self.fave, self.engine, self.checks)

    def test_full_asks_each_pair_once_per_round(self):
        self.fave.violated = {('source.a', 'probe.x')}
        verdicts = self.cache.full()
        self.assertEqual(verdicts, {c.line: c.source == 'source.a' for c in self.checks})
        self.assertEqual(self.cache.asked, 3)
        self.assertEqual(len(self.fave.asked), 2)       # two rounds
        self.assertEqual(self.fave.asked[0]['probe.x'][0],
                         ['source.a', False, [{'name': 'related', 'value': '0',
                                               'negated': False}]])

    def test_selective_reasks_only_the_affected_and_records_changes(self):
        self.cache.full()
        self.fave.violated = {('source.b', 'probe.x')}
        todo = self.cache.selective({('source.b', 'probe.x')})
        self.assertEqual(todo, [self.checks[2]])
        self.assertEqual(self.cache.last_changes, [(self.checks[2].line, False, True)])
        self.assertTrue(self.cache.verdict[self.checks[2].line])
        self.assertEqual(self.cache.asked, 4)

    def test_unknown_affected_reasks_everything(self):
        self.cache.full()
        self.assertEqual(self.cache.selective(None), self.checks)
        self.assertEqual(self.cache.last_changes, [])
        self.assertEqual(self.cache.asked, 6)


class TestChecksAndApply(unittest.TestCase):
    """ Loading checks, and `apply`'s refusal and error handling. """

    def test_load_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'checks.json')
            with open(path, 'w', encoding='utf-8') as out:
                json.dump(['! s=source.a && EF p=probe.b'], out)
            [check] = inc.load_checks(path)
        self.assertEqual((check.pair, check.negated), (('source.a', 'probe.b'), True))
        self.assertEqual(repr(check), "Check('! s=source.a && EF p=probe.b')")

    def test_a_refused_update_is_recorded_and_changes_nothing(self):
        def refuse(*_a):
            raise UpdateRefused('no new elements')
        engine = SimpleNamespace(delete_rule=refuse,
                                 set_link=lambda *_a: None)
        deleted, down, refused = set(), set(), []
        update = ('delete', ('n', 'n.1', 0), None)
        self.assertFalse(inc.apply(engine, update, deleted, down, refused))
        self.assertEqual(refused, [(update, 'no new elements')])
        self.assertEqual(deleted, set())

        self.assertTrue(inc.apply(engine, ('link_down', ('a', 'b'), None),
                                  deleted, down, refused))
        self.assertEqual(down, {('a', 'b')})

    def test_a_refusal_propagates_without_a_list(self):
        def refuse(*_a):
            raise UpdateRefused('no')
        with self.assertRaises(UpdateRefused):
            inc.apply(SimpleNamespace(insert_rule=refuse),
                      ('insert', ('n', 'n.1', 0), None), set(), set())

    def test_an_unknown_update_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown update 'modify'"):
            inc.apply(SimpleNamespace(), ('modify', None, None), set(), set())


if __name__ == '__main__':
    unittest.main()
