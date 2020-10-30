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

from threading import Thread
from Queue import Queue
from copy import deepcopy as dc

#from aggregator_profiler import profile_method
from aggregator_abstract import AbstractAggregator
from aggregator_singleton import AGGREGATOR
from aggregator_signals import register_signals
from aggregator_util import model_from_json, normalize_port
from aggregator_util import calc_port, calc_rule_index

from util.print_util import eprint
from util.aggregator_utils import UDS_ADDR
from util.lock_util import PreLockedFileLock
from util.packet_util import is_ip, is_domain, is_unix, is_port

import netplumber.jsonrpc as jsonrpc
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import copy_field_between_vectors, set_field_in_vector
from netplumber.vector import align_headerspace
from netplumber.vector import Vector

from ip6np.generator import field_value_to_bitvector

from openflow.switch import SwitchRule, Forward, Miss, Rewrite


def _print_help():
    """ Prints a usage message to stderr.
    """
    eprint(
        "aggregator -s <server> -p <port>",
        "\t-s <server> ip address of the instance",
        "\t-p <port> the port number of the netplumber instance",
        sep="\n"
    )


class Aggregator(AbstractAggregator):
    """ This class provides FaVe's central aggregation service.
    """

    def __init__(self, sock):
        self.sock = sock
        self.queue = Queue()
        self.models = {}
        self.mapping = Mapping(0)
        self.tables = {}
        self.fresh_table_index = 1
        self.ports = {}
        self.rule_ids = {}
        self.links = {}
        self.stop = False
        self.generators = {}
        self.probes = {}


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


    #@profile_method
    def _handler(self):
        t_start = time.time()

        while not self.stop:
            data = self.queue.get()
            Aggregator.LOGGER.debug('worker: fetched data from queue')

            if not data:
                Aggregator.LOGGER.debug('worker: ignoring empty data')
                self.queue.task_done()
                continue

            t_task_start = time.time()

            try:
                j = json.loads(data)
            except ValueError:
                Aggregator.LOGGER.exception('worker: could not parse data: %s' % data)
                self.queue.task_done()
                return

            if j['type'] == 'stop':
                task_typ = 'stop'
                self.stop_aggr()
                jsonrpc.stop(self.sock)

            elif j['type'] == 'dump':
                dump = j
                odir = dump['dir']

                task_type = "dump %s" % ','.join([k for k in dump if k not in ['type', 'dir']])

                if dump['fave']:
                    self._dump_aggregator(odir)
                if dump['flows']:
                    jsonrpc.dump_flows(self.sock, odir)
                if dump['network']:
                    jsonrpc.dump_plumbing_network(self.sock, odir)
                if dump['pipes']:
                    jsonrpc.dump_pipes(self.sock, odir)
                if dump['trees']:
                    jsonrpc.dump_flow_trees(self.sock, odir)

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

            Aggregator.LOGGER.info("worker: completed task %s in %s seconds." % (task_type, t_task_end - t_task_start))

            self.queue.task_done()

        t_stop = time.time()
        Aggregator.LOGGER.info("worker: stop handler after %s seconds.", t_stop-t_start)


    def run(self):
        """ Operates FaVe's aggregation service.
        """

        # open new unix domain socket
        Aggregator.LOGGER.info("open and bind uds socket")
        uds = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        uds.settimeout(1.0)
        uds.bind(UDS_ADDR)

        # start thread to handle incoming config events
        Aggregator.LOGGER.info("start handler thread")
        thread = Thread(target=self._handler)
        thread.daemon = True
        thread.start()

        Aggregator.LOGGER.info("listen on socket")
        uds.listen(1)

        only_conn = lambda x: x[0]
        while not self.stop:
            # accept connections on unix domain socket
            Aggregator.LOGGER.debug("master: wait for connection")
            try:
                conn = only_conn(uds.accept())
            except socket.timeout:
                Aggregator.LOGGER.debug("master: listening timed out, continue loop...")
                continue
            except socket.error:
                Aggregator.LOGGER.debug("master: break listening loop due to socket error")
                Aggregator.LOGGER.exception("master: error from accept():")
                break

            Aggregator.LOGGER.debug("master: accepted connection")

            # receive data from unix domain socket
            data = ""
            while True:
                part = conn.recv(Aggregator.BUF_SIZE)
                data += part
                if len(part) < Aggregator.BUF_SIZE:
                    Aggregator.LOGGER.debug("master: read data of size %s", len(data))
                    break

            # upon data receival enqueue
            self.queue.put(data)
            Aggregator.LOGGER.debug("master: enqueued data")

        # close unix domain socket
        Aggregator.LOGGER.info("master: close receiving socket")
        uds.close()

        # wait for the config event handler to finish
        Aggregator.LOGGER.info("master: join queue")
        self.queue.join()

        # join thread
        Aggregator.LOGGER.info("master: join handler thread")
        thread.join()

        Aggregator.LOGGER.info("master: finished run")


    def stop_aggr(self):
        """ Stops FaVe's aggregation service.
        """
        Aggregator.LOGGER.info("initiate stopping")
        self.stop = True



    #@profile_method
    def _sync_diff(self, model):
        Aggregator.LOGGER.debug('worker: synchronize model')

        # extend global mapping
        mlength = self.mapping.length

        if model.type in ["packet_filter", "router"]:
            Aggregator.LOGGER.debug("extend mapping for adding packet filters and routers")
            self._extend_mapping(model.mapping)

        elif model.type == "switch_command" and model.command == "add_rule":
            Aggregator.LOGGER.debug("extend mapping for adding switch rules")
            self._extend_mapping(model.rule.mapping)

        elif model.type == "topology_command" and \
                model.command == 'add' and \
                model.model.type in ['probe', 'generator', 'router', 'packet_filter']:
            Aggregator.LOGGER.debug("extend mapping for adding probes, generators, routers, and packet filters")
            self._extend_mapping(model.model.mapping)

        elif model.type == "topology_command" and \
                model.command == 'add' and \
                model.model.type == 'generators':
            Aggregator.LOGGER.debug("extend mapping for adding generators")
            for generator in model.model.generators:
                self._extend_mapping(generator.mapping)

        elif model.type == "slicing_command" and model.command == 'add_slice':
            Aggregator.LOGGER.debug("extend mapping for adding slices")
            self._extend_mapping(model.slice.mapping)

        if mlength < self.mapping.length:
            Aggregator.LOGGER.debug(
                "worker: expand to length %s", self.mapping.length
            )
            jsonrpc.expand(self.sock, self.mapping.length)

        # handle minor model changes (e.g. updates by the control plane)
        if model.type == "switch_command":
            if model.node in self.models:

                switch = dc(self.models[model.node]) # XXX: is there a more efficient way than copying?

                if model.command == "add_rule":
                    switch.add_rule(model.rule.idx, model.rule)
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
                    sport, dport = link
                    sport = self._global_port(sport)
                    dport = self._global_port(dport)

                    if cmd.command == "add":
                        Aggregator.LOGGER.debug(
                            "worker: add link to netplumber from %s to %s", hex(sport), hex(dport)
                        )
                        links.append((sport, dport))
                        self.links[sport] = dport
                    elif cmd.command == "del":
                        Aggregator.LOGGER.debug(
                            "worker: remove link from netplumber from %s to %s", sport, dport
                        )
                        jsonrpc.remove_link(self.sock, sport, dport)
                        del self.links[sport]

                jsonrpc.add_links_bulk(self.sock, links)

            elif cmd.mtype == "packet_filter":
                if cmd.command == "add":
                    self._add_packet_filter(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self._delete_packet_filter(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "switch":
                if cmd.command == "add":
                    self._add_switch(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self._delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "router":
                if cmd.command == "add":
                    self._add_router(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self._delete_router(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "generator":
                if cmd.command == "add":
                    self._add_generator(cmd.model)
                elif cmd.command == "del":
                    self._delete_generator(cmd.node)

            elif cmd.mtype == "generators":
                if cmd.command == "add":
                    self._add_generators_bulk(cmd.model.generators)
# TODO: implement deletion
#                elif cmd.command == "del":
#                    self._delete_generators_bulk(cmd.node)

            elif cmd.mtype == "probe":
                if cmd.command == "add":
                    self._add_probe(cmd.model)
                elif cmd.command == "del":
                    self._delete_probe(cmd.node)

            return


        if model.type == "slicing_command":
            cmd = model
            if cmd.command == 'add_slice':
                self._add_slice(cmd.slice)
            elif cmd.command == 'del_slice':
                self._del_slice(cmd.slice)

            return


        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            #sub = self.models[model.node] - model

# TODO: fix deletion... needs exclusion of pre-, post-routing, state tables
            # remove unecessary items
#            self._delete_model(sub)

            # add new items
            self._add_model(add)

        else:
            self.models[model.node] = model

            # add model completely
            self._add_model(model)


    def _delete_model(self, model):
        if model.type in ["packet_filter", "router"]:
            self._delete_packet_filter(model)
        elif model.type == "switch":
            self._delete_switch(model)

    def _add_model(self, model):
        if model.type == "packet_filter":
            self._add_packet_filter(model)
        elif model.type == "router":
            self._add_router(model)
        elif model.type == "switch":
            self._add_switch(model)


    def _extend_mapping(self, mapping):
        assert isinstance(mapping, Mapping)

        self.mapping.expand(mapping)
        for model in self.models:
            self.models[model].expand(self.mapping)


    def _add_slice(self, slicem):
        sid = slicem.sid

        ns_list = []
        for ns in slicem.ns_list:
            vec = Vector(length=self.mapping.length)
            for field in ns:
                set_field_in_vector(
                    self.mapping,
                    vec,
                    field.name,
                    field_value_to_bitvector(field).vector
                )

            ns_list.append(vec)

        for ns in slicem.ns_diff:
            vec = Vector(length=self.mapping.length)
            for field in ns:
                set_field_in_vector(
                    self.mapping,
                    vec,
                    field.name,
                    field_value_to_bitvector(field).vector
                )

            ns_diff.append(vec)

        Aggregator.LOGGER.debug(
            "worker: add slice %s to netplumber with list %s and diff %s", sid, ns_list, ns_diff if ns_diff else None
        )
        jsonrpc.add_slice(self.sock, sid, ns_list, ns_diff if ns_diff else None)


    def _del_slice(self, sid):
        Aggregator.LOGGER.debug(
            "worker: remove slice %s from netplumber", sid
        )
        jsonrpc.remove_slice(self.sock, sid)


    def _add_packet_filter(self, model):
        Aggregator.LOGGER.debug("worker: apply packet filter: %s", model.node)

        self._add_tables(model, prefixed=True)
        self._add_wiring(model)
        self._add_rules(model)


    def _add_switch(self, model):
        Aggregator.LOGGER.debug("worker: apply switch: %s", model.node)
        self._add_tables(model)
        self._add_wiring(model)
        self._add_switch_rules(model)


    def _add_router(self, model):
        Aggregator.LOGGER.debug("worker: apply router: %s", model.node)
        self._add_tables(model, prefixed=True)
        self._add_wiring(model)
        self._add_rules(model)


    def _add_tables(self, model, prefixed=False):
        for table in model.tables:
            name = '_'.join([model.node, table])

            if name not in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for port in model.ports:
                    if prefixed and port.startswith("in_") and (
                            table.startswith("pre_routing")
                    ):
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port[3:]]))

                    elif prefixed and port.startswith("out_") and table.startswith("post_routing"):
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port[4:]]))

                    elif prefixed and not port.startswith(table):
                        continue

                    else:
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port]))

                    ports.append(portno)
                    self.ports[portname] = portno

                Aggregator.LOGGER.debug(
                    "worker: add table to netplumber: %s with index %s and ports %s",
                    name, idx, ports
                )
                jsonrpc.add_table(self.sock, idx, ports)


    def _add_wiring(self, model):
        # add links between tables
        for port1, port2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if port1 in ["internals_in", "post_routing"] or \
                port2 in ["internals_out", "post_routing"]:
                Aggregator.LOGGER.debug("worker: skip wiring %s to %s", port1, port2)
                continue

            Aggregator.LOGGER.debug("worker: wire %s to %s", port1, port2)

            gport1 = self._global_port('_'.join([model.node, port1]))

            if gport1 not in self.links:
                gport2 = self._global_port('_'.join([model.node, port2]))

                Aggregator.LOGGER.debug(
                    "worker: add link to netplumber from %s to %s", hex(gport1), hex(gport2)
                )
                jsonrpc.add_link(self.sock, gport1, gport2)

                self.links[gport1] = gport2


    # XXX: remove
    def _add_state_table(self, model, table):
        if table not in model.tables:
            return

        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        for rule in model.tables[table]:
            if not isinstance(rule, SwitchRule):
                rule = SwitchRule.from_json(rule)
            rid = rule.idx

            self._absorb_mapping(rule.mapping)

            rvec = Vector(length=self.mapping.length)
            for fld in rule.match:
                set_field_in_vector(
                    self.mapping,
                    rvec,
                    fld.name,
                    field_value_to_bitvector(fld).vector
                )

            ports = [] if rule.actions == [] else [
                self._global_port(
                    port
                ) for port in rule.actions[0].ports
            ]

            Aggregator.LOGGER.debug(
                "worker: add rule %s to %s:\n\t(%s -> %s)",
                rule.idx,
                self.tables["%s_%s" % (model.node, table)],
                rvec.vector if rvec else "*",
                ports
            )

            r_id = jsonrpc.add_rule(
                self.sock,
                self.tables["%s_%s" % (model.node, table)],
                rule.idx,
                [self._global_port(p) for p in rule.in_ports],
                ports,
                rvec.vector,
                None,
                None
            )
            if calc_rule_index(tid, rid) in self.rule_ids:
                self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
            else:
                self.rule_ids[calc_rule_index(tid, rid)] = [r_id]


    def _add_pre_routing_rules(self, model):
        table = 'pre_routing'

        if table not in model.tables:
            return

        tname = '_'.join([model.node, table])
        tid = self.tables[tname]


        port_len = len(self.models.get(model.node, model).ports)
        priv_len = self.models.get(model.node, model).private_ports
        in_ports_len = (port_len - priv_len) / 2

        for rule in model.tables[table]:
            if not isinstance(rule, SwitchRule):
                rule = SwitchRule.from_json(rule)
            rid = rule.idx

            Aggregator.LOGGER.debug("absorb mapping for pre routing")
            self._absorb_mapping(rule.mapping)

            rvec = Vector(length=self.mapping.length)
            for fld in rule.match:
                size = FIELD_SIZES[fld.name]
                set_field_in_vector(
                    self.mapping,
                    rvec,
                    fld.name,
                    field_value_to_bitvector(fld).vector
                )

            in_ports = [self._global_port(p) for p in rule.in_ports]

            out_ports = []
            for act in [a for a in rule.actions if isinstance(a, Forward)]:
                out_ports.extend([self._global_port(p) for p in act.ports])

            rewrite = None
            mask = None
            if "in_port" not in self.mapping:
                self.mapping.extend("in_port")
                rvec.enlarge(FIELD_SIZES["in_port"])

            rewrite = Vector(length=self.mapping.length)
            mask = Vector(length=rewrite.length, preset='0')

            for action in [a for a in rule.actions if isinstance(a, Rewrite)]:
                for field in action.rewrite:
                    fvec = '{:032b}'.format(
                        self._global_port(field.value)
                    ) if field.name in [
                        'in_port', 'out_port', 'interface'
                    ] else field_value_to_bitvector(field).vector

                    set_field_in_vector(
                        self.mapping, rewrite, field.name, fvec
                    )
                    set_field_in_vector(
                        self.mapping, mask, field.name, "1"*FIELD_SIZES[field.name]
                    )

            Aggregator.LOGGER.debug(
                "worker: add rule %s to %s:\n\t((%s) %s -> (%s) %s)",
                rid,
                self.tables["%s_%s" % (model.node, table)],
                (self._global_port(p) for p in rule.in_ports),
                rvec.vector if rvec else "*",
                rewrite.vector if rewrite else "*",
                out_ports
            )
            r_id = jsonrpc.add_rule(
                self.sock,
                self.tables["%s_%s" % (model.node, table)],
                rid,
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector,
                rewrite.vector
            )
            if calc_rule_index(tid, rid) in self.rule_ids:
                self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
            else:
                self.rule_ids[calc_rule_index(tid, rid)] = [r_id]


    def _add_post_routing_rules(self, model):
        table = 'post_routing'

        if table not in model.tables:
            return

        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        for rule in model.tables[table]:
            if not isinstance(rule, SwitchRule):
                rule = SwitchRule.from_json(rule)
            rid = rule.idx

            Aggregator.LOGGER.debug("absorb mapping for post routing")
            self._absorb_mapping(rule.mapping)

            rvec = Vector(length=self.mapping.length)
            for fld in rule.match:
                if fld.name in ['in_port', 'out_port', 'interface'] and not Vector.is_vector(fld.value, name=fld.name):
                    fld.value = self._global_port(fld.value)

                fvec = field_value_to_bitvector(fld)
                set_field_in_vector(
                    self.mapping,
                    rvec,
                    fld.name,
                    fvec.vector
                )

            rewrite = None
            mask = None

            if any([(p in self.mapping) for p in ['in_port', 'out_port']]):
                rewrite = Vector(length=rvec.length, preset="x")
                mask = Vector(length=rewrite.length, preset="0")

            for port in [p for p in ['in_port', 'out_port'] if p in self.mapping]:
                set_field_in_vector(
                    self.mapping, mask, port, '1'*FIELD_SIZES[port]
                )

            in_ports = [
                self._global_port("%s_%s" % (tname, p)) for p in rule.in_ports
            ]

            out_ports = []
            for act in [a for a in rule.actions if a.name == "forward"]:

                out_ports.extend([self._global_port(p) for p in act.ports])
                # XXX: ugly workaround
                if model.type == 'router':
                    for port in act.ports:
                        set_field_in_vector(
                            self.mapping,
                            rvec,
                            "out_port",
                            "{:032b}".format(self._global_port(port))
                        )

            Aggregator.LOGGER.debug(
                "worker: add rule %s to %s:\n\t(%s -> %s)",
                rule.idx, tid, rvec.vector if rvec else "*", out_ports
            )
            r_id = jsonrpc.add_rule(
                self.sock,
                tid,
                rule.idx,
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector if mask else None,
                rewrite.vector if rewrite else None
            )
            if calc_rule_index(tid, rid) in self.rule_ids:
                self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
            else:
                self.rule_ids[calc_rule_index(tid, rid)] = [r_id]


    def _add_rule_table(self, model, table):
        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        Aggregator.LOGGER.debug("worker: add rules to %s", tname)

        for rule in model.tables[table]:
            rid = rule.idx
            act = rule.actions

            for field in [f for f in rule.match if f.name in ['in_port', 'out_port', 'interface']]:
                if not Vector.is_vector(field.value, name=field.name):
                    field.value = "{:032b}".format(self._global_port("%s_%s" % (model.node, field.value)))
                    field.vectorize()

            for action in [a for a in act if isinstance(a, Rewrite)]:
                for field in action.rewrite:
                    if field.name in ['in_port', 'out_port', 'interface'] and not Vector.is_vector(field.value, name=field.name):
                        field.value = "{:032b}".format(self._global_port(field.value))

                    field.vectorize()

            rule.calc_vector(model.mapping)
            vec = rule.match.vector.vector
            rvec = Vector(length=self.mapping.length)
            for fld in model.mapping:
                copy_field_between_vectors(
                    model.mapping, self.mapping, vec, rvec, fld
                )

            in_ports = [
                self._global_port(
                    "%s_%s" % (tname, pname)
                ) for pname in rule.in_ports
            ]

            out_ports = []
            mask = None
            rewrite = None
            for action in rule.actions:
                if isinstance(action, Forward):
                    out_ports.extend(
                        [self._global_port(
                            '%s_%s' %(tname, port.lower())
                        ) for port in action.ports]
                    )

                elif isinstance(action, Miss):
                    out_ports.append(
                        self._global_port('%s_miss' % tname)
                    )

                elif isinstance(action, Rewrite):
                    if not rewrite:
                        rewrite = Vector(self.mapping.length)
                    if not mask:
                        mask = Vector(self.mapping.length, preset='0')
                    for field in action.rewrite:
                        set_field_in_vector(
                            self.mapping,
                            rewrite,
                            field.name,
                            (
                                field.value.vector
                            ) if isinstance(field.value, Vector) else (
                                field.vector.vector
                            )
                        )

                        set_field_in_vector(
                            self.mapping,
                            mask,
                            field.name,
                            '1'*FIELD_SIZES[field.name]
                        )

                else:
                    Aggregator.LOGGER.warn(
                        "worker: ignore unknown action while adding rule\n%s",
                        json.dumps(action.to_json(), indent=2)
                    )

            Aggregator.LOGGER.debug(
                "worker: add rule %s to %s:\n\t(%s, %s -> %s)",
                rid, tid, in_ports, rvec.vector if rvec else "*", out_ports
            )
            r_id = jsonrpc.add_rule(
                self.sock,
                tid,
                rid,
                in_ports,
                out_ports,
                rvec.vector if rvec.vector else 'x'*8,
                mask.vector if mask else None,
                rewrite.vector if rewrite else None
            )
            if calc_rule_index(tid, rid) in self.rule_ids:
                self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
            else:
                self.rule_ids[calc_rule_index(tid, rid)] = [r_id]


    def _add_rules(self, model):
        for table in model.tables:
            # XXX: ugly as f*ck... eliminate INPUT/OUTPUT and make PREROUTING static???
            if table in [
                    "pre_routing",
                    "post_routing"
            ]:
                Aggregator.LOGGER.debug("worker: skip adding rules to table %s", table)
                continue

            self._add_rule_table(model, table)

        for table in ["post_routing"]:
            self._add_post_routing_rules(model)

        for table in ["pre_routing"]:
            self._add_pre_routing_rules(model)


    # XXX: merge with pre- post-routing handling above?
    def _add_switch_rules(self, model):
        for table in model.tables:

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                rid = rule.idx

                Aggregator.LOGGER.debug("absorb mapping for switch rules")
                self._absorb_mapping(rule.mapping)

                rvec = Vector(length=self.mapping.length)
                for fld in rule.match:
                    set_field_in_vector(
                        self.mapping,
                        rvec,
                        fld.name,
                        field_value_to_bitvector(fld).vector
                    )

                out_ports = []
                mask = None
                rewrite = None
                for action in rule.actions:
                    if isinstance(action, Forward):
                        out_ports.extend(
                            [self._global_port(port) for port in action.ports]
                        )

                    elif isinstance(action, Rewrite):
                        rewrite = Vector(self.mapping.length)
                        mask = Vector(self.mapping.length, preset='0')
                        for field in action.rewrite:
                            if field.name in ['interface', 'in_port', 'out_port']:
                                set_field_in_vector(
                                    self.mapping,
                                    rewrite,
                                    field.name,
                                    '{:032b}'.format(self._global_port(field.value))
                                )

                            else:
                                set_field_in_vector(
                                    self.mapping,
                                    rewrite,
                                    field.name,
                                    field_value_to_bitvector(field).vector
                                )

                            set_field_in_vector(
                                self.mapping,
                                mask,
                                field.name,
                                '1'*FIELD_SIZES[field.name]
                            )

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s & %s -> %s, %s)",
                    rule.idx, tid, rvec.vector if rvec else "*", mask.vector if mask else "*", out_ports, rewrite.vector if rewrite else "*"
                )

                in_ports = []
                if rule.in_ports:
                    in_ports = [self._global_port(
                        "%s_%s" % (model.node, p)
                    ) for p in rule.in_ports]

                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    rule.idx,
                    in_ports,
                    out_ports,
                    rvec.vector,
                    mask.vector if mask else None,
                    rewrite.vector if rewrite else None
                )
                if calc_rule_index(tid, rid) in self.rule_ids:
                    self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(tid, rid)] = [r_id]


    def _delete_packet_filter(self, model):
        self._delete_rules(model)
        self._delete_wiring(model)
        self._delete_tables(model)


    def _delete_switch(self, model):
        self._delete_packet_filter(model)


    def _delete_router(self, model):
        self._delete_packet_filter(model)


    def _delete_rules(self, model):
        for table in model.tables:
            tid = self.tables['_'.join([model.node, table])]

            only_rid = lambda x: x[0]
            for rid in [only_rid(x) for x in model.tables[table]]:
                for r_id in self.rule_ids[calc_rule_index(tid, rid)]:
                    Aggregator.LOGGER.debug(
                        "worker: remove rule %s from netplumber", r_id
                    )
                    jsonrpc.remove_rule(self.sock, r_id)
                del self.rule_ids[calc_rule_index(tid, rid)]


    def _delete_wiring(self, model):
        prefix = lambda x: '.'.join(x.split('.')[:len(x.split('.'))-1])

        for port1, port2 in model.wiring:
            node1 = prefix(port1)
            node2 = prefix(port2)

            idx1 = self.tables[node1]
            idx2 = self.tables[node2]

            Aggregator.LOGGER.debug(
                "worker: remove link from %s to %s from netplumber", calc_port(idx1, model, port1), calc_port(idx2, model, port2)
            )
            jsonrpc.remove_link(
                self.sock,
                calc_port(idx1, model, port1),
                calc_port(idx2, model, port2)
            )


    def _delete_tables(self, model):
        for table in model.tables:
            name = '_'.join([model.node, table])

            if not self.models[model.node].tables[table]:
                Aggregator.LOGGER.debug(
                    "worker: remove table %s with id %s from netplumber", name, self.tables[name]
                )
                jsonrpc.remove_table(self.sock, self.tables[name])
                del self.tables[name]


    def _prepare_generator(self, model):
        name = model.node
        if name in self.generators:
            self._delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        outgoing = align_headerspace(
            model.mapping, self.mapping, model.outgoing
        )

        return (name, idx, portno, outgoing)


    def _add_generator(self, model):
        name, idx, portno, outgoing = self._prepare_generator(model)

        Aggregator.LOGGER.debug(
            "worker: add source %s and port %s to netplumber with list %s and diff %s", name, portno, [v.vector for v in outgoing.hs_list], [v.vector for v in outgoing.hs_diff]
        )
        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )

        self.generators[name] = (idx, sid, model)


    def _add_generators_bulk(self, models):
        generators = [self._prepare_generator(m) for m in models]

        for name, idx, portno, outgoing in generators:
            Aggregator.LOGGER.debug(
                "worker: add source %s and port %s to netplumber with list %s and diff %s", name, portno, [v.vector for v in outgoing.hs_list], [v.vector for v in outgoing.hs_diff]
            )

        sids = jsonrpc.add_sources_bulk(
            self.sock,
            [
                (
                    [v.vector for v in outgoing.hs_list],
                    [v.vector for v in outgoing.hs_diff],
                    [portno]
                ) for _name, _idx, portno, outgoing in generators
            ]
        )

        for name, model, sid in zip([n for n, _i, _p, _o in generators], models, sids):
            self.generators[name] = (idx, sid, model)


    def _delete_generator(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self._global_port(node+'.1')
        port2 = self.links[port1]
        Aggregator.LOGGER.debug(
            "worker: remove link from %s to %s from netplumber", port1, port2
        )
        jsonrpc.remove_link(self.sock, port1, port2)
        Aggregator.LOGGER.debug(
            "worker: remove link from %s to %s from netplumber", port2, port1
        )
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        Aggregator.LOGGER.debug(
            "worker: remove source %s with id %s from netplumber", node, sid
        )
        jsonrpc.remove_source(self.sock, sid)

        del self.tables[node]


    def _get_model_table(self, node):
        mtype = self.models[node].type
        return self.tables[
            node+'_post_routing' if mtype == 'packet_filter' else node+'.1'
        ]


    def _absorb_mapping(self, mapping):
        assert isinstance(mapping, Mapping)

        mlength = self.mapping.length
        self.mapping.expand(mapping)
        if mlength < self.mapping.length:
            Aggregator.LOGGER.debug(
                "worker: expand to length %s", self.mapping.length
            )
            jsonrpc.expand(self.sock, self.mapping.length)


    def _add_probe(self, model):
        name = model.node
        if name in self.probes:
            self._delete_probe(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        Aggregator.LOGGER.debug("absorb mapping for probe")
        self._absorb_mapping(model.mapping)

        filter_fields = align_headerspace(
            model.mapping, self.mapping, model.filter_fields
        )
        test_fields = align_headerspace(
            model.mapping, self.mapping, model.test_fields
        )

        if not filter_fields.hs_diff and len(filter_fields.hs_list) == 1:
            filter_hs = filter_fields.hs_list[0].vector
        else:
            filter_hs = {
                "hs_list" : [
                    v.vector for v in filter_fields.hs_list
                ] if filter_fields.hs_list else ["x"*self.mapping.length],
                "hs_diff" : [
                    v.vector for v in filter_fields.hs_diff
                ] if filter_fields.hs_diff else None
            }

        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
#        filter_expr = {"type" : "header", "header" : filter_hs}
        filter_expr = None

        test_path = []
        for pathlet in model.test_path.to_json()['pathlets']:
            ptype = pathlet['type']

            if ptype not in ['start', 'end', 'skip', 'skip_next']:
                key, val = {
                    'port' : ('port', lambda pl: self._global_port(pl['port'])),
                    'next_ports' : (
                        'ports',
                        lambda pl: [self._global_port(p) for p in pl['ports']]
                    ),
                    'last_ports' : (
                        'ports',
                        lambda pl: [self._global_port(p) for p in pl['ports']]
                    ),
                    'table' : ('table', lambda pl: self._get_model_table(pl['table'])),
                    'next_tables' : (
                        'tables',
                        lambda pl: [self._get_model_table(t) for t in pl['tables']]
                    ),
                    'last_tables' : (
                        'tables',
                        lambda pl: [self._get_model_table(t) for t in pl['tables']]
                    )
                }[ptype]
                pathlet[key] = val(pathlet)

            test_path.append(pathlet)

        if test_fields and not test_fields.hs_diff and len(test_fields.hs_list) == 1:
            test_hs = test_fields.hs_list[0].vector
        else:
            test_hs = {
                "hs_list" : [
                    v.vector for v in test_fields.hs_list
                ] if test_fields.hs_list else ["x"*self.mapping.length],
                "hs_diff" : [
                    v.vector for v in test_fields.hs_diff
                ] if test_fields.hs_diff else None
            }

        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
        if test_fields and test_path:
            test_expr = {
#                "type": "and",
#                "arg1" : {
#                    "type" : "header",
#                    "header" : test_hs
#                },
#                "arg2" : {
                    "type" : "path",
                    "pathlets" : test_path
#                }
            }

        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
        elif test_fields:
            test_expr = {
                "type" : "true"
#                "type" : "header",
#                "header" : test_hs
            }

        elif test_path:
            test_expr = {
                "type" : "path",
                "pathlets" : test_path
            }

        else:
            eprint("Error while add probe: no test fields or path. Aborting.")
            return

        Aggregator.LOGGER.debug(
            "worker: add probe %s and port %s", name, portno
        )
        pid = jsonrpc.add_source_probe(
            self.sock,
            [portno],
            model.quantor,
            filter_expr,
            test_expr
        )
        self.probes[name] = (idx, pid, model)


    def _delete_probe(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.probes[node])

        # delete links
        port1 = self._global_port(node+'.1')
        port2 = self.links[port1]
        Aggregator.LOGGER.debug(
            "worker: remove link from %s to %s from netplumber", port1, port2
        )
        jsonrpc.remove_link(self.sock, port1, port2)
        Aggregator.LOGGER.debug(
            "worker: remove link from %s to %s from netplumber", port2, port1
        )
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        Aggregator.LOGGER.debug(
            "worker: remove probe %s from netplumber", sid
        )
        jsonrpc.remove_source_probe(self.sock, sid)

        del self.tables[node]


    def _global_port(self, port):
        return self.ports[normalize_port(port)]


    def _dump_aggregator(self, odir):
        os.system("mkdir -p %s" % odir)
        os.system("rm -f %s/*" % odir)

        with open("%s/fave.json" % odir, "w") as ofile:
            j = {}
            j["mapping"] = self.mapping.to_json()
            j["id_to_table"] = {self.tables[k]:k for k in self.tables}

            j["id_to_rule"] = {}
            for key in self.rule_ids:
                for elem in self.rule_ids[key]:
                    j["id_to_rule"][elem] = key >> 16

            j["id_to_generator"] = {
                self.generators[k][1]:k for k in self.generators
            }
            j["id_to_probe"] = {self.probes[k][1]:k for k in self.probes}
            j["id_to_port"] = {self.ports[k]:k for k in self.ports}

            ofile.write(
                json.dumps(j, sort_keys=True, indent=4, separators=(',', ': '))
            )


def main(argv):
    """ Connects to net_plumber backend and starts aggregator.
    """

    server = "127.0.0.1"
    port = 0

    try:
        only_opts = lambda x: x[0]
        opts = only_opts(
            getopt.getopt(argv, "hs:p:", ["help", "server=", "port="])
        )
    except getopt.GetoptError:
        _print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-s' and (is_ip(arg) or is_domain(arg) or is_unix(arg)):
            server = arg
        elif opt == '-p':
            port = int(arg) if is_port(arg) else port

    log_handler = logging.FileHandler('/tmp/np/aggregator.log')
    Aggregator.LOGGER.addHandler(log_handler)
    Aggregator.LOGGER.setLevel(logging.DEBUG)

    try:
        sock = jsonrpc.connect_to_netplumber(server, port)
    except jsonrpc.RPCError as err:
        Aggregator.LOGGER.error(err.message)
        _print_help()
        sys.exit(1)

    global AGGREGATOR
    AGGREGATOR = Aggregator(sock)

    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    register_signals()

    AGGREGATOR.run()


if __name__ == "__main__":
    #cProfile.run('main(%s)' % sys.argv[1:], "aggregator.profile")
    main(sys.argv[1:])
