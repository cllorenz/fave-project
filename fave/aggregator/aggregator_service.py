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

import socket
import os
import json
import logging
import sys
import argparse
import time

from pprint import pformat
from threading import Thread
from queue import Queue

from aggregator.aggregator_abstract import AbstractAggregator, TRACE
from aggregator.aggregator_singleton import AGGREGATOR
from aggregator.aggregator_signals import register_signals

from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
from util.aggregator_utils import fave_recvmsg
from util.lock_util import PreLockedFileLock
from util.packet_util import is_ip, is_domain, is_unix, is_port, is_host
from util.path_util import json_to_pathlet, pathlet_to_json, Path
from util.dynamic_distribution import NodeLinkDispatcher

import netplumber.jsonrpc as jsonrpc
from netplumber.jsonrpc import NET_PLUMBER_DEFAULT_PORT, NET_PLUMBER_DEFAULT_IP
from netplumber.adapter import NetPlumberAdapter

from netplumber.slice import SlicingCommand
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel, StateCommand
from devices.switch import SwitchModel, SwitchCommand
from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from topology.topology import LinksModel, TopologyCommand

from reporting.reporter import Reporter

from rule.rule_model import RuleField

class AggregatorService(AbstractAggregator):
    """ This class provides FaVe's central aggregation service.
    """

    def __init__(self, socks, asyncore_socks, mapping=None):
        self.queue = Queue()
        self.models = {}
        self.port_to_model = {}
        self.links = {}
        self.stop = False
        self.verification_engine = NetPlumberAdapter(
            list(socks.values()),
            AggregatorService.LOGGER,
            asyncore_socks=asyncore_socks,
            mapping=mapping
        )
        # XXX: make log file configurable
        self.reporter = Reporter(self, '/dev/shm/np/stdout.log')
        self.reporter.daemon = True
        self.model_types = {
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


    def print_aggregator(self):
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


    def _model_from_json(self, j):
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
            return model.from_json(j)


    def _handler(self):
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

            if j['type'] == 'stop':
                task_type = 'stop'
                self.stop_aggr()
                self.verification_engine.stop()

            elif j['type'] == 'report':
                task_type = 'report'
                report = j
                self.reporter.dump_report(report['file'])
                self.reporter.mark_compliance()
                self.reporter.mark_anomalies()

            elif j['type'] == 'check_compliance':
                task_type = 'check_compliance'
                rules = {}
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
                    task_type = model.model.type
                else:
                    task_type = model.type

                self._sync_diff(model)

            t_task_end = time.time()

            if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
                emsg = "worker: completed task %s in %s seconds." % (
                    task_type, t_task_end - t_task_start
                )
                AggregatorService.LOGGER.info(emsg)

            self.queue.task_done()

        t_stop = time.time()
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("worker: stop handler after %s seconds.", t_stop-t_start)


    def run(self, server, port=0):
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
            assert data != None
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

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: finished run")

        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("master: stop reporter")
        self.reporter.stop()


    def stop_aggr(self):
        """ Stops FaVe's aggregation service.
        """
        if AggregatorService.LOGGER.isEnabledFor(logging.INFO):
            AggregatorService.LOGGER.info("worker: initiate stopping")
        self.stop = True


    def _sync_diff(self, model):
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            AggregatorService.LOGGER.debug('worker: synchronize model')


        # handle minor model changes (e.g. updates by the control plane)
        if model.type in ["switch_command", 'state_command', 'relay_command']:
            if model.node in self.models:
                device = self.models[model.node]
                getattr(device, model.command)(model.rules)
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
                        nlink = (smodel.egress_port(sport), dmodel.ingress_port(dport))
                        if bulk:
                            links.append(nlink)
                        self.links.setdefault(sport, [])
                        self.links[sport].append(dport)
                        self.verification_engine.links.setdefault(sportno, [])
                        self.verification_engine.links[sportno].append(dportno)

                        if not bulk:
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
                        use_dynamic=(self.verification_engine.asyncore_socks != {})
                    )

                return

            elif cmd.mtype in [
                    "packet_filter",
                    "snapshot_packet_filter",
                    "application_layer_gateway",
                    "switch",
                    "router"
            ]:
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
                        use_dynamic=(self.verification_engine.asyncore_socks != {})
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

            else:
                return


        if model.type == "slicing_command":
            cmd = model
            if cmd.command == 'add_slice':
                self.verification_engine.add_slice(cmd.slice)
            elif cmd.command == 'del_slice':
                self.verification_engine.del_slice(cmd.slice)

            return


        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            for table in model._adds: # TODO: better interface :-/
                model.tables.setdefault(table, [])
                model.tables[table].extend(model._adds[table])

            model.reset()

            model = add

            #sub = self.models[model.node] - model

# TODO: fix deletion... needs exclusion of pre-, post-routing, state tables
            # remove unecessary items
#            self._delete_model(sub)

            # add new items
        self._add_model(model)

        self.models.setdefault(model.node, model)


    def _align_ports_for_probe(self, model):
        if model.test_path is None: return

        new_path = []
        for pathlet in model.test_path.pathlets:
            tmp = pathlet_to_json(pathlet)
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


    def _delete_model(self, model):
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            lmsg = "worker: delete %s: %s" % (model.type, model.node)
            AggregatorService.LOGGER.debug(lmsg)
        self.verification_engine.delete_rules(model)
        self.verification_engine.delete_wiring(model)
        self.verification_engine.delete_tables(model)


    def _add_model(self, model):
        if AggregatorService.LOGGER.isEnabledFor(logging.DEBUG):
            lmsg = "worker: apply %s: %s" % (model.type, model.node)
            AggregatorService.LOGGER.debug(lmsg)

        self.verification_engine.add_tables(model)
        self.verification_engine.add_wiring(model)
        self.verification_engine.add_rules(model)
        self._add_ports(model)


    def _add_ports(self, model):
        for port in model.ports:
            self.port_to_model.setdefault(port, model)


    def _del_ports(self, model):
        for port in model.ports:
            del self.port_to_model[port]


    def _delete_model(self, model):
        self.verification_engine.delete_rules(model)
        self.verification_engine.delete_wiring(model)
        self.verification_engine.delete_tables(model)
        self._del_ports(model)


    def _dump_aggregator(self, odir):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

        with open("%s/fave.json" % odir, "w") as ofile:
            j = {}
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

def _parse_servers(arg):
    servers = []

    for host in arg.split(','):
        try:
            np_host, np_port = host.split(':')
            assert is_host(host)
            np_port = int(np_port)
        except ValueError:
            np_host = host
            assert is_unix(host)
            np_port = 0
        servers.append((np_host, np_port))

    return servers


def main(argv):
    """ Connects to net_plumber backend and starts aggregator.
    """

    log_level = logging.INFO
    socks = {}
    asyncore_socks = {}

    logging._srcfile = None
    logging.logThreads = 0
    logging.logProcesses = 0

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

    for np_server, np_port in args.servers:
        try:
            sock = jsonrpc.connect_to_netplumber(np_server, np_port)
            socks[(np_server, np_port)] = sock
            if args.use_dynamic:
                asyncore_sock = NodeLinkDispatcher(np_server, np_port)
                asyncore_socks[(np_server, np_port)] = asyncore_sock
        except jsonrpc.RPCError as err:
            AggregatorService.LOGGER.error(err.message)
            print("could not connect to server: %s %s" % (np_server, np_port), file=sys.stderr)
            parser.print_help()
            sys.exit(1)

    global AGGREGATOR
    AGGREGATOR = AggregatorService(socks, asyncore_socks=asyncore_socks, mapping=args.mapping)

    register_signals()

    if args.use_unix:
        AGGREGATOR.run(FAVE_DEFAULT_UNIX)
    else:
        AGGREGATOR.run(args.fave_addr, port=args.fave_port)


if __name__ == "__main__":
    main(sys.argv[1:])
