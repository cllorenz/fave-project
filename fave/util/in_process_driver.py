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
import threading

from types import SimpleNamespace
from typing import Any, Dict, List

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

    def __init__(self, engine: Any) -> None:
        # Import here so merely importing this module does not drag in the whole
        # aggregator/bench stack (and its native deps) for callers that only
        # want the class symbol.
        from aggregator.aggregator_service import AggregatorService

        # A stub reporter: the real Reporter tails net_plumber's log, which does
        # not exist here. The handler only touches the reporter on 'report'
        # commands, which we never send.
        reporter = SimpleNamespace(daemon=False, start=lambda: None)
        self._agg = AggregatorService(
            {}, {}, mapping=None, engine=engine, reporter=reporter
        )
        self.engine = engine

        self._patched: List[Any] = []
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

        def _send(_conn: Any, data: str) -> None:
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

    def check_compliance(self, rules: Dict[str, List[Any]]) -> None:
        """ Issue a check_compliance command (same shape the live benchmark
        sends) and block until the engine has answered. rules maps a probe name
        to a list of [source, negated, cond] entries. """
        self._agg.queue.put(json.dumps({"type": "check_compliance", "rules": rules}))
        self._agg.queue.join()

    # -- lifecycle ------------------------------------------------------------

    def stop(self) -> None:
        self._agg.stop = True
        self._agg.queue.put("")  # unblock the blocking queue.get()
        self._worker.join(timeout=10)
        self._restore_transport()

    def __enter__(self) -> "InProcessFaVe":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.stop()
