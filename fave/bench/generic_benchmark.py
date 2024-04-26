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
import sys
import logging
import json

import netplumber.dump_np as dumper

from util.bench_utils import create_topology, add_routes, add_sources, add_policies
from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT

TMPDIR = "/dev/shm/np"


def _unpack(topo):
    return topo['devices'], topo['links']


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
            anomalies=None
    ):
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
            k : "%s/%s" % (prefix, v) for k, v in files.items()
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
            "python3 ../policy_translator/policy_translator.py " + ' '.join(
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
            "python3 bench/reach_csv_to_checks.py " + ' '.join(
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
        os.system("python3 %s/inventorygen.py" % self.prefix)
        self.logger.info("generated inventory.")

        self._convert_policy_to_checks()

        self.logger.info("generate topology, routes, and probes...")
        os.system("python3 %s/topogen.py" % self.prefix)
        os.system("python3 %s/routegen.py" % self.prefix)
        os.system("python3 %s/policygen.py" % self.prefix)
        self.logger.info("generated topology, routes, and probes.")


    def _post_preparation(self):
        pass


    def _startup(self):
        self.logger.info("starting netplumber...")
        for number_ in range(1, self.threads+1):
            if self.use_unix and not self.use_tcp_np:
                sockopt = "-u /dev/shm/np%d.socket" % number_
            else:
                sockopt = "-s 127.0.0.1 -p %d" % (44000+number_)

            if self.length: sockopt += " -L %d" % self.length

            os.system("bash scripts/start_np.sh -l %s %s" % (self.files['np_config'], sockopt))
        self.logger.info("started netplumber.")

        self.logger.info("starting aggregator...")
        aggr_args = [
            "/dev/shm/np%d.socket" % no for no in range(1, self.threads+1)
        ] if self.use_unix else [
            "127.0.0.1:%d" % no for no in range(44001, 44001+self.threads)
        ]

        os.system(
            "bash scripts/start_aggr.sh -S %s %s %s" % (
                ','.join(aggr_args),
                "-u" if self.use_unix else "",
                "-m %s" % self.mapping if self.mapping else ""
            )
        )
        self.logger.info("started aggregator.")


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
        os.system("python3 misc/await_fave.py")


    def _compliance(self):
        self.logger.info("checking flow trees...")
#        os.system("bash scripts/check_parallel.sh %s %s %s" % (
#            self.files['checks'], self.threads, "np_dump"
#        ))
        os.system("python3 bench/compliance_checker.py %s %s" % (
            "-u" if self.use_unix else "",
            self.files['checks']
        ))
        self.logger.info("checked flow trees.")

#        os.system("rm -f np_dump/.lock")


    def _anomalies(self):
        self.logger.info("checking for anomalies...")
        fave = connect_to_fave(
            FAVE_DEFAULT_UNIX
        ) if self.use_unix else connect_to_fave(
            FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
        )
        msg = {'type':'check_anomalies'}
        msg.update(self.anomalies)
        fave_sendmsg(fave, json.dumps(msg))
        fave.close()
        self.logger.info("checked for anomalies.")


    def _report(self):
        self.logger.info("generating report...")
        os.system("python3 reporting/report.py %s" % ("-u" if self.use_unix else ""))
        os.system("pandoc report.md -o report.pdf")
        self.logger.info("report generated.")


    def run(self):
        """ Runs the benchmark.
        """

        self._pre_preparation()
        self._preparation()
        self._post_preparation()
        self._startup()
        self._initialization()
        self._reachability()
        self._compliance()
        self._anomalies()
        self._report()
        if self.use_dump: self._dump_fave()
        else: self._wait_for_fave()
        self._teardown()
