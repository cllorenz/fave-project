#!/usr/bin/env python2

import cProfile
import signal
import re
import socket
import os
import json
import logging
import sys
import getopt

from threading import Thread
from Queue import Queue
from copy import deepcopy as dc

#import daemon

from util.print_util import eprint
from util.aggregator_utils import UDS_ADDR

import netplumber.jsonrpc as jsonrpc
from netplumber.model import Model
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import copy_field_between_vectors, Vector, HeaderSpace

from ip6np.packet_filter import PacketFilterModel
from ip6np.generator import field_value_to_bitvector

from openflow.switch import SwitchModel, SwitchCommand, SwitchRule

from topology.topology import TopologyCommand, LinksModel
from topology.host import HostModel
from topology.generator import GeneratorModel
from topology.probe import ProbeModel


_AGGREGATOR = None

profile = cProfile.Profile()

def profile_method(method):
    def profile_wrapper(*args, **kwargs):
        profile.enable()
        method(*args, **kwargs)
        profile.disable()
    return profile_wrapper

def dump_stats():
    profile.dump_stats("aggregator.stats")

def handle_sigterm(signum, frame):
    if _AGGREGATOR:
        _AGGREGATOR.stop_aggr()

handle_sigint = handle_sigterm

def print_help():
    eprint(
        "aggregator -s <server> -p <port>",
        "\t-s <server> ip address of the instance",
        "\t-p <port> the port number of the netplumber instance",
        sep="\n"
    )


def is_ip(s):
    ary = s.split(".")
    if len(ary) != 4:
        return False
    try:
        for x in ary:
            i = int(x)
            if 0 > i or i > 255:
                return False
    except:
        return False

    return True


def is_domain(s):
    labels = s.split(".")
    label = re.compile("^[a-zA-Z](([-a-zA-Z0-9]+)?[a-zA-Z0-9])?$") # cf. RFC1025
    return all([re.match(label, l) for l in labels])


def is_unix(s):
    return not '\0' in s


def is_port(s):
    try:
        p = int(s)
        if 0 > p or p > 0xffff:
            return False
    except ValueError:
        return False

    return True

is_ext_port = is_port

# XXX: returns None when profiled... WTF!?
#@profile_method
def model_from_string(s):
    model_from_json(json.loads(s))


def model_from_json(j):
    Aggregator.LOGGER.debug('reconstruct model')
    try:
        models = {
            "model" : Model,
            "packet_filter" : PacketFilterModel,
            "switch" : SwitchModel,
            "switch_command" : SwitchCommand,
            #"topology" : TopologyModel,
            "topology_command" : TopologyCommand,
            "links" : LinksModel,
            "host" : HostModel,
            "generator" : GeneratorModel,
            "probe" : ProbeModel
        }
        model = models[j["type"]]

    except KeyError:
        Aggregator.LOGGER.error("model type not implemented: %s" % j["type"])
        raise Exception("model type not implemented: %s" % j["type"])

    else:
        return model.from_json(j)


def calc_port(tab, model, port):
    try:
        return (tab<<16)+model.ports[port]
    except KeyError:
        return (tab<<16)+1


def calc_rule_index(t_idx, r_idx):
    return (t_idx<<16)+r_idx


def has_dot_but_is_not_post_int_port(port):
    labels = port.rsplit('.')
    if len(labels) != 2:
        return False
    try:
        int(labels[1])
        return False
    except ValueError:
        return True

def normalize_port(port):
    return port.replace('.', '_')

    if port.count('.') > 1:
        labels = port.split('.')
        l = len(labels)
        return '.'.join(labels[:l-1])+'_'+labels[l-1]
    elif has_dot_but_is_not_post_int_port(port):
        return port
    else:
        return port.replace('.', '_')

"""
class ProfiledThread(Thread):
    def run(self):
        print "run thread"
        profiler = cProfile.Profile()
        try:
            return profiler.runcall(Thread.run, self)
            #profiler.print_stats()
        finally:
            print "dump profile"
            profiler.dump_stats('aggr_handler.profile')
"""

class Aggregator(object):
    BUF_SIZE = 4096
    LOGGER = logging.getLogger('Aggregator')

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
        print >> sys.stderr, "Aggregator:"
        print >> sys.stderr, self.mapping
        print >> sys.stderr, "tables:"
        print >> sys.stderr, "\t", self.tables
        print >> sys.stderr, "ports:"
        print >> sys.stderr, "\t", self.ports
        print >> sys.stderr, "rule ids:"
        print >> sys.stderr, "\t", self.rule_ids
        print >> sys.stderr, "links:"
        print >> sys.stderr, "\t", self.links
        print >> sys.stderr, "generators:"
        print >> sys.stderr, "\t", self.generators
        print >> sys.stderr, "probes:"
        print >> sys.stderr, "\t", self.probes

    #@profile_method
    def _handler(self):
        while not self.stop:
            data = self.queue.get()
            Aggregator.LOGGER.debug('worker: fetched data from queue')

            if not data:
                Aggregator.LOGGER.debug('worker: ignoring empty data')
                self.queue.task_done()
                continue

            try:
                j = json.loads(data)
            except Exception as err:
                Aggregator.LOGGER.exception('worker: could not parse data:')
                self.queue.task_done()
                return

            if j['type'] == 'stop':
                self.stop_aggr()
                jsonrpc.stop(self.sock)

            elif j['type'] == 'dump':
                dump = j
                odir = dump['dir']

                if dump['fave']:
                    self._dump_aggregator(odir)
                if dump['flows']:
                    jsonrpc.dump_flows(self.sock, odir)
                if dump['network']:
                    jsonrpc.dump_plumbing_network(self.sock, odir)
                if dump['pipes']:
                    jsonrpc.dump_pipes(self.sock, odir)

            else:
                model = model_from_json(j)
                self._sync_diff(model)

            self.queue.task_done()

    def run(self):
        # open new unix domain socket
        Aggregator.LOGGER.info("open and bind uds socket")
        uds = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        uds.settimeout(1.0)
        uds.bind(UDS_ADDR)

        # start thread to handle incoming config events
        Aggregator.LOGGER.info("start handler thread")
        t = Thread(target=self._handler)
        t.daemon = True
        t.start()

        Aggregator.LOGGER.info("listen on socket")
        uds.listen(1)

        while not self.stop:
            # accept connections on unix domain socket
            Aggregator.LOGGER.debug("master: wait for connection")
            try:
                conn, addr = uds.accept()
            except socket.timeout:
                Aggregator.LOGGER.debug("master: listening timed out, continue loop...")
                continue
            except socket.error:
                Aggregator.LOGGER.debug("master: break listening loop due to socket error")
                Aggregator.LOGGER.exception("master: error from accept():")
                break

            Aggregator.LOGGER.debug("master: accepted connection")

            # receive data from unix domain socket
            #nbytes = Aggregator.BUF_SIZE
            #data = ""
            #while nbytes == Aggregator.BUF_SIZE:
            #    tmp = conn.recv(Aggregator.BUF_SIZE)
            #    nbytes = len(tmp)
            #    data += tmp
            #if not data:
            #    break

            data = ""
            while True:
                part = conn.recv(Aggregator.BUF_SIZE)
                data += part
                if len(part) < Aggregator.BUF_SIZE:
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

        #jsonrpc.dump_stats()
        #dump_stats()

        # join thread
        Aggregator.LOGGER.info("master: join handler thread")
        t.join()

        Aggregator.LOGGER.info("master: finished run")


    def stop_aggr(self):
        Aggregator.LOGGER.info("initiate stopping")
        self.stop = True


    #@profile_method
    def _sync_diff(self, model):
        Aggregator.LOGGER.debug('worker: synchronize model')

        # extend global mapping
        mlength = self.mapping.length

        if model.type == "packet_filter":
            self.mapping.expand(model.mapping)
            #self._extend_mapping(model.mapping)
        elif model.type == "switch_command" and model.command == "add_rule":
            self.mapping.expand(model.rule.mapping)
            #self._extend_mapping(model.rule.mapping)
        elif model.type == "topology_command" and \
                model.command == 'add' and \
                model.model.type in ['probe', 'host', 'generator']:

            self.mapping.expand(model.model.mapping)
            #self._extend_mapping(model.model.mapping)

        if mlength < self.mapping.length:
            jsonrpc.expand(self.sock, self.mapping.length) # XXX: +1 necessary?

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
                #ports = self.query_ports(model.node)
                #test_command = lambda x: x in ["add_rule", "update_rule"]
                #rules = [model.rule] if test_command(model.command) else []
                #model = SwitchModel(model.node, ports=ports, rules=rules)

        # handle topology changes (e.g. by the network management)
        if model.type == "topology_command":
            cmd = model

            if cmd.mtype == "links":
                for link in cmd.model:
                    sport, dport = link
                    sport = self._global_port(sport)
                    dport = self._global_port(dport)

                    if cmd.command == "add":
                        jsonrpc.add_link(self.sock, sport, dport)
                        self.links[sport] = dport
                    elif cmd.command == "del":
                        jsonrpc.remove_link(self.sock, sport, dport)
                        del self.links[sport]

            elif cmd.mtype == "packet_filter":
                if cmd.command == "add":
                    self._add_packet_filter(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self.delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "switch":
                if cmd.command == "add":
                    self._add_switch(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self.delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "host":
                if cmd.command == "add":
                    self._add_host(cmd.model)
                elif cmd.command == "del":
                    self._delete_host(cmd.node)

            elif cmd.mtype == "generator":
                if cmd.command == "add":
                    self._add_generator(cmd.model)
                elif cmd.command == "del":
                    self._delete_generator(cmd.node)

            elif cmd.mtype == "probe":
                if cmd.command == "add":
                    self._add_probe(cmd.model)
                elif cmd.command == "del":
                    self._delete_probe(cmd.node)

            return

        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            sub = self.models[model.node] - model

# TODO: fix deletion... needs exclusion of pre-, post-routing, state tables
#            print sub

            # remove unecessary items
#            self._delete_model(sub)

            # add new items
            self._add_model(add)

        else:
            self.models[model.node] = model

            # add model completely
            self._add_model(model)


    def _delete_model(self, model):
        if model.type == "packet_filter":
            self._delete_packet_filter(model)
        elif model.type == "switch":
            self.delete_switch(model)

    def _add_model(self, model):
        if model.type == "packet_filter":
            self._add_packet_filter(model)
        elif model.type == "switch":
            self._add_switch(model)

    # XXX: deprecated?
    def _extend_mapping(self, m):
        assert isinstance(m, Mapping)
        for f in m:
            if not f in self.mapping:
                self.mapping.extend(f)


    def _add_packet_filter(self, model):
        Aggregator.LOGGER.debug("worker: apply packet filter: %s" % model.node)

        self._add_tables(model, prefixed=True)
        self._add_wiring(model)
        self._add_rules(model)


    def _add_switch(self, model):
        Aggregator.LOGGER.debug("worker: apply switch: %s" % model.node)
        self._add_tables(model)
        self._add_wiring(model)
        self._add_switch_rules(model)


    def _add_tables(self, model, prefixed=False):
        ext_ports = []
        for t in model.tables:
            name = '_'.join([model.node, t])

            if not name in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for p in model.ports:
                    if prefixed and p.startswith("in_") and t.startswith("pre_routing"):
                        portno = calc_port(idx, model, p)
                        portname = normalize_port('.'.join([model.node, p[3:]]))

                    elif prefixed and p.startswith("out_") and t.startswith("post_routing"):
                        portno = calc_port(idx, model, p)
                        portname = normalize_port('.'.join([model.node, p[4:]]))

                    elif prefixed and not p.startswith(t):
                        continue

                    else:
                        portno = calc_port(idx, model, p)
                        portname = normalize_port('.'.join([model.node, p]))

                    ports.append(portno)
                    self.ports[portname] = portno

                Aggregator.LOGGER.debug(
                    "worker: add table to netplumber: %s with index %s and ports %s" %
                    (name, idx, ports)
                )
                jsonrpc.add_table(self.sock, idx, ports)


    def _add_wiring(self, model):
        # add links between tables
        for p1, p2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if p1 in ["internals_in", "post_routing"] or \
                p2 in ["internals_out", "post_routing"]:
                Aggregator.LOGGER.debug("worker: skip wiring %s to %s" % (p1, p2))
                continue

            Aggregator.LOGGER.debug("worker: wire %s to %s" % (p1, p2))

            gp1 = self._global_port('_'.join([model.node, p1]))

            if not gp1 in self.links:
                gp2 = self._global_port('_'.join([model.node, p2]))

                Aggregator.LOGGER.debug(
                    "worker: add link to netplumber from %s to %s" % (gp1, gp2)
                )
                jsonrpc.add_link(self.sock, gp1, gp2)

                self.links[gp1] = gp2


    def _add_rules(self, model):
        for t in model.tables:
            # XXX: ugly as f*ck... eliminate INPUT/OUTPUT and make PREROUTING static???
            if t in [
                    "pre_routing",
                    "post_routing",
                    "input_states",
                    "output_states",
                    "forward_states"
            ]:
                Aggregator.LOGGER.debug("worker: skip adding rules to table %s" % t)
                continue

            tn = '_'.join([model.node, t])
            ti = self.tables[tn]

            Aggregator.LOGGER.debug("worker: add rules to %s" % tn)

            for ri, v, a in model.tables[t]:
                rv = Vector(length=self.mapping.length)
                for f in model.mapping:
                    g_offset = self.mapping[f]
                    m_offset = model.mapping[f]
                    size = FIELD_SIZES[f]
                    rv[g_offset:g_offset+size] = v[m_offset:m_offset+size]

                ports = [self._global_port(
                    '_'.join([model.node, t, a.lower()])
                )] if a in ['ACCEPT', 'MISS'] else []

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)" %
                    (ri, ti, rv.vector if rv else "*", ports)
                )
                r_id = jsonrpc.add_rule(
                    self.sock,
                    ti,
                    ri,
                    [],
                    ports,
                    rv.vector if rv.vector else 'x'*8,
                    None,
                    None
                )
                if calc_rule_index(ti, ri) in self.rule_ids:
                    self.rule_ids[calc_rule_index(ti, ri)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(ti, ri)] = [r_id]

        for table in ["post_routing"]:
            if not table in model.tables:
                continue

            tn = '_'.join([model.node, table])
            ti = self.tables[tn]

            for r in model.tables[table]:
                if isinstance(r, SwitchRule):
                    rule = r
                else:
                    rule = SwitchRule.from_json(r)
                ri = rule.idx

                self._absorb_mapping(rule.mapping)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = FIELD_SIZES[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                rw = None
                if 'interface' in self.mapping:
                    rw = dc(rv)
                    offset = self.mapping["interface"]
                    size = FIELD_SIZES["interface"]
                    rw[offset:offset+size] = "x"*size

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([self._global_port(p) for p in a.ports])

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)" %
                    (rule.idx, ti, rv.vector if rv else "*", ports)
                )
                r_id = jsonrpc.add_rule(
                    self.sock,
                    ti,
                    rule.idx,
                    [],
                    ports,
                    rv.vector,
                    None,
                    rw.vector if rw else None
                )
                if calc_rule_index(ti, ri) in self.rule_ids:
                    self.rule_ids[calc_rule_index(ti, ri)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(ti, ri)] = [r_id]

        for table in ["pre_routing"]:
            if not table in model.tables:
                continue

            tn = '_'.join([model.node, table])
            ti = self.tables[tn]

            for r in model.tables[table]:
                if isinstance(r, SwitchRule):
                    rule = r
                else:
                    rule = SwitchRule.from_json(r)
                ri = rule.idx

                self._absorb_mapping(rule.mapping)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = FIELD_SIZES[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([self._global_port(p) for p in a.ports])

                rw = None
                if not "interface" in self.mapping:
                    self.mapping.extend("interface")
                    rv.enlarge(FIELD_SIZES["interface"])

                rw = dc(rv)
                offset = self.mapping["interface"]
                size = FIELD_SIZES["interface"]

                for port in range(1, 1+(len(self.models[model.node].ports)-19)/2):
                    rw[offset:offset+size] = '{:016b}'.format(port)

                    Aggregator.LOGGER.debug(
                        "worker: add rule %s to %s:\n\t((%s) %s -> (%s) %s)" %
                        (
                            rule.idx,
                            self.tables["%s_%s" % (model.node, table)],
                            self._global_port("%s_%s" % (model.node, str(port))),
                            rv.vector if rv else "*",
                            rw.vector if rw else "*",
                            ports
                        )
                    )
                    r_id = jsonrpc.add_rule(
                        self.sock,
                        self.tables["%s_%s" % (model.node, table)],
                        rule.idx,
                        [self._global_port("%s_%s" % (model.node, str(port)))],
                        ports,
                        rv.vector,
                        None,
                        rw.vector
                    )
                    if calc_rule_index(ti, ri) in self.rule_ids:
                        self.rule_ids[calc_rule_index(ti, ri)].append(r_id)
                    else:
                        self.rule_ids[calc_rule_index(ti, ri)] = [r_id]

        for table in ["input_states", "output_states", "forward_states"]:
            if not table in model.tables:
                continue

            tn = '_'.join([model.node, table])
            ti = self.tables[tn]

            for r in model.tables[table]:
                if isinstance(r, SwitchRule):
                    rule = r
                else:
                    rule = SwitchRule.from_json(r)
                ri = rule.idx

                self._absorb_mapping(rule.mapping)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = FIELD_SIZES[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                port = self._global_port(
                    "%s_%s" % (tn, 'miss' if ri == 65535 else 'accept')
                )

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)" %
                    (
                        rule.idx,
                        self.tables["%s_%s" % (model.node, table)],
                        rv.vector if rv else "*",
                        port
                    )
                )

                r_id = jsonrpc.add_rule(
                    self.sock,
                    self.tables["%s_%s" % (model.node, table)],
                    rule.idx,
                    [],
                    [port],
                    rv.vector,
                    None,
                    None
                )
                if calc_rule_index(ti, ri) in self.rule_ids:
                    self.rule_ids[calc_rule_index(ti, ri)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(ti, ri)] = [r_id]

    # XXX: merge with pre- post-routing handling above?
    def _add_switch_rules(self, model):
        for table in model.tables:

            tn = '_'.join([model.node, table])
            ti = self.tables[tn]

            for rule in model.tables[table]:
                ri = rule.idx

                self._absorb_mapping(rule.mapping)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = FIELD_SIZES[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([
                        self._global_port(p) for p in a.ports
                    ])

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)" %
                    (rule.idx, ti, rv.vector if rv else "*", ports)
                )

                r_id = jsonrpc.add_rule(
                    self.sock,
                    ti,
                    rule.idx,
                    [],
                    ports,
                    rv.vector,
                    None,
                    None
                )
                if calc_rule_index(ti, ri) in self.rule_ids:
                    self.rule_ids[calc_rule_index(ti, ri)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(ti, ri)] = [r_id]

    def _delete_packet_filter(self, model):
        self._delete_rules(model)
        self._delete_wiring(model)
        self._delete_tables(model)

    delete_switch = _delete_packet_filter

    #def delete_switch(self, model):
    #    self._delete_rules(model)
    #    self._delete_wiring(model)
    #    self._delete_tables(model)


    def _delete_rules(self, model):
        for t in model.tables:
            ti = self.tables['_'.join([model.node, t])]

            for ri, v, a in model.tables[t]:
                for r_id in self.rule_ids[calc_rule_index(ti, ri)]:
                    jsonrpc.remove_rule(r_id)
                del self.rule_ids[calc_rule_index(ti, ri)]

    def delete_wiring(self, model):
        for p1, p2 in model.wiring:
            n1 = prefix(p1)
            n2 = prefix(p2)

            i1 = self.tables[n1]
            i2 = self.tables[n2]

            jsonrpc.remove_link(calc_port(i1, model, p1), calc_port(i2, model, p2))

    def _delete_tables(self, model):
        for t in model.tables:
            name = '_'.join([model.node, t])

            if not self.models[model.node].tables[t]:
                jsonrpc.remove_table(self.sock, self.tables[name])
                del self.tables[name]




    def _add_host(self, model):
        name = model.node
        if name in self.tables:
            self._delete_host(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        outgoing = self._aligned_headerspace(model.outgoing, model.mapping)

        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )

        #incoming = self._aligned_headerspace(model.incoming, model.mapping)
        #pid = jsonrpc.add_source_probe(
        #    self.sock,
        #    [portno],
        #    'universal',
        #    {
        #        "type" : "header",
        #        "hs_list" : [v.vector for v in incoming.hs_list],
        #        "hs_diff" : [v.vector for v in incoming.hs_diff]
        #    },
        #    None
        #)
        self.generators[name] = (idx, sid, model)


    def _delete_host(self, node):
        idx, sid, model = self.generators[node]

        # delete links
        p1 = self._global_ports(node+'.1')
        p2 = self.links[p1]
        jsonrpc.remove_link(self.sock, p1, p2)
        jsonrpc.remove_link(self.sock, p2, p1)

        del self.links[p1]
        del self.links[p2]

        # delete source and probe
        jsonrpc.remove_source(sid)
        #jsonrpc.remove_source_probe(pid)

        del self.tables[node]


    def _add_generator(self, model):
        name = model.node
        if name in self.generators:
            self._delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        outgoing = self._aligned_headerspace(model.outgoing, model.mapping)

        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )
        self.generators[name] = (idx, sid, model)


    def _delete_generator(self, node):
        idx, sid, model = self.generators[node]

        # delete links
        p1 = self._global_port(node+'.1')
        p2 = self.links[p1]
        jsonrpc.remove_link(self.node, p1, p2)
        jsonrpc.remove_link(self.node, p2, p1)

        del self.links[p1]
        del self.links[p2]

        # delete source and probe
        jsonrpc.remove_source(sid)

        del self.tables[node]


    def _get_model_table(self, node):
        mtype = self.models[node].type
        if mtype == 'packet_filter':
            return self.tables[node+'_post_routing']
        else:
            return self.tables[node+'.1']

    def _absorb_mapping(self, mapping):
        mlength = self.mapping.length
        self.mapping.expand(mapping)
        if mlength < self.mapping.length:
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

        self._absorb_mapping(model.mapping)

        filter_fields = self._aligned_headerspace(model.filter_fields, model.mapping)
        test_fields = self._aligned_headerspace(model.test_fields, model.mapping)

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

        filter_expr = { "type" : "header", "header" : filter_hs }

        test_path = []
        for pathlet in model.test_path.to_json()['pathlets']:
            ptype = pathlet['type']
            if ptype in ['start','end','skip']:
                test_path.append(pathlet)
            elif ptype == 'port':
                pathlet['port'] = self.global_port(pathlet['port'])
                test_path.append(pathlet)
            elif ptype == 'next_ports':
                pathlet['ports'] = [self.global_port(port) for port in pathlet['ports']]
                test_path.append(pathlet)
            elif ptype == 'last_ports':
                pathlet['ports'] = [self.global_port(port) for port in pathlet['ports']]
                test_path.append(pathlet)
            elif ptype == 'table':
                pathlet['table'] = self.get_model_table(pathlet['table'])
                test_path.append(pathlet)
            elif ptype == 'next_table':
                pathlet['tables'] = [self.get_model_table(table) for table in pathlet['tables']]
                test_path.append(pathlet)
            elif ptype == 'last_table':
                pathlet['tables'] = [self.get_model_table(table) for table in pathlet['tables']]
                test_path.append(pathlet)


        if test_fields and test_path:
            if not test_fields.hs_diff and len(test_fields.hs_list) == 1:
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

            test_expr = {
                "type": "and",
                "arg1" : {
                    "type" : "header",
                    "header" : test_hs
                },
                "arg2" : {
                    "type" : "path",
                    "pathlets" : test_path
                }
            }

        elif test_fields:
            if not test_fields.hs_diff and len(test_fields.hs_list) == 1:
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

            test_expr = {
                "type" : "header",
                "header" : test_hs
            }

        elif test_path:
            test_expr = {
                "type" : "path",
                "pathlets" : test_path
            }

        else:
            eprint("Error while add probe: no test fields or path. Aborting.")
            return

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
        jsonrpc.remove_link(self.sock, port1, port2)
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        jsonrpc.remove_source_probe(self.sock, sid)

        del self.tables[node]



    def _aligned_headerspace(self, hspace, mapping):
        hs_list = []
        for vector in hspace.hs_list:
            hs_list.append(self._aligned_vector(vector, mapping))

        hs_diff = []
        for vector in hspace.hs_diff:
            hs_diff.append(self._aligned_vector(vector, mapping))

        return HeaderSpace(self.mapping.length, hs_list, hs_diff)


    def _aligned_vector(self, vector, mapping):
        vec = Vector(self.mapping.length)
        for fld in mapping:
            copy_field_between_vectors(mapping, self.mapping, vector, vec, fld)

        return vec


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
                self.generators[k][0]:k for k in self.generators
            }
            j["id_to_probe"] = {self.probes[k][0]:k for k in self.probes}
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
        print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-s' and (is_ip(arg) or is_domain(arg) or is_unix(arg)):
            server = arg
        elif opt == '-p':
            port = int(arg) if is_port(arg) else port

    backend = server if port == 0 else (server, port)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) if port == 0 else \
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if not sock:
        print_help()
        sys.exit(1)

    sock.connect(backend)

    global _AGGREGATOR
    _AGGREGATOR = Aggregator(sock)

    log_handler = logging.FileHandler('/tmp/np/aggregator.log')
    Aggregator.LOGGER.addHandler(log_handler)
    Aggregator.LOGGER.setLevel(logging.DEBUG)

    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)

    _AGGREGATOR.run()


if __name__ == "__main__":
    #cProfile.run('main(%s)' % sys.argv[1:], "aggregator.profile")
    main(sys.argv[1:])
