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

""" util/in_process_driver.py must not hide a backend failure.

WHY THIS EXISTS. `InProcessFaVe` is the harness every backend-vs-oracle test in
this repository drives its engine through (six of the ad6 test files alone, plus
the APKeep ones). It used to queue a task with no `barrier` key and merely
`queue.join()`: `AggregatorService._handler` catches every exception out of
`_dispatch`, logs it, and reports it THROUGH THE BARRIER -- so with no barrier
armed, a backend that raised looked exactly like a backend that found nothing.
A test would then read `get_compliance_results() == []` and call it "zero
violations".

That is the failure shape AD6_PLAN.md §9.23 is a post-mortem of, one layer up.
The bridge below learned to REFUSE a query it cannot honour rather than answer
the unconditioned question (ad6/fave_bridge.py's `_validated_conditions`); this
harness turned the refusal back into a silent pass. Found while measuring the
§9 Phase 5 default flip: under the structural translation wl_ifi's 54 stateful
checks raise in the bridge, and the suite reported 0 violations.

The real client does not have this hole -- bench/compliance_checker.py arms a
barrier on its own check_compliance. This harness now uses the same protocol,
so the two agree about what "finished" means.
"""

import logging
import threading
import unittest

from util.barrier import BarrierError
from util.in_process_driver import InProcessFaVe


class _Boom(Exception):
    """ Distinct from any exception the aggregator itself might raise, so a
    test cannot pass on the wrong failure. """


class _RaisingEngine:
    """ The minimum surface `AggregatorService._dispatch` touches for a
    'check_compliance' task, with the engine failing the way a real backend
    does when it refuses a query it cannot honour. """

    def __init__(self, exc=None):
        self._exc = exc
        self.calls = 0

    def check_compliance(self, rules):
        self.calls += 1
        if self._exc is not None:
            raise self._exc

    def stop(self):
        pass

    def max_rule_index(self, table):
        return 2**20 - 1


def _drive(engine, timeout=30.0):
    """ Run one check_compliance through the harness on a thread, so a
    regression that WEDGES (rather than silently passing) fails here too
    instead of hanging the suite. Returns (finished, box). """
    box = {}

    def target():
        try:
            with InProcessFaVe(engine) as fave:
                fave.check_compliance({"probe.a": [["source.b", False, []]]})
            box['ok'] = True
        except BaseException as exc:            # noqa: BLE001
            box['exc'] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    return (not thread.is_alive()), box


class TestInProcessDriverSurfacesFailure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # The aggregator logs the caught exception at exception level; that is
        # correct behaviour and not something this test needs on stderr.
        logging.getLogger("AggregatorService").setLevel(logging.CRITICAL)

    def test_a_backend_exception_reaches_the_caller(self):
        """ THE POINT OF THIS FILE. A raising engine must not read as a clean
        run with no results. """
        engine = _RaisingEngine(_Boom("the backend refused the query"))
        finished, box = _drive(engine)

        self.assertTrue(finished, "the harness hung instead of reporting")
        self.assertEqual(engine.calls, 1, "the engine was never even called")
        self.assertIn('exc', box,
                      "check_compliance returned normally although the engine "
                      "raised -- a backend failure is being swallowed")
        self.assertIsInstance(box['exc'], BarrierError)
        self.assertIn("the backend refused the query", str(box['exc']),
                      "the original failure must survive into the message, or "
                      "the caller cannot tell what went wrong")

    def test_a_successful_check_does_not_raise(self):
        """ Guards the test above: a fix that always raised would pass it. """
        engine = _RaisingEngine()
        finished, box = _drive(engine)

        self.assertTrue(finished, "the harness hung on a successful check")
        self.assertEqual(engine.calls, 1)
        self.assertNotIn('exc', box,
                         "a successful check must not raise: %r" % box.get('exc'))


#: written by `_client` in the client worker; must stay empty here
_CHILD_STATE = []


def _client(*messages, fail=False):
    """ A stand-in for topology.py's main(): sends `messages`, as a real
    client serialises its commands, and keeps state of its own. """
    import topology.topology as topo_mod
    _CHILD_STATE.append(messages)
    for msg in messages:
        topo_mod.fave_sendmsg(None, msg)
    if fail:
        raise _Boom("the client could not parse its configuration")


class TestClientProcess(unittest.TestCase):
    """ `_client_process` runs a client as its own process (pybison leaks
    every parse tree in the process that parses, util/client_worker.py): what
    the client sends arrives here in order, its failure fails the call, and
    what it keeps does not. """

    def _run(self, *messages, fail=False):
        import topology.topology as topo_mod
        got = []
        with InProcessFaVe(_RaisingEngine()) as fave:
            topo_mod.fave_sendmsg = lambda _conn, data: got.append(data)
            fave._client_process('test.test_in_process_driver:_client',
                                 *messages, fail=fail)
        return got

    def test_the_worker_serves_calls_until_it_is_recycled(self):
        from util.client_worker import ClientWorker
        worker = ClientWorker(recycle_mb=10 ** 6)
        try:
            first = worker.call('test.test_in_process_driver:_client', '{"a": 1}')
            pid = worker._proc.pid
            second = worker.call('test.test_in_process_driver:_client', '{"b": 2}')
            self.assertEqual((first, second), (['{"a": 1}'], ['{"b": 2}']))
            self.assertEqual(worker._proc.pid, pid, "one worker serves both calls")
            worker.recycle_mb = 0                   # every worker is too big now
            worker.call('test.test_in_process_driver:_client', '{"c": 3}')
            self.assertEqual(worker.recycled, 1)
            self.assertNotEqual(worker._proc.pid, pid, "a recycled worker is replaced")
        finally:
            worker.close()

    def test_the_messages_arrive_in_order(self):
        self.assertEqual(self._run('{"a": 1}', '{"b": 2}'), ['{"a": 1}', '{"b": 2}'])

    def test_the_client_runs_in_another_process(self):
        self._run('{"a": 1}')
        self.assertEqual(_CHILD_STATE, [],
                         "the client ran in this process: what it keeps "
                         "(a parse tree) would stay here")

    def test_a_failing_client_fails_the_call(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run('{"a": 1}', fail=True)
        self.assertIn("could not parse its configuration", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
