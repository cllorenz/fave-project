#!/usr/bin/env python2

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
import getopt
import time

from pprint import pformat
from threading import Thread
from Queue import Queue

from aggregator_abstract import AbstractAggregator, TRACE
from aggregator_singleton import AGGREGATOR
from aggregator_signals import register_signals
from aggregator_util import model_from_json

from util.print_util import eprint
from util.aggregator_utils import FAVE_DEFAULT_UNIX, FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, fave_recvmsg
from util.lock_util import PreLockedFileLock
from util.packet_util import is_ip, is_domain, is_unix, is_port, is_host
from util.path_util import json_to_pathlet, pathlet_to_json, Path

import netplumber.jsonrpc as jsonrpc
from netplumber.jsonrpc import NET_PLUMBER_DEFAULT_PORT, NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_UNIX
from netplumber.adapter import NetPlumberAdapter
from netplumber.mapping import Mapping


def _print_help():
    """ Prints a usage message to stderr.
    """
    eprint(
        "aggregator [-s <server> [-p <port>]] [-S <backends>] [-m <mapping>]",
        "\t-s <server> ip address of the netplumber instance",
        "\t-p <port> the port number of the netplumber instance",
        "\t-S <backends> a list of NP backend socket identifiers, e.g., /dev/shm/np1,/dev/shm/np2,... or 1.2.3.4:44001,1.2.3.4:44002,...",
        "\t-m <mapping> a json file containing a mapping to initialize the NP adapter",
        sep="\n"
    )


class Aggregator(AbstractAggregator):
    """ This class provides FaVe's central aggregation service.
    """

    def __init__(self, socks, mapping=None):
        self.queue = Queue()
        self.models = {}
        self.port_to_model = {}
        self.links = {}
        self.stop = False
        self.net_plumber = NetPlumberAdapter(socks.values(), Aggregator.LOGGER, mapping=mapping)


    def print_aggregator(self):
        """ Prints the state to stderr.
        """
        eprint(
            "Aggregator:",
            self.mapping,
            "tables:",
            "\t%s" % self.tables,
            "ports:",
            "\t%s" % self.ports,
            "rule ids:",
            "\t%s" % self.rule_ids,
            "links:",
            "\t%s" % self.links,
            "generators:",
            "\t%s" % self.generators,
            "probes:",
            "\t%s" % self.probes,
            sep="\n"
        )


    def _handler(self):
        t_start = time.time()

        while not self.stop:
            data = self.queue.get()
            if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                Aggregator.LOGGER.debug('worker: fetched data from queue')

            if not data:
                if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                    Aggregator.LOGGER.debug('worker: ignoring empty data')
                self.queue.task_done()
                continue

            t_task_start = time.time()

            try:
                j = json.loads(data)
            except ValueError:
                Aggregator.LOGGER.fatal('worker: could not parse data: %s' % data)
                self.queue.task_done()
                return

            if Aggregator.LOGGER.isEnabledFor(TRACE):
                Aggregator.LOGGER.trace('worker: parsed data\n%s' % pformat(j, indent=2))

            if j['type'] == 'stop':
                task_type = 'stop'
                self.stop_aggr()
                self.net_plumber.stop()

            elif j['type'] == 'dump':
                dump = j
                odir = dump['dir']

                task_type = "dump %s" % ','.join([k for k in dump if k not in ['type', 'dir']])

                if dump['fave']:
                    self._dump_aggregator(odir)
                if dump['flows']:
                    self.net_plumber.dump_flows(odir)
                if dump['network']:
                    self.net_plumber.dump_plumbing_network(odir)
                if dump['pipes']:
                    self.net_plumber.dump_pipes(odir)
                if dump['trees']:
                    self.net_plumber.dump_flow_trees(odir, dump['simple'])

                lock = PreLockedFileLock("%s/.lock" % odir)
                lock.release()

            else:
                model = model_from_json(j)
                if model.type == 'topology_command':
                    task_type = model.model.type
                else:
                    task_type = model.type

                self._sync_diff(model)

            t_task_end = time.time()

            if Aggregator.LOGGER.isEnabledFor(logging.INFO):
                Aggregator.LOGGER.info(
                    "worker: completed task %s in %s seconds." % (
                        task_type, t_task_end - t_task_start
                    )
                )

            self.queue.task_done()

        t_stop = time.time()
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("worker: stop handler after %s seconds.", t_stop-t_start)


    def run(self, server, port=0):
        """ Operates FaVe's aggregation service.
        """

        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("open and bind %s socket" % ('unix' if port == 0 else 'tcp/ip'))

        # open new socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) if port == 0 else socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.bind(server if port == 0 else (server, port))

        # start thread to handle incoming config events
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("start handler thread")
        thread = Thread(target=self._handler)
        thread.daemon = True
        thread.start()

        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("listen on socket")
        sock.listen(1)

        while not self.stop:
            # accept connections on socket
            if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                Aggregator.LOGGER.debug("master: wait for connection")
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                    Aggregator.LOGGER.debug("master: listening timed out, continue loop...")
                continue
            except socket.error:
                if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                    Aggregator.LOGGER.debug("master: break listening loop due to socket error")
                Aggregator.LOGGER.exception("master: error from accept():")
                break
            else:
                if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                    Aggregator.LOGGER.debug("master: accepted connection")
                pass

            # receive data from socket
            data = fave_recvmsg(conn, logger=Aggregator.LOGGER)
            assert data != None
            if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                Aggregator.LOGGER.debug("master: read data of size %s" % len(data))

            # upon data receival enqueue
            self.queue.put(data)
            if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                Aggregator.LOGGER.debug("master: enqueued data")

        # close unix domain socket
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("master: close receiving socket")
        sock.close()

        # wait for the config event handler to finish
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("master: join queue")
        self.queue.join()

        # join thread
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("master: join handler thread")
        thread.join()

        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("master: finished run")


    def stop_aggr(self):
        """ Stops FaVe's aggregation service.
        """
        if Aggregator.LOGGER.isEnabledFor(logging.INFO):
            Aggregator.LOGGER.info("initiate stopping")
        self.stop = True


    def _sync_diff(self, model):
        if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
            Aggregator.LOGGER.debug('worker: synchronize model')

        # handle minor model changes (e.g. updates by the control plane)
        if model.type == "switch_command":
            if model.node in self.models:

                switch = self.models[model.node]

                if model.command == "add_rule":
                    switch.add_rule(model.rule.idx, model.rule)
                elif model.command == "add_rules":
                    for idx, rule in enumerate(model.rules):
                        switch.add_rule(rule.idx, rule)
                elif model.command == "remove_rule":
                    switch.remove_rule(model.rule.idx)
                elif model.command == "update_rule":
                    switch.update_rule(model.rule.idx, model.rule)
                else:
                    # ignore unknown command
                    return

                model = switch

            else:
                eprint(
                    "Error while processing flow modification: no such dp:",
                    str(model.node),
                    sep=" "
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


                    sportno = self.net_plumber.global_port(smodel.egress_port(sport))
                    dportno = self.net_plumber.global_port(dmodel.ingress_port(dport))

                    if cmd.command == "add":
                        if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                            Aggregator.LOGGER.debug(
                                "worker: add link to netplumber from %s:%s to %s:%s%s",
                                sport, hex(sportno), dport,  hex(dportno), (" as bulk" if bulk else "")
                            )
                        nlink = (smodel.egress_port(sport), dmodel.ingress_port(dport))
                        if bulk:
                            links.append(nlink)
                        self.links.setdefault(sport, [])
                        self.links[sport].append(dport)
                        self.net_plumber.links.setdefault(sportno, [])
                        self.net_plumber.links[sportno].append(dportno)

                        if not bulk:
                            self.net_plumber.add_link(*nlink)

                    elif cmd.command == "del":
                        if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                            Aggregator.LOGGER.debug(
                                "worker: remove link from netplumber from %s to %s",
                                sport, dport
                            )
                        self.net_plumber.remove_link(self.net_plumber.sock, sportno, dportno)
                        self.links[sport].remove(dport)
                        if not self.links[sport]: del self.links[sport]

                if links:
                    if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
                        Aggregator.LOGGER.debug("worker: add all bulk links")
                    self.net_plumber.add_links_bulk(links)

                return

            elif cmd.mtype in ["packet_filter", "switch", "router"]:
                model = cmd.model

            elif cmd.mtype == "generator":
                if cmd.command == "add":
                    self._add_ports(cmd.model)
                    self.net_plumber.add_generator(cmd.model)
                elif cmd.command == "del":
                    self.net_plumber.delete_generator(cmd.node)

                return

            elif cmd.mtype == "generators":
                if cmd.command == "add":
                    for generator in cmd.model.generators:
                        self._add_ports(generator)

                    self.net_plumber.add_generators_bulk(cmd.model.generators)

# TODO: implement deletion
#                elif cmd.command == "del":
#                    self._delete_generators_bulk(cmd.node)

                return

            elif cmd.mtype == "probe":
                if cmd.command == "add":
                    self._add_ports(cmd.model)
                    self._align_ports_for_probe(cmd.model)
                    self.net_plumber.add_probe(cmd.model)
                elif cmd.command == "del":
                    self.net_plumber.delete_probe(cmd.node)

                return

            else:
                return


        if model.type == "slicing_command":
            cmd = model
            if cmd.command == 'add_slice':
                self.net_plumber.add_slice(cmd.slice)
            elif cmd.command == 'del_slice':
                self.add_slice.del_slice(cmd.slice)

            return


        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            for table in model.adds:
                model.tables.setdefault(table, [])
                model.tables[table].extend(model.adds[table])

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
        if model.type in ["packet_filter", "router"]:
            self._delete_packet_filter(model)
        elif model.type == "switch":
            self._delete_switch(model)


    def _add_model(self, model):
        if Aggregator.LOGGER.isEnabledFor(logging.DEBUG):
            Aggregator.LOGGER.debug("worker: apply %s: %s" % (model.type, model.node))

        self.net_plumber.add_tables(model)
        self.net_plumber.add_wiring(model)
        self.net_plumber.add_rules(model)
        self._add_ports(model)


    def _add_ports(self, model):
        for port in model.ports:
            self.port_to_model.setdefault(port, model)


    def _del_ports(self, model):
        for port in model.ports:
            del self.port_to_model[port]


    def _delete_model(self, model):
        self.net_plumber.delete_rules(model)
        self.net_plumber.delete_wiring(model)
        self.net_plumber.delete_tables(model)
        self._del_ports(model)


    def _dump_aggregator(self, odir):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

        with open("%s/fave.json" % odir, "w") as ofile:
            j = {}
            j["mapping"] = self.net_plumber.mapping.to_json()
            j["id_to_table"] = {self.net_plumber.tables[k]:k for k in self.net_plumber.tables}

            j["id_to_rule"] = {}
            for key in self.net_plumber.rule_ids:
                for elem in self.net_plumber.rule_ids[key]:
                    j["id_to_rule"][elem] = key >> 16

            j["id_to_generator"] = {
                self.net_plumber.generators[k][1]:k for k in self.net_plumber.generators
            }
            j["id_to_probe"] = {self.net_plumber.probes[k][1]:k for k in self.net_plumber.probes}
            j["id_to_port"] = {self.net_plumber.ports[k]:k for k in self.net_plumber.ports}

            j["links"] = [(src, dst) for src, dst in self.links.iteritems()]

            ofile.write(
                json.dumps(j, sort_keys=True, indent=4, separators=(',', ': '))
            )


def main(argv):
    """ Connects to net_plumber backend and starts aggregator.
    """

    fave_addr = FAVE_DEFAULT_IP
    fave_port = FAVE_DEFAULT_PORT
    fave_unix = FAVE_DEFAULT_UNIX
    servers = [(NET_PLUMBER_DEFAULT_IP, NET_PLUMBER_DEFAULT_PORT)]
    log_level = logging.INFO
    socks = {}
    use_unix = False
    mapping = None

    logging._srcfile = None
    logging.logThreads = 0
    logging.logProcesses = 0

    try:
        opts, _args = getopt.getopt(argv, "hdm:s:p:S:tu", ["help", "debug","mapping=", "server=", "port=", "servers=", "trace", "unix"])
    except getopt.GetoptError:
        eprint("could not parse options: %s" % argv)
        _print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-m':
            mapping = json.load(open(arg))
        elif opt == '-s' and (is_ip(arg) or is_domain(arg)):
            fave_addr = arg
        elif opt == '-p':
            fave_port = int(arg) if is_port(arg) else port
        elif opt == '-u':
            use_unix = True
        elif opt == '-S':
            servers = []
            for sp in arg.split(','):
                try:
                    np_host, np_port = sp.split(':')
                    assert is_host(sp)
                    np_port = int(np_port)
                except ValueError:
                    np_host = sp
                    assert is_unix(sp)
                    np_port = 0
                servers.append((np_host, np_port))
        elif opt == '-d':
            log_level = logging.DEBUG

        elif opt == '-t':
            log_level = TRACE

    log_handler = logging.FileHandler('/dev/shm/np/aggregator.log')
    Aggregator.LOGGER.addHandler(log_handler)
    Aggregator.LOGGER.setLevel(log_level)

    for np_server, np_port in servers:
        try:
            sock = jsonrpc.connect_to_netplumber(np_server, np_port)
            socks[(np_server, np_port)] = sock
        except jsonrpc.RPCError as err:
            Aggregator.LOGGER.error(err.message)
            eprint("could not connect to server: %s %s" % (np_server, np_port))
            _print_help()
            raise
            sys.exit(1)

    global AGGREGATOR
    AGGREGATOR = Aggregator(socks, mapping=mapping)

    register_signals()

    if use_unix:
        AGGREGATOR.run(FAVE_DEFAULT_UNIX)
    else:
        AGGREGATOR.run(fave_addr, port=fave_port)


if __name__ == "__main__":
#    import yappi
#    yappi.start()
    main(sys.argv[1:])
#    yappi.stop()

#    yappi.get_func_stats().save('aggregator.profile', type='pstat')
