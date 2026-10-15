#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module provides FaVe's central aggregation service.
"""

from __future__ import annotations

import socket
import os
import json
import logging
import sys
import argparse
import copy
import time

from typing import Any, Dict, List, Optional, Tuple

from pprint import pformat
from threading import Thread
from queue import Empty, Queue

from util.typing_util import JSONDict

from aggregator.aggregator_abstract import AbstractAggregator, TRACE
from aggregator.aggregator_singleton import AGGREGATOR
from aggregator.aggregator_signals import register_signals

from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
from util.aggregator_utils import fave_recvmsg
from util.lock_util import PreLockedFileLock
from util import barrier
from util.packet_util import is_ip, is_domain, is_unix, is_port, is_host
from util.path_util import json_to_pathlet, pathlet_to_json, Path
#from util.dynamic_distribution import NodeLinkDispatcher

import netplumber.jsonrpc as jsonrpc
from netplumber.jsonrpc import NET_PLUMBER_DEFAULT_PORT, NET_PLUMBER_DEFAULT_IP
from netplumber.adapter import NetPlumberAdapter

from netplumber.slice import SlicingCommand
from devices.abstract_device import LPM, restore_table_semantics, validate_lpm_rules
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel, StateCommand
from devices.switch import SwitchModel, SwitchCommand
from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from topology.topology import LinksModel, TopologyCommand

from reporting.reporter import Reporter
from aggregator.abstract_engine import UpdateRefused
from util.stable_index import StableIndexer, diff as stable_diff, key as stable_key

from rule.rule_model import RuleField

def common_index_budget(table: str) -> int:
    """ INCREMENTAL_PLAN.md §8.1: the room the aggregator numbers `table` in,
    the SAME on every engine -- so a model, an update stream and its records
    carry the same indices whichever engine runs them, and cells compare
    across engines. It is the tightest any engine has for that kind of table:
    APKeep's router ACLs (priority 70000 - idx), NetPlumber's 20 rule-index
    bits everywhere else. An engine's own `max_rule_index` decides only what
    is refused, and the room of a table that outgrows this one
    (`test_aggregator_backend` pins it below every engine's). """
    if table.endswith(('.acl_in', '.acl_out')):
        return 69_999
    return 2**20 - 1


#: device models that arrive WHOLE -- the ones stable indices apply to
#: (INCREMENTAL_PLAN.md §8.1); a switch's control-plane commands keep the
#: indices their sender chose
_WHOLE_DEVICE_TYPES = ('packet_filter', 'snapshot_packet_filter',
                       'application_layer_gateway', 'switch', 'router')

#: tables an engine translates as a whole (util/incremental._WHOLE_TABLES)
_WHOLE_TABLES = ('.pre_routing', '.post_routing')


def _has_asyncore_socks(socks: Dict[Any, Any]) -> bool:
    return socks != {} and all(v is not None for v in socks.values())


# AD6_PLAN.md §9.3 Phase 6: the verification engines FaVe can be run on.
#
# WHY THIS EXISTS. Three engines live in this tree -- NetPlumber (HSA), APKeep
# (BDD/NDD) and ad6 (SAT/QBF) -- but until now `AggregatorService` constructed
# `NetPlumberAdapter` unconditionally, and its `engine=` parameter is
# documented as, and remains, a TEST injection seam. There was no production
# route to the other two at all: running FaVe on ad6 meant building the service
# from Python and injecting the engine, which no benchmark or script does.
#
# NetPlumber is first, and the default, because every existing benchmark,
# script and CI job invokes the aggregator without naming a backend.
BACKEND_NETPLUMBER = 'netplumber'
BACKEND_APKEEP = 'apkeep'
BACKEND_AD6 = 'ad6'
# VeriFlow-FR (VERIFLOW_PLAN.md V4): an independent VeriFlow, in-process through
# libveriflow_fr -- no net_plumber process, and no anomaly step.
BACKEND_VERIFLOW = 'veriflow'
BACKENDS = (BACKEND_NETPLUMBER, BACKEND_APKEEP, BACKEND_AD6, BACKEND_VERIFLOW)

# Which backends need a separate `net_plumber` PROCESS to talk to. Only one
# does: APKeep runs in-process (JPype) and ad6 as a subprocess per
# check_compliance, so a benchmark that starts net_plumber for them would be
# waiting on a backend they never use.
BACKENDS_NEEDING_NETPLUMBER = (BACKEND_NETPLUMBER,)

# Which backends implement `check_anomalies`. `Ad6Adapter` raises
# NotImplementedError by design (AD6_PLAN.md §9.4: the anomaly queries are
# named as a documented gap, not a goal), and APKeepAdapter does not offer it
# either -- so a benchmark must SKIP that step rather than send a request that
# can only fail. Declared here, next to BACKENDS, so the benchmark harness and
# the adapters cannot disagree about it silently.
BACKENDS_WITH_ANOMALIES = (BACKEND_NETPLUMBER,)


def build_engine(
        backend: str, logger: Any, socks: Optional[List[Any]] = None,
        asyncore_socks: Optional[Dict[Any, Any]] = None,
        mapping: Optional[Any] = None, apkeep_engine: str = 'ndd',
        faithful_vlan: bool = True, grounding: Optional[str] = None,
        solver: Optional[str] = None, lite_acyclic: bool = False,
        vf_fields: str = '4+10', vf_revisit: str = 'state',
        vf_slicing: str = 'device', vf_budget: int = 0,
        invert_lpm: bool = False
) -> Any:
    """ The verification engine named by `backend`.

    Imports the chosen adapter LAZILY, because the three have very different
    dependency footprints -- APKeep needs a JVM through JPype, ad6 needs
    nothing at import time but reaches a subprocess later -- and an aggregator
    running on NetPlumber should not pay for, or fail on, either.

    Backend-specific options are accepted and ignored by the backends they do
    not apply to, so one command line can switch engines without also having to
    edit away its flags. What must NOT be silently ignored is a malformed value
    for the backend actually selected: those are validated by the adapters
    themselves, at construction, before any model is built.
    """
    if backend not in BACKENDS:
        raise ValueError(
            "unknown backend %r -- expected one of %s" % (
                backend, ', '.join(repr(b) for b in BACKENDS)))

    # The one backend option that must NOT be silently ignored, which is why it
    # is checked here and not left to the adapters. §5.4's guardrail reads a
    # verdict that did not move as "this check set cannot see rule priority".
    # On a backend that never applied the inversion, the verdict cannot move
    # for a reason that has nothing to do with the check set -- so the
    # experiment would manufacture its own conclusion, in the direction that
    # retires a guardrail. APKeep resolves longest-prefix in its own
    # ForwardElement trie and ad6 orders at translation rather than here.
    if invert_lpm and backend not in (BACKEND_NETPLUMBER, BACKEND_VERIFLOW):
        raise ValueError(
            "--invert-lpm is not implemented for %s. It is MEASUREMENT_RUN_PLAN"
            ".md §5.4's guardrail, and a run that quietly ignored it would "
            "report an unchanged verdict -- which that guardrail reads as "
            "'this check set is blind to longest-prefix-match'. Use netplumber "
            "or veriflow, which order a declared-LPM table themselves."
            % backend)

    # The SECOND option that must not be silently ignored, and for the same
    # reason. `--no-vlan` is MEASUREMENT_RUN_PLAN.md's VLAN guardrail arm: it
    # relaxes the VLAN dimension, and relaxing can only ADD reachability, so
    # an unchanged verdict reads as 'this check set cannot see VLAN at all'.
    # Only APKeep has the flag -- NetPlumber and VeriFlow-FR translate the
    # model's rules literally, and ad6's semantic path (the one
    # `faithful_vlan` configured) was deleted, `AD6_PLAN.md` §9.25 -- so on
    # any other backend the arm would relax NOTHING and the verdict would be
    # unchanged for a reason that has nothing to do with the check set. That
    # manufactures the guardrail's own conclusion, in the direction that
    # retires it.
    #
    # It was accepted-and-ignored here until 2026-10-08, twenty lines below
    # the comment explaining why `--invert-lpm` must not be.
    if not faithful_vlan and backend != BACKEND_APKEEP:
        raise ValueError(
            "--no-vlan is not implemented for %s: only APKeep models VLAN "
            "behind a flag. It is the VLAN guardrail arm, and a run that "
            "quietly ignored it would report an unchanged verdict -- which "
            "that guardrail reads as 'this check set is blind to VLAN'. The "
            "other backends carry VLAN unconditionally and have no plain arm "
            "to compare against." % backend)

    if backend == BACKEND_NETPLUMBER:
        return NetPlumberAdapter(
            list(socks or []), logger,
            asyncore_socks=asyncore_socks or {}, mapping=mapping,
            invert_lpm=invert_lpm)

    if backend == BACKEND_VERIFLOW:
        # The decided defaults (VERIFLOW_PLAN.md D6, Q4, Q22); every one is a
        # stamp, and each ablation stays reachable by name. No budget by
        # default: the suite's did-not-finish limit is external (TODO item 31).
        from veriflow.adapter import VeriFlowAdapter
        return VeriFlowAdapter(logger, slicing=vf_slicing, budget=vf_budget,
                               revisit=vf_revisit, fields=vf_fields,
                               invert_lpm=invert_lpm)

    if backend == BACKEND_APKEEP:
        from apkeep.adapter import APKeepAdapter
        return APKeepAdapter(logger, mapping=mapping,
                             faithful_vlan=faithful_vlan, engine=apkeep_engine)

    from ad6.adapter import GROUNDING_RANK, SOLVER_MINISAT22, Ad6Adapter
    return Ad6Adapter(
        logger,
        grounding=grounding or GROUNDING_RANK,
        solver=solver or SOLVER_MINISAT22,
        lite_acyclic=lite_acyclic)

class AggregatorService(AbstractAggregator):
    """ This class provides FaVe's central aggregation service.
    """

    def __init__(
            self, socks: Dict[Any, Any], asyncore_socks: Dict[Any, Any],
            mapping: Optional[Any] = None,
            engine: Optional[Any] = None, reporter: Optional[Any] = None,
            backend: str = BACKEND_NETPLUMBER, stable_indices: bool = True,
            **backend_options: Any
    ) -> None:
        self.queue: Queue[Any] = Queue()
        self.models: Dict[str, Any] = {}
        # (node, table) -> {matched prefix: action signature}, for the
        # declared-LPM ambiguity check. Carried across syncs because rules
        # arrive in batches and a collision between two batches is still one.
        self._lpm_index: Dict[Tuple[str, str], Dict[Any, str]] = {}
        self.port_to_model: Dict[str, Any] = {}
        self.links: Dict[Any, List[Any]] = {}
        self.stop = False
        # `engine`/`reporter` are injection seams (default None -> the production
        # objects). Tests pass a recording engine and a stub reporter to drive
        # the dispatch/diff logic without a live backend or the log-tailing
        # daemon (which opens /dev/shm/np/stdout.log).
        #
        # `backend` is the PRODUCTION route (AD6_PLAN.md §9.3 Phase 6) and
        # `engine` stays the test one: an explicitly injected object wins, so
        # every existing test keeps working unchanged. Before Phase 6 there was
        # only the seam, which is why no benchmark could run on anything but
        # NetPlumber.
        self.verification_engine = engine if engine is not None else build_engine(
            backend,
            AggregatorService.LOGGER,
            socks=list(socks.values()),
            asyncore_socks=asyncore_socks,
            mapping=mapping,
            **backend_options
        )
        # Recorded so the reporter can say WHICH engine produced (or did not
        # produce) a verdict -- see reporting/reporter.py's
        # `_backend_checks_anomalies`.
        self.backend = backend
        # INCREMENTAL_PLAN.md §8.1: stable indices, ON by default since
        # 2026-10-15 (owner). A device model that arrives whole is re-numbered
        # against its last emission, within the engine's index budget, and a
        # re-sent device reaches the engine as the rules that changed
        # (`_sync_stable`). Off (`--no-stable-indices`), every path is as V5
        # measured it, on the generators' indices.
        self.stable_indices = stable_indices
        self._indexer: Optional[StableIndexer] = (
            StableIndexer(common_index_budget, self.verification_engine.max_rule_index)
            if stable_indices else None)
        #: failed tasks no barrier reported, as "<exception>: <message>"
        self.unguarded_failures: List[str] = []
        #: per-device-update counts of the stable path, for the S4 driver
        self.update_stats: Dict[str, Any] = {}
        #: (node, table) a control-plane command has filled -- a packet
        #: filter's routing table, a switch's flow table (§8.1)
        self._commanded: set = set()
        # XXX: make log file configurable
        #
        # AD6_PLAN.md §9.28: the log tail is net_plumber's stdout, so it is
        # passed only for the backend that writes it. Handing it to an ad6 or
        # APKeep run would replay a STALE log from an earlier NetPlumber run --
        # the Reporter opens at offset 0 -- and attribute one engine's verdict
        # to another. Those engines report their own results instead
        # (`get_compliance_results`).
        np_log = ('/dev/shm/np/stdout.log'
                  if backend in BACKENDS_NEEDING_NETPLUMBER else None)
        self.reporter = reporter if reporter is not None else Reporter(
            self, np_log
        )
        self.reporter.daemon = True
        self.model_types: Dict[str, Any] = {
            "packet_filter" : PacketFilterModel,
            "snapshot_packet_filter" : SnapshotPacketFilterModel,
            "switch" : SwitchModel,
            "switch_command" : SwitchCommand,
            "state_command" : StateCommand,
            "topology_command" : TopologyCommand,
            "slicing_command" : SlicingCommand,
            "links" : LinksModel,
            "generator" : GeneratorModel,
            "probe" : ProbeModel
        }


    def print_aggregator(self) -> None:
        """ Prints the state to stderr.
        """
        print(
            "Aggregator:",
            self.verification_engine.mapping,
            "tables:",
            "\t%s" % self.verification_engine.tables,
            "ports:",
            "\t%s" % self.verification_engine.ports,
            "rule ids:",
            "\t%s" % self.verification_engine.rule_ids,
            "links:",
            "\t%s" % self.verification_engine.links,
            "generators:",
            "\t%s" % self.verification_engine.generators,
            "probes:",
            "\t%s" % self.verification_engine.probes,
            file=sys.stderr,
            sep="\n"
        )


    def _model_from_json(self, j: JSONDict) -> Any:
        """ Reconstructs a model from a JSON object.

        Keyword arguments:
        j -- a JSON object
        """

        AbstractAggregator.LOGGER.debug('reconstruct model')
        try:
            model = self.model_types[j["type"]]

        except KeyError:
            AbstractAggregator.LOGGER.error(
                "model type not implemented: %s", j["type"]
            )
            raise Exception("model type not implemented: %s" % j["type"])

        else:
            # TABLE_SEMANTICS_PLAN.md S1: declared table semantics ride beside
            # the tables, and every model's own from_json predates the field, so
            # restore them here -- the one place all model types are rebuilt.
            return restore_table_semantics(model.from_json(j), j)


    def _dispatch(self, j: JSONDict) -> str:
        """ Handle one parsed message and return its task type.

        Split out of `_handler` so the barrier release can be wrapped in a
        `finally` (TODO.md item 1r): every path out of here, including an
        exception, must reach `barrier.release`. Pure move otherwise --
        `task_type` was the only local the caller used. """

        if j['type'] == 'stop':
            task_type = 'stop'
            self.stop_aggr()
            self.verification_engine.stop()

        elif j['type'] == 'report':
            task_type = 'report'
            report = j
            # Let the log tailer catch up first: the events it has not parsed
            # yet are the reachability evidence the report renders from, so
            # rendering early would yield a partial verdict. Latent race, not an
            # observed one (see Reporter.drain). Safe to block here -- the
            # compliance/anomaly checks are barrier-guarded and synchronous, so
            # net_plumber has stopped writing by now.
            self.reporter.drain()
            self.reporter.dump_report(report['file'])
            self.reporter.mark_compliance()
            self.reporter.mark_anomalies()

        elif j['type'] == 'check_compliance':
            task_type = 'check_compliance'
            rules: Dict[Any, List[Any]] = {}
            for dst, src_rules in j['rules'].items():
                rules.setdefault(dst, [])
                for src, negated, cond in src_rules:
                    rules[dst].append((src, negated, [RuleField.from_json(f) for f in cond]))

            self.verification_engine.check_compliance(rules)

        elif j['type'] == 'dump':
            dump = j
            odir = dump['dir']

            task_type = "dump %s" % ','.join([k for k in dump if k not in ['type', 'dir']])

            if dump['fave']:
                self._dump_aggregator(odir)
            if dump['flows']:
                self.verification_engine.dump_flows(odir)
            if dump['network']:
                self.verification_engine.dump_plumbing_network(odir)
            if dump['pipes']:
                self.verification_engine.dump_pipes(odir)
            if dump['trees']:
                self.verification_engine.dump_flow_trees(odir, dump['simple'])

            lock = PreLockedFileLock("%s/.lock" % odir)
            lock.release()


        elif j['type'] == 'check_anomalies':
            task_type = 'check_anomalies'
            self.verification_engine.check_anomalies(
                use_shadow=j.get('use_shadow', False),
                use_reach=j.get('use_reach', False),
                use_general=j.get('use_general', False)
            )

        else:
            model = self._model_from_json(j)
            if model.type == 'topology_command':
                # A delete carries no model, only its type (TODO item 53).
                task_type = model.model.type if model.model is not None \
                    else (model.mtype or model.type)
            else:
                task_type = model.type

            self._sync_diff(model)

        return task_type


    def _abandon_queued_barriers(self) -> None:
        """ Release, with an error, the barriers of requests left unhandled when
        the handler stops (TODO.md item 1r). `queue.task_done` is called for
        each so `run`'s `queue.join()` can still complete. """
        while True:
            try:
                data = self.queue.get_nowait()
            except Empty:
                return

            try:
                pending = json.loads(data) if data else {}
                path = pending.get('barrier') if isinstance(pending, dict) else None
                if path:
                    AggregatorService.LOGGER.warning(
                        "worker: abandoning queued %s request (aggregator "
                        "stopping)", pending.get('type', 'unknown')
                    )
                    barrier.release(
                        path,
                        error="the aggregator stopped before handling this request"
                    )
            except ValueError:
                pass
            finally:
                self.queue.task_done()


    def _handler(self) -> None:
        t_start = time.time()

        while not self.stop:
            data = self.queue.get()
            if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                AggregatorService.LOGGER.debug('worker: fetched data from queue')

            if not data:
                if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                    AggregatorService.LOGGER.debug('worker: ignoring empty data')
                self.queue.task_done()
                continue

            t_task_start = time.time()

            try:
                j = json.loads(data)
            except ValueError:
                emsg = 'worker: could not parse data: %s' % data
                AggregatorService.LOGGER.fatal(emsg)
                self.queue.task_done()
                return

            if AggregatorService.LOGGER.isEnabledFor(TRACE):
                AggregatorService.LOGGER.trace('worker: parsed data\n%s' % pformat(j, indent=2))

            barrier_path = j.get('barrier')
            task_type = 'unknown'
            error = None
            try:
                task_type = self._dispatch(j)
            except Exception as exc:               # pylint: disable=broad-except
                # Report the failure THROUGH the barrier: a waiter that never
                # learns about it would block for as long as this process
                # happens to live, turning a loud error into a silent hang.
                error = "%s: %s" % (type(exc).__name__, exc)
                AggregatorService.LOGGER.exception("worker: task failed:")
                if not barrier_path:
                    # No one waits on this task -- a device sent during a
                    # from-zero build. Kept, so the build's driver can say the
                    # network is not the one sent (`InProcessFaVe.replay`); a
                    # refusal also gets a line of its own, which `cell_run.py`
                    # reads (owner, 2026-10-15: a refusal must be clear).
                    self.unguarded_failures.append(error)
                    if isinstance(exc, UpdateRefused):
                        AggregatorService.LOGGER.error(
                            "worker: REFUSED, with no one waiting: %s", exc)
            finally:
                barrier.release(barrier_path, error=error)

            t_task_end = time.time()

            if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
                emsg = "worker: completed task %s in %s seconds." % (
                    task_type, t_task_end - t_task_start
                )
                AggregatorService.LOGGER.info(emsg)

            self.queue.task_done()

        # The loop above exits on `self.stop` without touching whatever is
        # still queued, so those requests will never be handled. Fail their
        # barriers explicitly: a waiter that is never told would block for as
        # long as this process lives.
        self._abandon_queued_barriers()

        t_stop = time.time()
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("worker: stop handler after %s seconds.", t_stop-t_start)


    def run(self, server: str, port: int = 0) -> None:
        """ Operates FaVe's aggregation service.
        """

        self.reporter.start()

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            lmsg = "master: open and bind %s socket" % (
                'unix' if port == 0 else 'tcp/ip'
            )
            AggregatorService.LOGGER.info(lmsg)

        # open new socket
        sock = socket.socket(
            socket.AF_UNIX if port == 0 else socket.AF_INET,
            socket.SOCK_STREAM
        )
        sock.settimeout(2.0)
        sock.bind(server if port == 0 else (server, port))

        # Declare who releases request barriers (TODO.md item 1r). Published
        # after the bind so its presence means "an aggregator is actually up",
        # and it carries pid + start time so a waiter checks identity rather
        # than mere pid existence.
        barrier.publish_owner()

        # start thread to handle incoming config events
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: start handler thread")
        thread = Thread(target=self._handler)
        thread.daemon = True
        thread.start()

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: listen on socket")
        sock.listen(1)

        while not self.stop:
            # accept connections on socket
            if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                AggregatorService.LOGGER.debug("master: wait for connection")
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                    AggregatorService.LOGGER.debug("master: listening timed out, continue loop...")
                continue
            except socket.error:
                if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                    AggregatorService.LOGGER.debug(
                        "master: break listening loop due to socket error"
                    )
                AggregatorService.LOGGER.exception("master: error from accept():")
                break
            else:
                if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                    AggregatorService.LOGGER.debug("master: accepted connection")

            # receive data from socket
            data = fave_recvmsg(conn, logger=AggregatorService.LOGGER)
            if data is None:
                # A client that connected and closed without a complete
                # message. Skip it: an assert here ended the whole service,
                # and every request after it (TODO item 53).
                AggregatorService.LOGGER.warning(
                    "master: connection closed without a complete message, ignored")
                conn.close()
                continue
            if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                lmsg = "master: read data of size %s" % len(data)
                AggregatorService.LOGGER.debug(lmsg)

            # upon data receival enqueue
            self.queue.put(data)
            if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                AggregatorService.LOGGER.debug("master: enqueued data")

        # close unix domain socket
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: close receiving socket")
        sock.close()

        # wait for the config event handler to finish
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: join queue")
        self.queue.join()

        # join thread
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: join handler thread")
        thread.join()

        # Only now stop claiming responsibility for barriers: in-flight work
        # has completed and released normally, so no waiter is failed while its
        # request is still being handled. A leftover file after a crash is
        # harmless -- waiters check the pid it names, and a dead pid reads as
        # "will never release".
        barrier.withdraw_owner()

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: finished run")

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: stop reporter")
        self.reporter.stop()


    def stop_aggr(self) -> None:
        """ Stops FaVe's aggregation service.
        """
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("worker: initiate stopping")
        self.stop = True


    def _validate_declared_tables(self, model: Any) -> None:
        """ Run the declared-semantics checks over this model's rules.

        Silent on a model that declares nothing, which is every workload but
        wl_stanford and wl_i2 today -- so the cost is one `getattr` per sync.
        """
        semantics_of = getattr(model, 'semantics_of', None)
        if semantics_of is None:
            return

        for table, rules in getattr(model, 'tables', {}).items():
            if semantics_of(table) != LPM or not rules:
                continue
            index = self._lpm_index.setdefault((model.node, table), {})
            validate_lpm_rules(model.node, table, rules, index)


    def _sync_diff(self, model: Any) -> None:
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            AggregatorService.LOGGER.debug('worker: synchronize model')

        # §8.1: decided on the message as it ARRIVED -- a switch command below
        # turns `model` into the stored switch, whose type is 'switch' too
        whole = (model.type in _WHOLE_DEVICE_TYPES or (
            model.type == 'topology_command' and model.mtype in _WHOLE_DEVICE_TYPES
            and model.command == 'add'))
        commanded = model.type in ["switch_command", 'state_command', 'relay_command']
        #: the tables a control-plane command fills, at its sender's indices --
        #: read from what the device buffered, not from the rules' `tid`: a
        #: packet filter turns a route into rules of its `.routing` table
        command_tables: set = set()


        # handle minor model changes (e.g. updates by the control plane)
        if model.type in ["switch_command", 'state_command', 'relay_command']:
            if model.command in ('remove_rule', 'update_rule'):
                # Refused by name until the deletion half of the diff exists
                # (INCREMENTAL_PLAN.md §8.2). Before, `remove_rule` got the
                # whole rule list and raised TypeError; with that mended it
                # would only fill `_deletes`, which nothing reads, so the
                # engine would keep the rule SILENTLY (TODO item 53).
                raise NotImplementedError(
                    "%s on %s is not implemented: rule deletions do not reach "
                    "the engine yet; see INCREMENTAL_PLAN.md §8.2"
                    % (model.command, model.node))
            if model.node in self.models:
                device = self.models[model.node]
                before = {t: len(rules) for t, rules in device._adds.items()}
                getattr(device, model.command)(model.rules)
                command_tables = {t for t, rules in device._adds.items()
                                  if len(rules) > before.get(t, 0)}
                if self._indexer is not None:
                    try:
                        self._refuse_mixed_numbering(model.node, command_tables)
                    except UpdateRefused:
                        device.reset()      # nothing of the command is kept
                        raise
                model = device

            else:
                print(
                    "Error while processing flow modification: no such dp:",
                    str(model.node),
                    file=sys.stderr
                )
                return


        # handle topology changes (e.g. by the network management)
        if model.type == "topology_command":
            cmd = model

            if cmd.mtype == "links":
                links = []
                for link in cmd.model:
                    sport, dport, bulk = link
                    try:
                        smodel = self.port_to_model[sport]
                        dmodel = self.port_to_model[dport]
                    except KeyError:
                        import pprint
                        pprint.pprint(self.links, indent=2)
                        pprint.pprint(self.port_to_model, indent=2)
                        raise


                    sportno = self.verification_engine.global_port(smodel.egress_port(sport))
                    dportno = self.verification_engine.global_port(dmodel.ingress_port(dport))

                    if cmd.command == "add":
                        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                            AggregatorService.LOGGER.debug(
                                "worker: add link to netplumber from %s:%s to %s:%s%s",
                                sport,
                                hex(sportno),
                                dport,
                                hex(dportno),
                                (" as bulk" if bulk else "")
                            )
                        nlink = self._record_link(sport, dport)
                        if bulk:
                            links.append(nlink)
                        else:
                            self.verification_engine.add_link(*nlink)

                    elif cmd.command == "del":
                        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                            AggregatorService.LOGGER.debug(
                                "worker: remove link from netplumber from %s to %s",
                                sport, dport
                            )
                        self.verification_engine.remove_link(sportno, dportno)
                        self.links[sport].remove(dport)
                        if not self.links[sport]: del self.links[sport]

                if links:
                    if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
                        AggregatorService.LOGGER.debug("worker: add all bulk links")
                    self.verification_engine.add_links_bulk(
                        links,
                        use_dynamic=_has_asyncore_socks(self.verification_engine.asyncore_socks)
                    )

                return

            elif cmd.mtype in [
                    "packet_filter",
                    "snapshot_packet_filter",
                    "application_layer_gateway",
                    "switch",
                    "router"
            ]:
                if cmd.command == "del":
                    self._remove_device(cmd.node, cmd.mtype)
                    return
                model = cmd.model

            elif cmd.mtype == "generator":
                if cmd.command == "add":
                    self._add_ports(cmd.model)
                    self.verification_engine.add_generator(cmd.model)
                elif cmd.command == "del":
                    self.verification_engine.delete_generator(cmd.node)

                return

            elif cmd.mtype == "generators":
                if cmd.command == "add":
                    for generator in cmd.model.generators:
                        self._add_ports(generator)

                    self.verification_engine.add_generators_bulk(
                        cmd.model.generators,
                        use_dynamic=_has_asyncore_socks(self.verification_engine.asyncore_socks)
                    )

# TODO: implement deletion
#                elif cmd.command == "del":
#                    self._delete_generators_bulk(cmd.node)

                return

            elif cmd.mtype == "probe":
                if cmd.command == "add":
                    self._add_ports(cmd.model)
                    self._align_ports_for_probe(cmd.model)
                    self.verification_engine.add_probe(cmd.model)
                elif cmd.command == "del":
                    self.verification_engine.delete_probe(cmd.node)

                return

            elif cmd.command == "del":
                # Without a type there is nothing to dispatch on; it used to be
                # dropped silently (TODO item 53).
                raise ValueError(
                    "cannot delete %r: the command names no type (-t)" % cmd.node)

            else:
                return


        if model.type == "slicing_command":
            cmd = model
            if cmd.command == 'add_slice':
                self.verification_engine.add_slice(cmd.slice)
            elif cmd.command == 'del_slice':
                self.verification_engine.del_slice(cmd.slice)

            return

        if self._indexer is not None and whole:
            self._sync_stable(model)
            return


        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            # The ENGINE is handed this diff, not the model it came from, so a
            # declaration left behind here never reaches an adapter at all.
            # MEASURED, not hypothesised: without this, `add_tables` saw
            # wl_stanford's 16 `mid` tables as `first_match` on the second of
            # the two calls it gets per device, although they are declared
            # `lpm`. Done here rather than in `__sub__` because there are four
            # of those and one of these.
            add.table_semantics = dict(model.table_semantics)
            for table in model._adds: # TODO: better interface :-/
                model.tables.setdefault(table, [])
                model.tables[table].extend(model._adds[table])

            model.reset()

            model = add

            #sub = self.models[model.node] - model

# TODO: fix deletion... needs exclusion of pre-, post-routing, state tables
            # remove unecessary items (with stable indices: `_sync_stable`;
            # a whole device: `_remove_device`, INCREMENTAL_PLAN.md §8.2)

            # add new items
        # TABLE_SEMANTICS_PLAN.md S4: a table DECLARED longest-prefix-match must
        # be able to mean it. Backend-neutral (a property of the rules alone) and
        # run BEFORE the model reaches any engine, so all three see the same
        # answer instead of each deciding privately -- and so a false declaration
        # is refused rather than acted on.
        #
        # Validated over the rules being ADDED, with a per-(node, table) index
        # carried across calls: rules arrive in batches, and re-scanning the
        # whole table per batch would be quadratic (wl_i2 sends 77,451).
        self._validate_declared_tables(model)

        self._add_model(model)

        self.models.setdefault(model.node, model)

        if self._indexer is not None and commanded:
            # §8.1: a control-plane command changed the device rule by rule,
            # at the indices its sender chose; what the engine now holds is the
            # stored model, and the next whole re-send is diffed against that
            for table, rules in self.models[model.node].tables.items():
                if rules and table in command_tables:
                    self._commanded.add((model.node, table))
                self._indexer.seed(model.node, table, rules)


    def _record_link(self, sport: str, dport: str) -> Tuple[str, str]:
        """ Record the link sport -> dport, in the aggregator's and the
        engine's adjacency, and return it as the engine names it: the
        (egress, ingress) pair `add_link` takes. """
        nlink = (self.port_to_model[sport].egress_port(sport),
                 self.port_to_model[dport].ingress_port(dport))
        self.links.setdefault(sport, []).append(dport)
        engine = self.verification_engine
        engine.links.setdefault(engine.global_port(nlink[0]), []).append(
            engine.global_port(nlink[1]))
        return nlink


    def _links_of(self, model: Any) -> List[Tuple[str, str]]:
        """ The external links of the stored `model`, in either direction. """
        return [(sport, dport)
                for sport, dports in self.links.items() for dport in dports
                if self.port_to_model.get(sport) is model
                or self.port_to_model.get(dport) is model]


    def _replace_device(self, old: Any, model: Any,
                        ordered: Dict[str, List[Any]], why: str) -> None:
        """ INCREMENTAL_PLAN.md §8.2, D-R6: a re-sent device whose structure
        changed (`why`) replaces the stored one, as ONE update: §8.2's
        removal, then the new model added like a new device and its links
        added again. Refused before anything is touched when a link uses a
        port the new model drops (the client deletes the link first), when
        the engine only empties a removed device, or when the new model's
        declared-LPM tables are invalid. A table the control plane filled
        and the re-send left empty keeps its rules, as in a diff. """
        node = model.node
        links = self._links_of(old)
        dead = [(s, d) for s, d in links
                if (self.port_to_model[s] is old and s not in model.ports)
                or (self.port_to_model[d] is old and d not in model.ports)]
        if dead:
            raise UpdateRefused(
                "%s: the re-sent model drops ports its links use: %s. Delete "
                "the links first." % (node, ', '.join('%s -> %s' % l for l in dead)))
        engine = self.verification_engine
        if not engine.REMOVES_DEVICES:
            raise UpdateRefused(
                "%s: %s: the re-sent model %s, and this engine cannot replace "
                "a device" % (type(engine).__name__, node, why))
        semantics_of = getattr(model, 'semantics_of', None)
        if semantics_of is not None:
            for table, rules in ordered.items():
                if semantics_of(table) == LPM and rules:
                    validate_lpm_rules(node, table, rules, {})

        carried = {t for t, rules in model.tables.items()
                   if not rules and ordered[t] and (node, t) in self._commanded}
        self._check_index_budget(
            node, {t: rules for t, rules in ordered.items() if t not in carried})
        t0 = time.perf_counter()
        self._remove_device(node, old.type)

        indexer = self._indexer
        assert indexer is not None
        model.tables = {}
        for table, rules in ordered.items():
            if table in carried:
                # as the control plane left it: its indices are the sender's
                model.tables[table] = rules
                indexer.seed(node, table, rules)
                self._commanded.add((node, table))
            else:
                model.tables[table] = indexer.emit(node, table, rules)
        self._validate_declared_tables(model)
        self._add_model(model)
        self.models[node] = model
        nlinks = [self._record_link(s, d) for s, d in links]
        for nlink in nlinks:
            engine.add_link(*nlink)
        self.update_stats = {
            'node': node, 'new': False, 'replaced': why,
            'links': len(links), 't_update_s': time.perf_counter() - t0,
        }


    def _refuse_mixed_numbering(self, node: str, tables: set) -> None:
        """ §8.1: a control-plane command's rules carry the indices its sender
        chose; a table the aggregator numbered from a whole model carries the
        indexer's. The two do not order against each other -- a sender's rule
        1 meant to follow rule 0 would land before the rule the indexer put at
        262,143 -- so a command into such a table is refused, not guessed
        at. """
        indexer = self._indexer
        assert indexer is not None
        numbered = sorted(t for t in tables
                          if indexer.last(node, t) and (node, t) not in self._commanded)
        if numbered:
            raise UpdateRefused(
                "%s: a control-plane command adds to %s, whose rules the "
                "aggregator numbered from the device model (stable indices); "
                "the command's indices do not order against them. Re-send the "
                "device whole, or run with --no-stable-indices"
                % (node, ', '.join(numbered)))


    def _check_index_budget(self, node: str, tables: Dict[str, List[Any]]) -> None:
        """ INCREMENTAL_PLAN.md §8.1 (3), owner 2026-10-15: a table with more
        rules than the engine has index slots in it is REFUSED, before the
        indexer or the engine is touched -- not truncated, wrapped or squeezed
        into indices the engine would misread. The indexer spaces from 1, so a
        budget of `b` holds `b` rules. """
        engine = self.verification_engine
        over = ["%s holds %d rules, the engine takes indices up to %d"
                % (table, len(rules), engine.max_rule_index(table))
                for table, rules in sorted(tables.items())
                if len(rules) > engine.max_rule_index(table)]
        if over:
            raise UpdateRefused(
                "%s: %s: more rules than index slots: %s"
                % (type(engine).__name__, node, '; '.join(over)))


    def _sync_stable(self, model: Any) -> None:
        """ INCREMENTAL_PLAN.md §8.1: a device model that arrived WHOLE, with
        stable indices. New: every table is spaced in its index budget and the
        model added as before. Re-sent: every table is re-numbered against its
        last emission and the ENGINE gets the difference -- the rules whose
        index left or whose content changed are deleted, the new ones
        inserted, deletes first. What the engines cannot take rule by rule (a
        table appearing or vanishing, other ports or wiring, a whole-translated
        table that changed) replaces the device (`_replace_device`, D-R6) or
        is refused before anything is touched. """
        indexer = self._indexer
        assert indexer is not None
        node = model.node
        old = self.models.get(node)
        # a table's order is its INDEX order (the index is the priority), not
        # the list order the model happens to carry (ad6/translate.py:711)
        ordered = {t: sorted(rules, key=lambda r: r.idx) for t, rules in model.tables.items()}
        if old is not None:
            # A table the control plane filled (a packet filter's routing
            # table, from routes.json) arrives EMPTY in a whole re-send of the
            # device's configuration, which does not own it: it keeps the
            # commanded rules. Re-sent WITH rules (a switch whose table is its
            # configuration, S4 on wl_cloud), it is diffed like any other.
            for table in ordered:
                if not ordered[table] and (node, table) in self._commanded:
                    ordered[table] = sorted(old.tables[table], key=lambda r: r.idx)

        if old is None:
            self._check_index_budget(node, ordered)
            model.tables = {t: indexer.emit(node, t, rules) for t, rules in ordered.items()}
            self._validate_declared_tables(model)
            self._add_model(model)
            self.models[node] = model
            self.update_stats = {'node': node, 'new': True}
            return

        why = None
        if set(ordered) != set(old.tables):
            why = "has other tables (%s)" % sorted(set(ordered) ^ set(old.tables))
        elif model.ports != old.ports or model.wiring != old.wiring:
            why = "has other ports or wiring"
        else:
            for table in ordered:
                if table.endswith(_WHOLE_TABLES) and \
                        [stable_key(r) for r in ordered[table]] != \
                        [k for _i, k in indexer.last(node, table) or []]:
                    why = "changed %s, which is translated as a whole" % table
                    break
        if why is not None:
            self._replace_device(old, model, ordered, why)
            return

        self._check_index_budget(node, ordered)
        t0 = time.perf_counter()
        windows, moved = indexer.stats['windows'], indexer.stats['moved']
        deletes: List[Tuple[str, int]] = []
        inserts: List[Any] = []
        for table, rules in ordered.items():
            if indexer.last(node, table) is None:
                # never emitted here: a switch table its control plane filled
                # rule by rule -- the engine holds the stored rules as they are
                indexer.seed(node, table, old.tables[table])
            prev = indexer.last(node, table)
            emitted = indexer.emit(node, table, rules)
            gone, new = stable_diff(prev, emitted)
            deletes.extend((table, idx) for idx in gone)
            inserts.extend(new)
            model.tables[table] = emitted

        t1 = time.perf_counter()
        for table, idx in deletes:
            self.verification_engine.delete_rule(node, table, idx)
        if inserts:
            # the declared-LPM check over what is added, as for any batch
            added = copy.copy(model)
            added.tables = {}
            for rule in inserts:
                added.tables.setdefault(rule.tid, []).append(rule)
            self._validate_declared_tables(added)
        for rule in inserts:
            self.verification_engine.insert_rule(rule)
        t2 = time.perf_counter()

        model.table_semantics = dict(model.table_semantics)
        self.models[node] = model
        self.update_stats = {
            'node': node, 'new': False,
            'deleted': len(deletes), 'inserted': len(inserts),
            'windows': indexer.stats['windows'] - windows,
            'moved': indexer.stats['moved'] - moved,
            # align + diff, and the engine's updates (INCREMENTAL_PLAN.md §8.1, 7)
            't_diff_s': t1 - t0, 't_update_s': t2 - t1,
        }

    def _align_ports_for_probe(self, model: Any) -> None:
        if model.test_path is None: return

        new_path = []
        for pathlet in model.test_path.pathlets:
            tmp = pathlet_to_json(pathlet)
            assert tmp is not None  # a normalized pathlet always converts
            if tmp['type'] == 'port':
                new_pl = json_to_pathlet({
                    'type' : 'port',
                    'port' : self.port_to_model[tmp['port']].ingress_port(tmp['port'])
                })
                new_path.append(new_pl)

            elif tmp['type'] in ['next_ports', 'last_ports']:
                new_pl = json_to_pathlet({
                    'type' : tmp['type'],
                    'ports' : [self.port_to_model[p].ingress_port(p) for p in tmp['ports']]
                })
                new_path.append(new_pl)

            else:
                new_path.append(pathlet)

        model.test_path = Path(new_path)


    def _remove_device(self, node: str, mtype: str) -> None:
        """ INCREMENTAL_PLAN.md §8.2: remove device `node` with its external
        links, as one engine update -- the caller re-verifies once, after it
        (D-R3). An engine without the primitives refuses before anything is
        touched (D-R4), and so does this for a device it does not hold. The
        stored model and the indexer's last emission go with it, so a later
        `add` of the same name starts from zero (D-R1). Generators and probes
        linked to it stay; their checks are re-verified (Q-R4). """
        model = self.models.get(node)
        if model is None or model.type != mtype:
            raise ValueError("cannot delete %s %r: no such device" % (mtype, node))
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            AggregatorService.LOGGER.debug("worker: delete %s: %s", mtype, node)

        links = self._links_of(model)
        self.verification_engine.remove_device(model, [
            (self.port_to_model[s].egress_port(s),
             self.port_to_model[d].ingress_port(d)) for s, d in links])

        for sport, dport in links:
            self.links[sport].remove(dport)
            if not self.links[sport]:
                del self.links[sport]
        self._del_ports(model)
        del self.models[node]
        if self._indexer is not None:
            self._indexer.forget(node)
        self._commanded = {k for k in self._commanded if k[0] != node}
        for key in [k for k in self._lpm_index if k[0] == node]:
            del self._lpm_index[key]


    def _add_model(self, model: Any) -> None:
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            lmsg = "worker: apply %s: %s" % (model.type, model.node)
            AggregatorService.LOGGER.debug(lmsg)

        self.verification_engine.add_tables(model)
        self.verification_engine.add_wiring(model)
        self.verification_engine.add_rules(model)
        self._add_ports(model)


    def _add_ports(self, model: Any) -> None:
        for port in model.ports:
            self.port_to_model.setdefault(port, model)


    def _del_ports(self, model: Any) -> None:
        for port in model.ports:
            if self.port_to_model.get(port) is model:
                del self.port_to_model[port]


    def _dump_aggregator(self, odir: str) -> None:
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

        with open("%s/fave.json" % odir, "w") as ofile:
            j: Dict[str, Any] = {}
            j["mapping"] = self.verification_engine.mapping.to_json()
            j["id_to_table"] = {self.verification_engine.tables[k]:k for k in self.verification_engine.tables}

            j["id_to_rule"] = {}
            for key in self.verification_engine.rule_ids:
                for elem in self.verification_engine.rule_ids[key]:
                    j["id_to_rule"][elem] = key >> 12

            j["id_to_generator"] = {
                self.verification_engine.generators[k][1]:k for k in self.verification_engine.generators
            }
            j["id_to_probe"] = {self.verification_engine.probes[k][1]:k for k in self.verification_engine.probes}
            j["id_to_port"] = {self.verification_engine.ports[k]:k for k in self.verification_engine.ports}

            j["links"] = [(src, dst) for src, dst in self.links.items()]

            ofile.write(
                json.dumps(j, sort_keys=True, indent=4, separators=(',', ': '))
            )

def _parse_servers(arg: str) -> List[Tuple[str, int]]:
    servers = []

    for host in arg.split(','):
        try:
            np_host, np_port_str = host.split(':')
            assert is_host(host)
            np_port = int(np_port_str)
        except ValueError:
            np_host = host
            assert is_unix(host)
            np_port = 0
        servers.append((np_host, np_port))

    return servers


def build_parser() -> argparse.ArgumentParser:
    """ The aggregator's command line, built separately from `main` so the
    defaults are testable without starting a service. Which options exist is
    part of the backend contract: a measurement-affecting setting that has no
    flag cannot be reproduced from the production path (AD6_PLAN.md §9.27),
    and `faithful_vlan` was exactly that until APKEEP_BACKEND.md's
    production-path parity pass found it. """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a', '--use-dynamic',
        dest='use_dynamic',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-d', '--debug',
        dest='debug',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-m', '--mapping',
        dest='mapping',
        type=lambda f: json.load(open(f))
    )
    parser.add_argument(
        '-s', '--server',
        dest='fave_addr',
        type=lambda a: a if is_ip(a) or is_domain(a) else FAVE_DEFAULT_IP,
        default=FAVE_DEFAULT_IP
    )
    parser.add_argument(
        '-p', '--port',
        dest='fave_port',
        type=lambda p: int(p) if is_port(p) else FAVE_DEFAULT_PORT,
        default=FAVE_DEFAULT_PORT
    )
    parser.add_argument(
        '-S', '--servers',
        dest='servers',
        type=_parse_servers,
        default=[(NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT)]
    )
    parser.add_argument(
        '-t', '--trace',
        dest='trace',
        action='store_const',
        const=True,
        default=False
    )
    parser.add_argument(
        '-u', '--use-unix',
        dest='use_unix',
        action='store_const',
        const=True,
        default=False
    )
    # AD6_PLAN.md §9.3 Phase 6: the production route to a non-NetPlumber
    # engine. Defaults to netplumber, so every existing invocation is
    # unaffected.
    parser.add_argument(
        '-b', '--backend',
        dest='backend',
        choices=BACKENDS,
        default=BACKEND_NETPLUMBER
    )
    # ad6-only, and measurement-affecting -- the reason Phase 6 exists at all.
    # A production path that can run only ONE configuration cannot reproduce
    # the archived numbers, and the drivers that could were deleted at §9.25.
    parser.add_argument('--grounding', dest='grounding', default=None)
    parser.add_argument('--solver', dest='solver', default=None)
    parser.add_argument(
        '--lite-acyclic',
        dest='lite_acyclic',
        action='store_const',
        const=True,
        default=False
    )
    # apkeep-only. The NDD engine is the default because the faithful VLAN
    # model below is: BDD-APKeep's single global atomic-predicate partition
    # cross-products (dst x VLAN) and finishes neither wl_stanford nor wl_i2
    # faithfully (APKEEP_NDD_EVAL.md §2.6/§2.6b), where per-field NDD builds
    # both in seconds. `bdd` stays reachable by name -- it is the comparand in
    # every Sigma-vs-Pi result.
    parser.add_argument(
        '--apkeep-engine', dest='apkeep_engine',
        choices=('bdd', 'ndd'), default='ndd')
    # Faithful VLAN handling is ON by default and this turns it OFF, rather
    # than the other way round: ad6 and NetPlumber both model VLAN admission
    # and rewrite, so an APKeep run that silently drops them is not answering
    # the same question, and a differential against it is not like-for-like.
    # The plain model stays available because it is a legitimate measurement
    # (the P7a out-stage collapse, the convergence harness) -- it just has to
    # be asked for now.
    parser.add_argument(
        '--no-vlan',
        dest='faithful_vlan',
        action='store_false',
        default=True
    )
    # veriflow-only, and measurement-affecting (VERIFLOW_PLAN.md §8): the
    # decided defaults, with the ablations selectable by name.
    parser.add_argument('--vf-fields', dest='vf_fields',
                        choices=('4+10', 'plain'), default='4+10')
    parser.add_argument('--vf-revisit', dest='vf_revisit',
                        choices=('state', 'path'), default='state')
    parser.add_argument('--vf-slicing', dest='vf_slicing',
                        choices=('device', 'network'), default='device')
    parser.add_argument('--vf-budget', dest='vf_budget', type=int, default=0)
    # MEASUREMENT_RUN_PLAN.md §5.4's guardrail, and NEVER a faithful run: order
    # every declared-LPM table shortest-prefix-first, so the default route
    # outranks every specific one. Honoured by netplumber and veriflow, which
    # order such a table themselves; see `build_engine`.
    parser.add_argument('--invert-lpm', dest='invert_lpm', action='store_true',
                        default=False)
    # INCREMENTAL_PLAN.md §8.1: stable indices are the default since
    # 2026-10-15 (owner); off reproduces V5, which ran on the generators'
    # indices.
    parser.add_argument('--no-stable-indices', dest='stable_indices',
                        action='store_false', default=True)

    return parser


def main(argv: List[str]) -> None:
    """ Connects to net_plumber backend and starts aggregator.
    """

    log_level = logging.INFO
    socks: Dict[Any, Any] = {}
    asyncore_socks: Dict[Any, Any] = {}

    logging._srcfile = None
    logging.logThreads = False
    logging.logProcesses = False

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.debug: log_level = logging.DEBUG
    if args.trace: log_level = TRACE

    os.system('rm -f {}/aggregator.log'.format(
        os.environ.get('log_dir', '/dev/shm/np')
    ))

    log_handler = logging.FileHandler(
        '{}/aggregator.log'.format(os.environ.get('log_dir', '/dev/shm/np'))
    )

    AggregatorService.LOGGER.addHandler(log_handler)
    AggregatorService.LOGGER.setLevel(log_level)

    # Only NetPlumber speaks this transport. APKeep runs in-process and ad6 as
    # a subprocess per check_compliance, so insisting on a net_plumber
    # connection under those backends would refuse to start for the absence of
    # something they never use (AD6_PLAN.md §9.3 Phase 6).
    if args.backend == BACKEND_NETPLUMBER:
        for np_server, np_port in args.servers:
            try:
                sock = jsonrpc.connect_to_netplumber(np_server, np_port)
                socks[(np_server, np_port)] = sock
                if args.use_dynamic:
                    asyncore_sock = None # NodeLinkDispatcher(np_server, np_port)
                    asyncore_socks[(np_server, np_port)] = asyncore_sock
            except jsonrpc.RPCError as err:
                AggregatorService.LOGGER.error(str(err))
                print("could not connect to server: %s %s" % (np_server, np_port), file=sys.stderr)
                parser.print_help()
                sys.exit(1)

    global AGGREGATOR
    try:
        AGGREGATOR = AggregatorService(
            socks, asyncore_socks=asyncore_socks, mapping=args.mapping,
            backend=args.backend,
            grounding=args.grounding, solver=args.solver,
            lite_acyclic=args.lite_acyclic, apkeep_engine=args.apkeep_engine,
            faithful_vlan=args.faithful_vlan,
            vf_fields=args.vf_fields, vf_revisit=args.vf_revisit,
            vf_slicing=args.vf_slicing, vf_budget=args.vf_budget,
            invert_lpm=args.invert_lpm, stable_indices=args.stable_indices)
    except ValueError as err:
        # A malformed backend option (an unknown solver, or a solver/grounding
        # combination that would silently answer the wrong question). Reported
        # here rather than as a traceback, because it is a command-line error.
        print("backend configuration error: %s" % err, file=sys.stderr)
        sys.exit(1)

    # The configuration is measurement-affecting, so the run's own log records
    # it (the generality-debt gate). EVERY backend carries a stamp since
    # 2026-10-02 -- the base class gives one, so at minimum a backend reports
    # WHOSE code it is (TODO item 31's provenance). It used to be ad6's alone,
    # and the backend name was said to be "the whole story" for the rest; it
    # was not, which is why `bench/cell_run.py` had to record `impl: null`.
    # `cell_run.py` parses this line back out of the log, so its shape is a
    # contract, not a convenience: `backend: <name> {<stamp dict>}`.
    engine = AGGREGATOR.verification_engine
    # the aggregator's own measurement-affecting setting rides along: with or
    # without stable indices the engine sees other indices (§8.1)
    detail = " %s" % (dict(engine.configuration_stamp(),
                           stable_indices=AGGREGATOR.stable_indices),)
    AggregatorService.LOGGER.info("backend: %s%s", args.backend, detail)

    register_signals()

    if args.use_unix:
        AGGREGATOR.run(FAVE_DEFAULT_UNIX)
    else:
        AGGREGATOR.run(args.fave_addr, port=args.fave_port)


if __name__ == "__main__":
    main(sys.argv[1:])
