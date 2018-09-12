#!/usr/bin/env python2

""" This module provides FaVe's central aggregation service.
"""

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

PROFILE = cProfile.Profile()


def profile_method(method):
    """ Wraps a profiler around a method.

    Keyword arguments:
    method -- a method to be profiled
    """
    def profile_wrapper(*args, **kwargs):
        """ Collects profiling information while executing a method.
        """
        PROFILE.enable()
        method(*args, **kwargs)
        PROFILE.disable()
    return profile_wrapper


def dump_stats():
    """ Dumps collected profiling stats to the file \"./aggregator.stats\".
    """
    PROFILE.dump_stats("aggregator.stats")


def handle_sigterm(signum, frame):
    """ Handler for SIGTERM signals.
    """
    if _AGGREGATOR:
        _AGGREGATOR.stop_aggr()


def handle_sigint(signum, frame):
    """ Handler for SIGINT signals.
    """
    handle_sigterm(signum, frame)


def print_help():
    """ Prints a usage message to stderr.
    """
    eprint(
        "aggregator -s <server> -p <port>",
        "\t-s <server> ip address of the instance",
        "\t-p <port> the port number of the netplumber instance",
        sep="\n"
    )


def is_ip(ips):
    """ Checks if a string represents a valid IPv4 address.

    Keyword arguments:
    ips -- a string
    """
    elems = ips.split(".")
    if len(elems) != 4:
        return False
    try:
        for elem in elems:
            i = int(elem)
            if i < 0 or i > 255:
                return False
    except ValueError:
        return False

    return True


def is_domain(domains):
    """ Checks if a string is a valid domain name.

    Keyword arguments:
    domains -- a string
    """
    labels = domains.split(".")
    label = re.compile("^[a-zA-Z](([-a-zA-Z0-9]+)?[a-zA-Z0-9])?$") # cf. RFC1025
    return all([re.match(label, l) for l in labels])


def is_unix(unixs):
    """ Checks if a string is a valid unix domain socket address.

    Keyword arguments:
    unixs -- a string
    """
    return '\0' not in unixs


def is_port(ports):
    """ Checks if a string is a valid port number.

    Keyword arguments:
    ports -- a string
    """
    try:
        port = int(ports)
        return port >= 0 and port <= 0xffff
    except ValueError:
        return False

    return False


def is_ext_port(ports):
    """ Checks if a string is a valid interface number.

    Keyword arguments:
    ports -- a string
    """
    return is_port(ports)


# XXX: returns None when profiled... WTF!?
#@profile_method
def model_from_string(jsons):
    """ Reconstructs a model from a JSON string.

    Keyword arguments:
    jsons -- a json string
    """
    model_from_json(json.loads(jsons))


def model_from_json(j):
    """ Reconstructs a model from a JSON object.

    Keyword arguments:
    j -- a JSON object
    """

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
        Aggregator.LOGGER.error("model type not implemented: %s", j["type"])
        raise Exception("model type not implemented: %s" % j["type"])

    else:
        return model.from_json(j)


def calc_port(tab, model, port):
    """ Calculates a port number for a table.

    Keyword arguments:
    tab -- a table id
    model -- the model inheriting the table
    port -- the port index in the table
    """
    try:
        return (tab<<16)+model.ports[port]
    except KeyError:
        return (tab<<16)+1


def calc_rule_index(t_idx, r_idx):
    """ Calculates the rule index within a table

    Keyword arguments:
    t_idx -- a table index
    r_idx -- a rule index within the table
    """
    return (t_idx<<16)+r_idx


#def has_dot_but_is_not_post_int_port(port):
#    labels = port.rsplit('.')
#    if len(labels) != 2:
#        return False
#    try:
#        int(labels[1])
#        return False
#    except ValueError:
#        return True


def normalize_port(port):
    """ Normalizes a port's name

    Keyword arguments:
    port -- a port name
    """
    return port.replace('.', '_')

    #if port.count('.') > 1:
    #    labels = port.split('.')
    #    length = len(labels)
    #    return '.'.join(labels[:length-1])+'_'+labels[length-1]
    #elif has_dot_but_is_not_post_int_port(port):
    #    return port
    #else:
    #    return port.replace('.', '_')


#class ProfiledThread(Thread):
#    def run(self):
#        print "run thread"
#        profiler = cProfile.Profile()
#        try:
#            return profiler.runcall(Thread.run, self)
#            #profiler.print_stats()
#        finally:
#            print "dump profile"
#            profiler.dump_stats('aggr_handler.profile')


class Aggregator(object):
    """ This class provides FaVe's central aggregation service.
    """

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
        while not self.stop:
            data = self.queue.get()
            Aggregator.LOGGER.debug('worker: fetched data from queue')

            if not data:
                Aggregator.LOGGER.debug('worker: ignoring empty data')
                self.queue.task_done()
                continue

            try:
                j = json.loads(data)
            except ValueError:
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
                if dump['trees']:
                    jsonrpc.dump_flow_trees(self.sock, odir)

            else:
                model = model_from_json(j)
                self._sync_diff(model)

            self.queue.task_done()


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

        while not self.stop:
            # accept connections on unix domain socket
            Aggregator.LOGGER.debug("master: wait for connection")
            try:
                only_conn = lambda x: x[0]
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
                    self._delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "switch":
                if cmd.command == "add":
                    self._add_switch(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self._delete_switch(cmd.node)
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
            #sub = self.models[model.node] - model

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
            self._delete_switch(model)

    def _add_model(self, model):
        if model.type == "packet_filter":
            self._add_packet_filter(model)
        elif model.type == "switch":
            self._add_switch(model)

    # XXX: deprecated?
    def _extend_mapping(self, mapping):
        assert isinstance(mapping, Mapping)
        for fld in mapping:
            if fld not in self.mapping:
                self.mapping.extend(fld)


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


    def _add_tables(self, model, prefixed=False):
        for table in model.tables:
            name = '_'.join([model.node, table])

            if name not in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for port in model.ports:
                    if prefixed and port.startswith("in_") and table.startswith("pre_routing"):
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
                    "worker: add link to netplumber from %s to %s", gport1, gport2
                )
                jsonrpc.add_link(self.sock, gport1, gport2)

                self.links[gport1] = gport2


    def _add_rules(self, model):
        for table in model.tables:
            # XXX: ugly as f*ck... eliminate INPUT/OUTPUT and make PREROUTING static???
            if table in [
                    "pre_routing",
                    "post_routing",
                    "input_states",
                    "output_states",
                    "forward_states"
            ]:
                Aggregator.LOGGER.debug("worker: skip adding rules to table %s", table)
                continue

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            Aggregator.LOGGER.debug("worker: add rules to %s", tname)

            for rid, vec, act in model.tables[table]:
                rvec = Vector(length=self.mapping.length)
                for fld in model.mapping:
                    g_offset = self.mapping[fld]
                    m_offset = model.mapping[fld]
                    size = FIELD_SIZES[fld]
                    rvec[g_offset:g_offset+size] = vec[m_offset:m_offset+size]

                ports = [self._global_port(
                    '_'.join([model.node, table, act.lower()])
                )] if act in ['ACCEPT', 'MISS'] else []

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)",
                    rid, tid, rvec.vector if rvec else "*", ports
                )
                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    rid,
                    [],
                    ports,
                    rvec.vector if rvec.vector else 'x'*8,
                    None,
                    None
                )
                if calc_rule_index(tid, rid) in self.rule_ids:
                    self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(tid, rid)] = [r_id]

        for table in ["post_routing"]:
            if table not in model.tables:
                continue

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                if not isinstance(rule, SwitchRule):
                    rule = SwitchRule.from_json(rule)
                rid = rule.idx

                self._absorb_mapping(rule.mapping)

                rvec = Vector(length=self.mapping.length)
                for fld in rule.match:
                    offset = self.mapping[fld.name]
                    size = FIELD_SIZES[fld.name]
                    rvec[offset:offset+size] = field_value_to_bitvector(fld).vector

                rewrite = None
                if 'interface' in self.mapping:
                    rewrite = dc(rvec)
                    offset = self.mapping["interface"]
                    size = FIELD_SIZES["interface"]
                    rewrite[offset:offset+size] = "x"*size

                ports = []
                for act in rule.actions:
                    if act.name != "forward":
                        continue
                    ports.extend([self._global_port(p) for p in act.ports])

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)",
                    rule.idx, tid, rvec.vector if rvec else "*", ports
                )
                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    rule.idx,
                    [],
                    ports,
                    rvec.vector,
                    None,
                    rewrite.vector if rewrite else None
                )
                if calc_rule_index(tid, rid) in self.rule_ids:
                    self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(tid, rid)] = [r_id]

        for table in ["pre_routing"]:
            if table not in model.tables:
                continue

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                if not isinstance(rule, SwitchRule):
                    rule = SwitchRule.from_json(rule)
                rid = rule.idx

                self._absorb_mapping(rule.mapping)

                rvec = Vector(length=self.mapping.length)
                for fld in rule.match:
                    offset = self.mapping[fld.name]
                    size = FIELD_SIZES[fld.name]
                    rvec[offset:offset+size] = field_value_to_bitvector(fld).vector

                ports = []
                for act in rule.actions:
                    if act.name != "forward":
                        continue
                    ports.extend([self._global_port(p) for p in act.ports])

                rewrite = None
                if "interface" not in self.mapping:
                    self.mapping.extend("interface")
                    rvec.enlarge(FIELD_SIZES["interface"])

                rewrite = dc(rvec)
                offset = self.mapping["interface"]
                size = FIELD_SIZES["interface"]

                for port in range(1, 1+(len(self.models[model.node].ports)-19)/2):
                    rewrite[offset:offset+size] = '{:016b}'.format(port)

                    Aggregator.LOGGER.debug(
                        "worker: add rule %s to %s:\n\t((%s) %s -> (%s) %s)",
                        rule.idx,
                        self.tables["%s_%s" % (model.node, table)],
                        self._global_port("%s_%s" % (model.node, str(port))),
                        rvec.vector if rvec else "*",
                        rewrite.vector if rewrite else "*",
                        ports
                    )
                    r_id = jsonrpc.add_rule(
                        self.sock,
                        self.tables["%s_%s" % (model.node, table)],
                        rule.idx,
                        [self._global_port("%s_%s" % (model.node, str(port)))],
                        ports,
                        rvec.vector,
                        None,
                        rewrite.vector
                    )
                    if calc_rule_index(tid, rid) in self.rule_ids:
                        self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
                    else:
                        self.rule_ids[calc_rule_index(tid, rid)] = [r_id]

        for table in ["input_states", "output_states", "forward_states"]:
            if table not in model.tables:
                continue

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                if not isinstance(rule, SwitchRule):
                    rule = SwitchRule.from_json(rule)
                rid = rule.idx

                self._absorb_mapping(rule.mapping)

                rvec = Vector(length=self.mapping.length)
                for fld in rule.match:
                    offset = self.mapping[fld.name]
                    size = FIELD_SIZES[fld.name]
                    rvec[offset:offset+size] = field_value_to_bitvector(fld).vector

                port = self._global_port(
                    "%s_%s" % (tname, 'miss' if rid == 65535 else 'accept')
                )

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)",
                    rule.idx,
                    self.tables["%s_%s" % (model.node, table)],
                    rvec.vector if rvec else "*",
                    port
                )

                r_id = jsonrpc.add_rule(
                    self.sock,
                    self.tables["%s_%s" % (model.node, table)],
                    rule.idx,
                    [],
                    [port],
                    rvec.vector,
                    None,
                    None
                )
                if calc_rule_index(tid, rid) in self.rule_ids:
                    self.rule_ids[calc_rule_index(tid, rid)].append(r_id)
                else:
                    self.rule_ids[calc_rule_index(tid, rid)] = [r_id]

    # XXX: merge with pre- post-routing handling above?
    def _add_switch_rules(self, model):
        for table in model.tables:

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                rid = rule.idx

                self._absorb_mapping(rule.mapping)

                rvec = Vector(length=self.mapping.length)
                for fld in rule.match:
                    offset = self.mapping[fld.name]
                    size = FIELD_SIZES[fld.name]
                    rvec[offset:offset+size] = field_value_to_bitvector(fld).vector

                ports = []
                for act in rule.actions:
                    if act.name != "forward":
                        continue
                    ports.extend([
                        self._global_port(p) for p in act.ports
                    ])

                Aggregator.LOGGER.debug(
                    "worker: add rule %s to %s:\n\t(%s -> %s)",
                    rule.idx, tid, rvec.vector if rvec else "*", ports
                )

                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    rule.idx,
                    [],
                    ports,
                    rvec.vector,
                    None,
                    None
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


    def _delete_rules(self, model):
        for table in model.tables:
            tid = self.tables['_'.join([model.node, table])]

            only_rid = lambda x: x[0]
            for rid in [only_rid(x) for x in model.tables[table]]:
                for r_id in self.rule_ids[calc_rule_index(tid, rid)]:
                    jsonrpc.remove_rule(self.sock, r_id)
                del self.rule_ids[calc_rule_index(tid, rid)]


    def _delete_wiring(self, model):
        prefix = lambda x: '.'.join(x.split('.')[:len(x.split('.'))-1])

        for port1, port2 in model.wiring:
            node1 = prefix(port1)
            node2 = prefix(port2)

            idx1 = self.tables[node1]
            idx2 = self.tables[node2]

            jsonrpc.remove_link(
                self.sock,
                calc_port(idx1, model, port1),
                calc_port(idx2, model, port2)
            )


    def _delete_tables(self, model):
        for table in model.tables:
            name = '_'.join([model.node, table])

            if not self.models[model.node].tables[table]:
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
        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self._global_port(node+'.1')
        port2 = self.links[port1]
        jsonrpc.remove_link(self.sock, port1, port2)
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        jsonrpc.remove_source(self.sock, sid)
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
        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self._global_port(node+'.1')
        port2 = self.links[port1]
        jsonrpc.remove_link(self.sock, port1, port2)
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        jsonrpc.remove_source(self.sock, sid)

        del self.tables[node]


    def _get_model_table(self, node):
        mtype = self.models[node].type
        return self.tables[
            node+'_post_routing' if mtype == 'packet_filter' else node+'.1'
        ]


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

        filter_expr = {"type" : "header", "header" : filter_hs}

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


        if test_fields and test_path:
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

    log_handler = logging.FileHandler('/tmp/np/aggregator.log')
    Aggregator.LOGGER.addHandler(log_handler)
    Aggregator.LOGGER.setLevel(logging.DEBUG)

    try:
        sock = jsonrpc.connect_to_netplumber(server, port)
    except jsonrpc.RPCError as err:
        Aggregator.LOGGER.error(err.message)
        print_help()
        sys.exit(1)

    global _AGGREGATOR
    _AGGREGATOR = Aggregator(sock)

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
