#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module provides a generic benchmark class.
"""

import os
import os.path
import shlex
import sys
import logging
import json

import netplumber.dump_np as dumper

from util.bench_utils import create_topology, add_routes, add_sources, add_policies
from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util import barrier
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
# AD6_PLAN.md §9.28: which engine to run, and what it can do. Imported rather
# than re-listed so the harness and the aggregator cannot disagree about either.
from aggregator.aggregator_service import (
    BACKEND_NETPLUMBER, BACKENDS, BACKENDS_NEEDING_NETPLUMBER,
    BACKENDS_WITH_ANOMALIES,
)

TMPDIR = "/dev/shm/np"


def _unpack(topo):
    return topo['devices'], topo['links']


# The interpreter THIS process is running under, quoted for the shell -- never a
# bare "python3".
#
# Imported by the workload benchmarks too (wl_ifi/wl_tum/wl_shadow/wl_expand/
# wl_state_snapshots), which spawn their own sub-steps the same way.
#
# Every sub-step below is spawned through os.system(), so a bare "python3" is
# whatever PATH resolves first, which in a container whose venv is not activated
# is the SYSTEM interpreter with none of FaVe's dependencies. The failure that
# produces is maximally misleading: the aggregator dies on `No module named
# 'filelock'` in a backgrounded process nobody reads, the benchmark then cannot
# reach FaVe, and every flow check fails as though the MODEL were wrong (the same
# shape as the net_plumber-not-on-PATH bug, see test.sh's resolve_net_plumber).
# sys.executable is exact by construction and needs no environment plumbing.
PYTHON = shlex.quote(sys.executable)


def _exit_code(status):
    """ Decode an `os.system()` wait status into a plain exit code (negative for
    a signal). Unlike `os.waitstatus_to_exitcode` this never raises, so checking
    a sub-step can't itself become a new crash path in a benchmark run. """
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return status


class GenericBenchmark(object):
    """ This class provides a canonical benchmark and can be customized by sub classes.
    """

    def __init__(
            self,
            prefix,
            extra_files=None,
            use_dump=False,
            use_unix=True,
            use_tcp_np=False,
            logger=None,
            threads=1,
            use_interweaving=True,
            strict=False,
            use_internet=True,
            ip=None,
            length=0,
            suffix='',
            mapping=None,
            anomalies=None,
            backend=BACKEND_NETPLUMBER,
            engine_options=''
    ):
        # AD6_PLAN.md §9.28: which verification engine this run uses.
        # `engine_options` is passed through to the aggregator verbatim (e.g.
        # "--solver cadical195 --lite-acyclic"); this harness has no business
        # knowing an engine's vocabulary, and the aggregator validates it and
        # exits non-zero on a bad value before any model is built.
        #
        # Overridable from the environment so an existing benchmark can be run
        # on another engine WITHOUT editing its driver -- every wl_*/benchmark.py
        # constructs its subclass with hardcoded arguments, so a parameter alone
        # would reach none of them.
        backend = os.environ.get('FAVE_BACKEND', backend)
        if backend not in BACKENDS:
            raise ValueError(
                "unknown backend %r -- expected one of %s" % (
                    backend, ', '.join(repr(b) for b in BACKENDS)))
        self.backend = backend
        self.engine_options = os.environ.get('FAVE_ENGINE_OPTIONS', engine_options)

        self.prefix = prefix
        files = {
            "inventory" : "inventory.json",
            "topology" : "topology.json",
            "routes" : "routes.json",
            "sources" : "sources.json",
            "policies" : "policies.json",
            "checks" : "checks.json",
            "cchecks" : "cchecks.json",
            "reach_csv" : "reachability.csv",
            "reach_json" : "reachable.json",
            "roles_services" : "roles_and_services.txt",
            "reach_policies" : "reach.txt",
            "np_config" : 'np.conf'
        }

        self.files = {
            k : "%s/%s" % (prefix, v) for k, v in list(files.items())
        }

        if extra_files:
            self.files.update(extra_files)

        self.use_dump = use_dump
        self.use_unix = use_unix
        self.use_tcp_np = use_tcp_np
        self.use_interweaving = use_interweaving
        self.strict = strict
        self.use_internet = use_internet
        self.ip = ip
        self.length = length
        self.suffix = suffix
        self.mapping = mapping

        self.logger = logger if logger else logging.getLogger(prefix)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.setLevel(logging.DEBUG)

        if not os.path.exists(TMPDIR):
            os.system("mkdir -p %s" % TMPDIR)

        logging.basicConfig(
            format='%(asctime)s [%(name)s.%(levelname)s] - %(message)s',
            level=logging.INFO,
            filename="%s/fave.log" % TMPDIR,
            filemode='w'
        )

        self.threads = threads

        self.anomalies = anomalies if anomalies is not None else {}

    def _pre_preparation(self):
        pass


    def _delete_artifacts(self):
        os.system("mkdir -p %s" % TMPDIR)
        self.logger.info("deleting old logs and measurements...")
        os.system("rm -rf %s/*" % TMPDIR)
        self.logger.info("deleted old logs and measurements.")
        os.system("rm -f %s/../*.socket" % TMPDIR)


    def _generate_policy_matrix(self):
        self.logger.info("generate policy matrix...")
        os.system(
            "%s ../policy_translator/policy_translator.py " % PYTHON + ' '.join(
                (["--strict"] if self.strict else []) +
                (["--no-internet"] if not self.use_internet else []) +
                (
                    [
                        "--roles %s" % self.files['roles_json']
                    ] if 'roles_json' in self.files else []
                ) + [
                    "--csv", "--out", self.files['reach_csv'],
                    self.files['roles_services'],
                    self.files['reach_policies']
                ]
            )
        )
        self.logger.info("generated policy matrix.")


    def _convert_policy_to_checks(self):
        self.logger.info("convert policy matrix to checks...")
        os.system(
            "%s bench/reach_csv_to_checks.py " % PYTHON + ' '.join(
                (['-s', self.suffix] if self.suffix else []) + [
                    '-p', self.files['reach_csv'],
                    '-m', self.files['inventory'],
                    '-c', self.files['checks'],
                    '--cchecks', self.files['cchecks'],
                    '-j', self.files['reach_json']
                ]
            )
        )
        self.logger.info("converted policy matrix.")


    def _preparation(self):
        self._delete_artifacts()

        self._generate_policy_matrix()

        self.logger.info("generate inventory...")
        os.system("%s %s/inventorygen.py" % (PYTHON, self.prefix))
        self.logger.info("generated inventory.")

        self._convert_policy_to_checks()

        self.logger.info("generate topology, routes, and probes...")
        os.system("%s %s/topogen.py" % (PYTHON, self.prefix))
        os.system("%s %s/routegen.py" % (PYTHON, self.prefix))
        os.system("%s %s/policygen.py" % (PYTHON, self.prefix))
        self.logger.info("generated topology, routes, and probes.")


    def _post_preparation(self):
        pass


    def _startup(self):
        # AD6_PLAN.md §9.28: only the netplumber backend has a separate backend
        # PROCESS. APKeep runs in-process and ad6 as a subprocess per
        # check_compliance, so starting net_plumber for them would leave a
        # daemon nothing connects to -- and on a small /dev/shm its logs are
        # not free.
        if self.backend in BACKENDS_NEEDING_NETPLUMBER:
            self.logger.info("starting netplumber...")
            for number_ in range(1, self.threads+1):
                if self.use_unix and not self.use_tcp_np:
                    sockopt = "-u /dev/shm/np%d.socket" % number_
                else:
                    sockopt = "-s 127.0.0.1 -p %d" % (44000+number_)

                if self.length: sockopt += " -L %d" % self.length

                os.system("bash scripts/start_np.sh -l %s %s" % (self.files['np_config'], sockopt))
            self.logger.info("started netplumber.")
        else:
            self.logger.info(
                "backend %s needs no netplumber process; not starting one",
                self.backend)

        self.logger.info("starting aggregator (backend: %s%s)...",
                         self.backend,
                         " %s" % self.engine_options if self.engine_options else "")
        aggr_args = [
            "/dev/shm/np%d.socket" % no for no in range(1, self.threads+1)
        ] if self.use_unix else [
            "127.0.0.1:%d" % no for no in range(44001, 44001+self.threads)
        ]

        os.system(
            "bash scripts/start_aggr.sh -S %s %s %s -b %s %s" % (
                ','.join(aggr_args),
                "-u" if self.use_unix else "",
                "-m %s" % self.mapping if self.mapping else "",
                self.backend,
                "-X %s" % shlex.quote(self.engine_options) if self.engine_options else ""
            )
        )
        self.logger.info("started aggregator.")

        self._wait_for_fave()


    def _teardown(self):
        self.logger.info("stopping fave and netplumber...")
        os.system("bash scripts/stop_fave.sh %s" % ("-u" if self.use_unix else ""))
        self.logger.info("fave ordered to stop")


    def _initialization(self):
        self.logger.info("initialize topology...")
        with open(self.files['topology'], 'r') as raw_topology:
            devices, links = _unpack(json.load(raw_topology))

            create_topology(
                devices, links, use_unix=self.use_unix, interweave=self.use_interweaving
            )
        self.logger.info("topology sent to fave")


        self.logger.info("initialize routes...")
        with open(self.files['routes'], 'r') as raw_routes:
            routes = json.load(raw_routes)

            add_routes(routes, use_unix=self.use_unix)
        self.logger.info("routes sent to fave")

        self.logger.info("initialize probes...")
        with open(self.files['policies'], 'r') as raw_policies:
            probes, links = _unpack(json.load(raw_policies))

            add_policies(probes, links, use_unix=self.use_unix)
        self.logger.info("probes sent to fave")


    def _reachability(self):
        self.logger.info("initialize sources...")
        with open(self.files['sources'], 'r') as raw_sources:
            sources, links = _unpack(json.load(raw_sources))
            add_sources(sources, links, use_unix=self.use_unix)
        self.logger.info("sources sent to fave")


    def _dump_fave(self):
        self.logger.info("dumping fave and netplumber...")
        dumper.main(["-atn%s" % ("u" if self.use_unix else "")])
        self.logger.info("fave ordered to dump")


    def _wait_for_fave(self):
        self.logger.info("wait for fave")
        os.system("%s misc/await_fave.py" % PYTHON)


    def _compliance(self):
        self.logger.info("checking flow trees...")
#        os.system("bash scripts/check_parallel.sh %s %s %s" % (
#            self.files['checks'], self.threads, "np_dump"
#        ))
        cmd = "%s bench/compliance_checker.py %s %s" % (
            PYTHON,
            "-u" if self.use_unix else "",
            self.files['checks']
        )
        code = _exit_code(os.system(cmd))
        if code != 0:
            # FATAL, unlike _report's non-fatal sub-steps. The exit status used
            # to be discarded and "checked flow trees." logged unconditionally,
            # so a checker that ABORTED was indistinguishable from one that
            # found nothing -- and the report then read "No compliance
            # violations have been found" for a verdict nobody computed. Found
            # running wl_example on the ad6 backend (AD6_PLAN.md §9.28), where
            # the checker correctly refused a `protocol` condition that query
            # path cannot force; but it is not backend-specific, and this is the
            # one step whose result the whole benchmark exists to produce.
            raise RuntimeError(
                "compliance check FAILED (exit %s): %s -- the run has no "
                "verdict, and reporting one anyway is how a benchmark comes to "
                "publish a number nobody computed (TODO.md items 1i/1n/1p)."
                % (code, cmd))
        self.logger.info("checked flow trees.")

#        os.system("rm -f np_dump/.lock")


    def _anomalies(self):
        # AD6_PLAN.md §9.28: `Ad6Adapter.check_anomalies` raises
        # NotImplementedError BY DESIGN (§9.4 names the anomaly queries as a
        # documented gap, not a goal), and APKeep offers none either. Skipped
        # rather than attempted: the request is barrier-guarded, so sending it
        # would abort the run on a capability the engine never claimed. Said out
        # loud, because a silently-skipped verification step is how a benchmark
        # comes to report a verdict it never computed.
        if self.backend not in BACKENDS_WITH_ANOMALIES:
            self.logger.info(
                "SKIPPED anomaly check: backend %s does not implement it "
                "(this run's verdict covers compliance only)", self.backend)
            return

        self.logger.info("checking for anomalies...")
        fave = connect_to_fave(
            FAVE_DEFAULT_UNIX
        ) if self.use_unix else connect_to_fave(
            FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
        )
        # Barrier-guarded and blocking (TODO.md item 1r): unlike _compliance
        # and _report this posts the request in-process, so without the wait it
        # would return before FaVe had looked for a single anomaly.
        guard = barrier.arm()
        msg = {'type':'check_anomalies'}
        msg.update(self.anomalies)
        msg['barrier'] = guard          # after update(): never clobberable
        fave_sendmsg(fave, json.dumps(msg))
        fave.close()
        barrier.wait(guard)
        self.logger.info("checked for anomalies.")


    def _report(self):
        self.logger.info("generating report...")

        # Both steps used to discard their exit status, so a crashing report.py
        # or a missing pandoc still logged "report generated." and the run
        # carried on as if it had one -- the swallowed-sub-step pattern of
        # TODO.md items 1i/1n/1p. Report what actually happened instead.
        #
        # Deliberately NON-FATAL: by the time _report runs the verification
        # verdict is already computed, and the report is a presentation
        # artifact. Whether a failed sub-step should fail the whole benchmark is
        # the open decision in TODO.md item 1n, not something to settle here.
        steps = (
            ("report.md", "%s reporting/report.py %s" % (
                PYTHON, "-u" if self.use_unix else ""
            )),
            ("report.pdf", "pandoc report.md -o report.pdf"),
        )

        missing = []
        for artifact, cmd in steps:
            code = _exit_code(os.system(cmd))
            if code != 0:
                missing.append(artifact)
                self.logger.error(
                    "report step failed (exit %s), %s not generated: %s",
                    code, artifact, cmd
                )

        if missing:
            self.logger.error(
                "report INCOMPLETE -- not generated: %s", ", ".join(missing)
            )
        else:
            self.logger.info("report generated.")


    def run(self):
        """ Runs the benchmark.
        """

        self._pre_preparation()
        self._preparation()
        self._post_preparation()
        # From here on a daemon may be running, so teardown is unconditional.
        # `_compliance` is FATAL (see there), and before this a raising step
        # left the aggregator -- and net_plumber -- alive, holding their ports
        # and a stale /dev/shm/np/aggregator.owner that the NEXT run's barriers
        # would then wait on. A failed benchmark must not sabotage the next one.
        self._startup()
        try:
            self._initialization()
            self._reachability()
            self._compliance()
            self._anomalies()
            self._report()
            if self.use_dump: self._dump_fave()
            else: self._wait_for_fave()
        finally:
            try:
                self._teardown()
            except Exception:                   # pylint: disable=broad-except
                # Never let a teardown failure REPLACE the real error: the
                # exception propagating out of the try block is the one worth
                # reading, and a bare `finally` would swallow it.
                self.logger.exception("teardown failed")
