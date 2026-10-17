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

""" Drive a benchmark's REAL device models through an in-process
AggregatorService, with no sockets and no net_plumber.

A benchmark normally builds its device models in topology.py/switch.py main(),
serialises each command (TopologyCommand.to_json) and ships it over a socket to
a separate aggregator process, which reconstructs the model and dispatches it to
the verification engine. This harness keeps every bit of that real model-
building and dispatch but routes the JSON command stream straight into an
in-process AggregatorService whose engine is the one passed in -- so a backend
(e.g. APKeepAdapter) can be driven by the exact same wl_ifi/stanford/... models
the live benchmark uses, without standing up net_plumber.

It is the substrate for the FaVe+APKeep vs FaVe+NetPlumber comparison
(APKEEP_BACKEND.md, P5) and for the wl_ifi end-to-end adapter test (P4).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from util import barrier

_BENCH_FILES = (
    ("topology", "topology.json"),
    ("routes", "routes.json"),
    ("policies", "policies.json"),
    ("sources", "sources.json"),
)


class InProcessFaVe:
    """ An in-process FaVe aggregator wired to an injected verification engine.

    Usage:
        with InProcessFaVe(engine) as fave:
            fave.replay("bench/wl_ifi")
            fave.check_compliance(rules)
        # engine now holds the built network + compliance results
    """

    def __init__(self, engine: Any, stable_indices: bool = True) -> None:
        # Import here so merely importing this module does not drag in the whole
        # aggregator/bench stack (and its native deps) for callers that only
        # want the class symbol.
        from aggregator.aggregator_service import AggregatorService

        # A stub reporter: the real Reporter tails net_plumber's log, which does
        # not exist here. The handler only touches the reporter on 'report'
        # commands, which we never send.
        reporter = SimpleNamespace(daemon=False, start=lambda: None)
        # `stable_indices`: INCREMENTAL_PLAN.md §8.1 -- re-sent devices reach
        # the engine as the rules that changed (the S4 path); on by default,
        # as in the aggregator (owner, 2026-10-15)
        self._agg = AggregatorService(
            {}, {}, mapping=None, engine=engine, reporter=reporter,
            stable_indices=stable_indices
        )
        self.engine = engine

        # Barriers in a private directory, so a harness instance never sees
        # another one's (or a live aggregator's) state under /dev/shm/np. We
        # are both the client and the releaser here, so this process publishes
        # itself as the owner `barrier.wait` checks for liveness.
        self._barrier_dir: Optional[str] = tempfile.mkdtemp(
            prefix="fave_inproc_barrier_")
        barrier.publish_owner(self._barrier_dir)

        self._patched: List[Any] = []
        self._guard: Optional[str] = None
        self._guarded_sends = 0
        self._install_transport()

        self._worker = threading.Thread(target=self._agg._handler)
        self._worker.start()

    # -- transport: route topology.py/switch.py sends into our queue ----------

    def _install_transport(self) -> None:
        import topology.topology as topo_mod
        import devices.switch as switch_mod

        agg = self._agg

        class _Conn:
            def close(self) -> None:
                pass

        driver = self

        def _send(_conn: Any, data: str) -> None:
            # `resend_device`: the device's message carries a barrier, so a
            # refusal reaches the caller instead of only the log
            if driver._guard is not None:
                msg = json.loads(data)
                msg['barrier'] = driver._guard
                driver._guarded_sends += 1
                data = json.dumps(msg)
            agg.queue.put(data)

        def _connect(*_a: Any, **_k: Any) -> Any:
            return _Conn()

        for mod in (topo_mod, switch_mod):
            self._patched.append((mod, mod.connect_to_fave, mod.fave_sendmsg))
            mod.connect_to_fave = _connect
            mod.fave_sendmsg = _send

    def _restore_transport(self) -> None:
        for mod, connect, send in self._patched:
            mod.connect_to_fave = connect
            mod.fave_sendmsg = send
        self._patched = []

    # -- driving --------------------------------------------------------------

    def replay(self, prefix: str, files: Optional[Dict[str, str]] = None) -> None:
        """ Build and dispatch a benchmark's topology, routes, probes and
        sources (its real device models) from <prefix>/{topology,routes,
        policies,sources}.json, then block until the engine has applied them.

        `files` overrides the per-role base filenames (keys topology/routes/
        policies/sources) for benchmarks that name them differently -- e.g.
        wl_i2/wl_stanford use device_topology.json and probes.json. """
        from util.bench_utils import (
            create_topology, add_routes, add_policies, add_sources
        )

        names = dict(_BENCH_FILES)
        if files:
            names.update(files)
        files = {k: "%s/%s" % (prefix, v) for k, v in names.items()}

        failed = len(self._agg.unguarded_failures)
        with open(files["topology"]) as raw:
            topo = json.load(raw)
            create_topology(topo["devices"], topo["links"],
                            use_unix=False, interweave=True)
        with open(files["routes"]) as raw:
            add_routes(json.load(raw), use_unix=False)
        with open(files["policies"]) as raw:
            pol = json.load(raw)
            add_policies(pol["devices"], pol["links"], use_unix=False)
        with open(files["sources"]) as raw:
            src = json.load(raw)
            add_sources(src["devices"], src["links"], use_unix=False)

        self._agg.queue.join()
        # The build's messages carry no barrier, so a device the aggregator
        # failed on or refused (§8.1: more rules than index slots) used to be
        # logged and left out, and the engine answered for another network.
        errors = self._agg.unguarded_failures[failed:]
        if errors:
            raise RuntimeError("replay of %s: %d of the build's messages failed: %s"
                               % (prefix, len(errors), '; '.join(errors[:5])))

    def check_compliance(self, rules: Dict[str, List[Any]]) -> None:
        """ Issue a check_compliance command (same shape the live benchmark
        sends) and block until the engine has answered. rules maps a probe name
        to a list of [source, negated, cond] entries.

        BARRIER-GUARDED, exactly as bench/compliance_checker.py's own
        check_compliance is. Without the guard a backend that RAISED was
        indistinguishable from one that found nothing: `AggregatorService`
        catches every exception out of `_dispatch` and reports it through the
        barrier, so with none armed the error was logged and this returned
        normally, leaving the caller to read `get_compliance_results() == []`
        as "zero violations". See test/test_in_process_driver.py for the full
        rationale and AD6_PLAN.md §9.23 for the class of published-number bug
        that shape produces.

        Raises `util.barrier.BarrierError` carrying the engine's own message
        if the check could not be answered.

        NOTE the remaining gap: `replay()` above is NOT guarded -- its messages
        are serialized by topology.py/switch.py and put straight onto the queue
        by the patched transport, so guarding them means injecting a barrier
        per message (thousands, on wl_up). A build failure there still only
        reaches the log. Narrower in practice, because a model that failed to
        build produces answers the assertions catch; worth closing separately.
        """
        guard = barrier.arm(self._barrier_dir)
        self._agg.queue.put(json.dumps(
            {"type": "check_compliance", "rules": rules, "barrier": guard}))
        self._agg.queue.join()
        # `_handler` releases in a `finally` BEFORE its `task_done()`, so the
        # join above already guarantees this resolves on the first poll.
        barrier.wait(guard, directory=self._barrier_dir)

    def _client_process(self, client: Any, *args: Any, **kwargs: Any) -> None:
        """ Run `client` -- a topology.py/switch.py main(): parse, generate,
        serialise -- in a forked child, as real FaVe runs every CLI command as
        a process of its own, and hand the messages it sent to the transport
        here. In this process the iptables parser (pybison 0.6.4) leaks every
        parse tree whole: its `py_callback` never releases the argument lists
        of a grammar action, nor the generated actions their stack values.
        Measured on wl_tum: about 210 MB per re-sent packet filter, which
        stopped the calibration's VeriFlow-FR cell at its RSS limit after 12
        re-sends (bench/campaigns/results_inc_dev_fave_calibration_20261016).

        The child runs only client code (no engine, no aggregator; the
        aggregator's worker is idle in `queue.get` while a client runs) and
        leaves by `os._exit`, so the threads it does not inherit hold
        nothing it needs. A client that raises fails the call here with the
        child's traceback. """
        import os
        import struct
        import traceback
        import warnings
        import topology.topology as topo_mod
        import devices.switch as switch_mod
        mods = (topo_mod, switch_mod)
        sends = [mod.fave_sendmsg for mod in mods]
        read_fd, write_fd = os.pipe()
        with warnings.catch_warnings():
            # Python 3.12 warns on fork() with threads alive (the worker, a
            # JVM's): see the docstring for why this child is safe
            warnings.simplefilter('ignore', DeprecationWarning)
            pid = os.fork()
        if pid == 0:                                        # the client
            code = 0
            os.close(read_fd)
            out = os.fdopen(write_fd, 'wb')
            try:
                def _to_parent(_conn: Any, data: str) -> None:
                    raw = b'M' + data.encode()
                    out.write(struct.pack('!Q', len(raw)) + raw)

                for mod in mods:
                    mod.fave_sendmsg = _to_parent
                client(*args, **kwargs)
            except BaseException:
                raw = b'E' + traceback.format_exc().encode()
                out.write(struct.pack('!Q', len(raw)) + raw)
                code = 1
            finally:
                try:
                    out.flush()
                finally:
                    os._exit(code)
        os.close(write_fd)
        records = []
        with os.fdopen(read_fd, 'rb') as inp:
            while True:
                head = inp.read(8)
                if not head:
                    break
                records.append(inp.read(struct.unpack('!Q', head)[0]))
        _pid, status = os.waitpid(pid, 0)
        errors = [r[1:].decode() for r in records if r[:1] == b'E']
        if errors or status:
            raise RuntimeError("client process failed (status %d)%s" % (
                status, (":\n" + errors[0]) if errors else ""))
        for raw in records:
            sends[0](None, raw[1:].decode())

    def resend_device(self, device: List[Any]) -> None:
        """ Re-send ONE device, as `replay` sends it -- a `topology.json`
        entry [name, type, ...] whose config path may point at an edited copy
        -- and block until the aggregator has applied it. With
        `stable_indices`, the engine then gets the rules that changed
        (INCREMENTAL_PLAN.md §8.1, S4). Barrier-guarded like
        `check_compliance`: a refusal or failure raises `BarrierError` with
        the aggregator's message. """
        from util.bench_utils import _DEVICES
        guard = barrier.arm(self._barrier_dir)
        self._guard, self._guarded_sends = guard, 0
        try:
            self._client_process(_DEVICES[device[1]], *device,
                                 use_unix=False, interweave=True)
        finally:
            self._guard = None
        if self._guarded_sends != 1:
            raise RuntimeError("resend_device: %d messages for one device, "
                               "expected one" % self._guarded_sends)
        self._agg.queue.join()
        barrier.wait(guard, directory=self._barrier_dir)

    def resend_switch(self, name: str, entries: List[List[Any]]) -> None:
        """ Re-send switch `name` WHOLE with the rules `entries` (routes.json
        entries [node, table, idx, fields, commands, in_ports], built into
        rules exactly as `devices/switch.py` builds a command's) -- S4 on a
        workload whose rules are switch tables (wl_cloud). Its ports, wiring
        and declarations are the stored model's. Barrier-guarded. """
        import copy as _copy
        from devices.switch import _commands_to_actions, _fields_to_match
        from rule.rule_model import Match, Rule
        from topology.topology import TopologyCommand
        model = _copy.deepcopy(self._agg.models[name])
        table = name + '.1'
        model.tables[table] = [
            Rule(node, table, int(idx), [p for p in in_ports if p],
                 Match(_fields_to_match(';'.join(fields))),
                 _commands_to_actions(','.join(commands)))
            for node, _t, idx, fields, commands, in_ports in entries]
        msg = TopologyCommand(name, 'add', model=model).to_json()
        guard = barrier.arm(self._barrier_dir)
        msg['barrier'] = guard
        self._agg.queue.put(json.dumps(msg))
        self._agg.queue.join()
        barrier.wait(guard, directory=self._barrier_dir)

    def topology(self, argv: List[str]) -> None:
        """ Send ONE topology command exactly as `topology.py <argv>` sends
        it -- e.g. links taken down (`-d -l`) or up again (`-a -l`),
        INCREMENTAL_PLAN.md D14 -- and block until the aggregator has applied
        it. Barrier-guarded like `switch`. """
        import topology.topology as topo_mod
        self._guarded(lambda: topo_mod.main(argv), 'topology')

    def _guarded(self, send: Any, what: str) -> None:
        guard = barrier.arm(self._barrier_dir)
        self._guard, self._guarded_sends = guard, 0
        try:
            send()
        finally:
            self._guard = None
        if self._guarded_sends != 1:
            raise RuntimeError("%s: %d messages for one command, expected one"
                               % (what, self._guarded_sends))
        self._agg.queue.join()
        barrier.wait(guard, directory=self._barrier_dir)

    def switch(self, argv: List[str]) -> None:
        """ Send ONE control-plane command exactly as `switch.py <argv>`
        sends it -- e.g. a batch of routes added (`-a -r`), deleted (`-d -r`)
        or replaced (`-u -r`), INCREMENTAL_PLAN.md D14 -- and block until the
        aggregator has applied it. Barrier-guarded: a refusal raises
        `BarrierError` with the aggregator's message. """
        import devices.switch as switch_mod
        self._guarded(lambda: switch_mod.main(argv), 'switch')

    def delete_device(self, name: str, mtype: str) -> None:
        """ Delete device `name` of type `mtype` with its links, as
        `topology.py -d -n <name> -t <mtype>` sends it (INCREMENTAL_PLAN.md
        §8.2), and block until the aggregator has applied it.
        Barrier-guarded: a refusal raises `BarrierError`. """
        from topology.topology import TopologyCommand
        msg = TopologyCommand(name, 'del', mtype=mtype).to_json()
        guard = barrier.arm(self._barrier_dir)
        msg['barrier'] = guard
        self._agg.queue.put(json.dumps(msg))
        self._agg.queue.join()
        barrier.wait(guard, directory=self._barrier_dir)

    # -- lifecycle ------------------------------------------------------------

    def stop(self) -> None:
        self._agg.stop = True
        self._agg.queue.put("")  # unblock the blocking queue.get()
        self._worker.join(timeout=10)
        self._restore_transport()
        if self._barrier_dir is not None:
            # Withdraw first: a waiter that somehow outlives us must read "no
            # aggregator is registered" rather than poll a vanished directory.
            barrier.withdraw_owner(self._barrier_dir)
            shutil.rmtree(self._barrier_dir, ignore_errors=True)
            self._barrier_dir = None

    def __enter__(self) -> "InProcessFaVe":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.stop()
