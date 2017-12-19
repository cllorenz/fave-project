#!/usr/bin/env python2

import cProfile

import signal

import sys,getopt
from util.print_util import eprint

import re
import socket

import os

import json

import daemon

from threading import Thread

from Queue import Queue

from copy import deepcopy as dc

from netplumber.model import Model
from netplumber.mapping import Mapping, field_sizes
from netplumber.vector import copy_field_between_vectors, Vector, HeaderSpace
import netplumber.jsonrpc as jsonrpc

from ip6np.packet_filter import PacketFilterModel
from ip6np.generator import field_value_to_bitvector
from openflow.switch import SwitchModel, SwitchCommand, SwitchRule
from topology.topology import TopologyCommand, LinksModel
from topology.host import HostModel
from topology.generator import GeneratorModel
from topology.probe import ProbeModel

UDS_ADDR = "/tmp/np_aggregator.socket"

_aggregator = None

profile = cProfile.Profile()

def profile_method(method):
    def profile_wrapper(*args,**kwargs):
        profile.enable()
        method(*args,**kwargs)
        profile.disable()
    return profile_wrapper

def dump_stats():
    profile.dump_stats("aggregator.stats")

def handle_sigterm(signum,frame):
    if _aggregator:
        _aggregator.stop_aggr()

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
    return all([re.match(label,l) for l in labels])


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
    j = json.loads(s)
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
        raise Exception("model type not implemented: " + j["type"])

    else:
        return model.from_json(j)


def calc_port(tab,model,port):
    try:
        return (tab<<16)+model.ports[port]
    except KeyError:
        return (tab<<16)+1


def calc_rule_index(t_idx,r_idx):
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
    return port.replace('.','_')

    if port.count('.') > 1:
        labels = port.split('.')
        l = len(labels)
        return '.'.join(labels[:l-1])+'_'+labels[l-1]
    elif has_dot_but_is_not_post_int_port(port):
        return port
    else:
        return port.replace('.','_')

"""
class ProfiledThread(Thread):
    def run(self):
        print "run thread"
        profiler = cProfile.Profile()
        try:
            return profiler.runcall(Thread.run,self)
            #profiler.print_stats()
        finally:
            print "dump profile"
            profiler.dump_stats('aggr_handler.profile')
"""

class Aggregator(object):
    BUF_SIZE = 4096

    def __init__(self,sock):
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

    def print_aggregator(self):
        print "Aggregator:"
        print self.mapping
        print "tables:\n\t%s" % self.tables
        print "ports:\n\t%s" % self.ports
        print "rule ids:\n\t%s" % self.rule_ids
        print "links:\n\t%s" % self.links

    #@profile_method
    def handler(self):
        while not self.stop:
            data = self.queue.get()
            if data:
                model = model_from_string(data)
                self.sync_diff(model)
            self.queue.task_done()

    def run(self):
        # open new unix domain socket
        uds = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        uds.bind(UDS_ADDR)

        # start thread to handle incoming config events
        t = Thread(target=self.handler)
        t.daemon = True
        t.start()

        uds.listen(1)

        while True:
            # accept connections on unix domain socket
            try:
                conn,addr = uds.accept()
            except socket.error:
                break

            # receive data from unix domain socket
            nbytes = Aggregator.BUF_SIZE
            data = ""
            while nbytes == Aggregator.BUF_SIZE:
                tmp = conn.recv(Aggregator.BUF_SIZE)
                nbytes = len(tmp)
                data += tmp
            if not data:
                break

            # upon data receival enqueue
            self.queue.put(data)

        # close unix domain socket
        uds.close()

        # wait for the config event handler to finish
        self.queue.join()

        #jsonrpc.dump_stats()
        #dump_stats()

        # join thread
        t.join()

    def stop_aggr(self):
        self.stop = True
        self.queue.put("")

    #@profile_method
    def sync_diff(self,model):
        # extend global mapping
        mlength = self.mapping.length

        if model.type == "packet_filter":
            self.extend_mapping(model.mapping)
        elif model.type == "switch_command" and model.command == "add_rule":
            self.extend_mapping(model.rule.mapping)
        elif model.type == "topology_command" and model.command == 'add' and model.model.type in ['probe','host','generator']:
            self.extend_mapping(model.model.mapping)

        if mlength < self.mapping.length:
            jsonrpc.expand(self.sock, self.mapping.length) # XXX: +1 necessary?

        # handle minor model changes (e.g. updates by the control plane)
        if model.type == "switch_command":
            if model.node in self.models:
                switch = dc(self.models[model.node]) # XXX: is there a more efficient way than copying?

                if model.command == "add_rule":
                    switch.add_rule(model.rule.idx,model.rule)
                elif model.command == "remove_rule":
                    switch.remove_rule(model.rule.idx)
                elif model.command == "update_rule":
                    switch.update_rule(model.rule.idx,model.rule)
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
                #test_command = lambda x: x in ["add_rule","update_rule"]
                #rules = [model.rule] if test_command(model.command) else []
                #model = SwitchModel(model.node,ports=ports,rules=rules)

        # handle topology changes (e.g. by the network management)
        if model.type == "topology_command":
            cmd = model

            if cmd.mtype == "links":
                for link in cmd.model:
                    sport,dport = link
                    sport = self.global_port(sport)
                    dport = self.global_port(dport)

                    if cmd.command == "add":
                        jsonrpc.add_link(self.sock,sport,dport)
                        self.links[sport] = dport
                    elif cmd.command == "del":
                        jsonrpc.remove_link(self.sock,sport,dport)
                        del self.links[sport]

            elif cmd.mtype == "packet_filter":
                if cmd.command == "add":
                    self.add_packet_filter(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self.delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype  == "switch":
                if cmd.command == "add":
                    self.add_switch(cmd.model)
                    self.models[cmd.model.node] = cmd.model
                elif cmd.command == "del":
                    self.delete_switch(cmd.node)
                    del self.models[cmd.model.node]

            elif cmd.mtype == "host":
                if cmd.command == "add":
                    self.add_host(cmd.model)
                elif cmd.command == "del":
                    self.delete_host(cmd.node)

            elif cmd.mtype == "generator":
                if cmd.command == "add":
                    self.add_generator(cmd.model)
                elif cmd.command == "del":
                    self.delete_generator(cmd.node)

            elif cmd.mtype == "probe":
                if cmd.command == "add":
                    self.add_probe(cmd.model)
                elif cmd.command == "del":
                    self.delete_probe(cmd.node)

            return

        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            sub = self.models[model.node] - model

# TODO: fix deletion... needs exclusion of pre-, post-routing, state tables
#            print sub

            # remove unecessary items
#            self.delete_model(sub)

            # add new items
            self.add_model(add)

        else:
            self.models[model.node] = model

            # add model completely
            self.add_model(model)


    def delete_model(self,model):
        if model.type == "packet_filter":
            self.delete_packet_filter(model)
        elif model.type == "switch":
            self.delete_switch(model)

    def add_model(self,model):
        if model.type == "packet_filter":
            self.add_packet_filter(model)
        elif model.type == "switch":
            self.add_switch(model)

    def extend_mapping(self,m):
        assert(type(m) == Mapping)
        for f in m:
            if not f in self.mapping:
                self.mapping.extend(f)


    def add_packet_filter(self,model):
        self.add_tables(model,prefixed=True)
        self.add_wiring(model)
        self.add_rules(model)


    def add_switch(self,model):
        self.add_tables(model)
        self.add_wiring(model)
        self.add_switch_rules(model)


    def add_tables(self,model,prefixed=False):
        ext_ports = []
        for t in model.tables:
            name = '_'.join([model.node,t])

            if not name in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for p in model.ports:
                    if prefixed and p.startswith("in_") and t.startswith("pre_routing"):
                        portno = calc_port(idx,model,p)
                        portname = normalize_port('.'.join([model.node,p[3:]]))

                    elif prefixed and p.startswith("out_") and t.startswith("post_routing"):
                        portno = calc_port(idx,model,p)
                        portname = normalize_port('.'.join([model.node,p[4:]]))

                    elif prefixed and not p.startswith(t):
                        continue

                    else:
                        portno = calc_port(idx,model,p)
                        portname = normalize_port('.'.join([model.node,p]))

                    ports.append(portno)
                    self.ports[portname] = portno

                jsonrpc.add_table(self.sock,idx,ports)


    def add_wiring(self,model):
        # add links between tables
        for p1,p2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if p1 in ["internals_in","post_routing"] or \
                p2 in ["internals_out","post_routing"]:
                continue

            prefix = lambda x: '_'.join(x.split('_')[:2])
            n1 = '_'.join([model.node,prefix(p1)])
            n2 = '_'.join([model.node,prefix(p2)])

            jsonrpc.add_link(
                self.sock,
                self.global_port('_'.join([model.node,p1])),
                self.global_port('_'.join([model.node,p2]))
            )

    def add_rules(self,model):
        for t in model.tables:
            # XXX: ugly as f*ck... eliminate INPUT/OUTPUT and make PREROUTING static???
            if t == "pre_routing" or t == "post_routing":
                continue

            ti = self.tables['_'.join([model.node,t])]

            for ri,v,a in model.tables[t]:
                rv = Vector(length=self.mapping.length)
                for f in model.mapping:
                    offset = model.mapping[f]
                    size = field_sizes[f]
                    rv[offset:offset+size] = v[offset:offset+size]

                self.rule_ids[calc_rule_index(ti,ri)] = jsonrpc.add_rule(
                    self.sock,
                    ti,
                    ri,
                    [],
                    [self.global_port(
                        '_'.join([model.node,t,a.lower()])
                    )] if a in ['ACCEPT','MISS'] else [],
                    rv.vector if rv.vector else 'x'*8,
                    'x'*self.mapping.length if self.mapping.length else 'x'*8,
                    None
                )

        for table in ["post_routing"]:
            if not table in model.tables:
                continue

            ti = self.tables['_'.join([model.node,table])]

            for r in model.tables[table]:
                if type(r) == SwitchRule:
                    rule = r
                else:
                    rule = SwitchRule.from_json(r)
                ri = rule.idx

                mlength = self.mapping.length
                self.mapping.expand(rule.mapping)
                if mlength < self.mapping.length:
                    jsonrpc.expand(self.sock,self.mapping.length)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = field_sizes[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                rw = dc(rv)
                offset = self.mapping["interface"]
                size = field_sizes["interface"]
                rw[offset:offset+size] = "x"*size

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([self.global_port(p) for p in a.ports])

                self.rule_ids[calc_rule_index(ti,ri)] = jsonrpc.add_rule(
                    self.sock,
                    self.tables['_'.join([model.node,table])],
                    rule.idx,
                    [],
                    ports,
                    rv.vector,
                    'x'*self.mapping.length if self.mapping.length else 'x'*8,
                    rw.vector
                )

        for table in ["pre_routing"]:
            if not table in model.tables:
                continue

            ti = self.tables['_'.join([model.node,table])]

            for r in model.tables[table]:
                if type(r) == SwitchRule:
                    rule = r
                else:
                    rule = SwitchRule.from_json(r)
                ri = rule.idx

                mlength = self.mapping.length
                self.mapping.expand(rule.mapping)
                if mlength < self.mapping.length:
                    jsonrpc.expand(self.sock,self.mapping.length)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = field_sizes[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([self.global_port(p) for p in a.ports])

                rw = dc(rv)
                offset = self.mapping["interface"]
                size = field_sizes["interface"]

                for port in range(1,1+(len(self.models[model.node].ports)-19)/2):
                    rw[offset:offset+size] = '{:016b}'.format(port)

                    self.rule_ids[calc_rule_index(ti,ri)] = jsonrpc.add_rule(
                        self.sock,
                        self.tables['_'.join([model.node,table])],
                        rule.idx,
                        [self.global_port('_'.join([model.node,str(port)]))],
                        ports,
                        rv.vector,
                        'x'*self.mapping.length if self.mapping.length else 'x'*8,
                        rw.vector
            )

    # XXX: merge with pre- post-routing handling above?
    def add_switch_rules(self,model):
        for table in model.tables:
            ti = self.tables['_'.join([model.node,table])]
            for rule in model.tables[table]:
                ri = rule.idx

                mlength = self.mapping.length
                self.mapping.expand(rule.mapping)
                if mlength < self.mapping.length:
                    jsonrpc.expand(self.sock,self.mapping.length)

                rv = Vector(length=self.mapping.length)
                for f in rule.match:
                    offset = self.mapping[f.name]
                    size = field_sizes[f.name]
                    rv[offset:offset+size] = field_value_to_bitvector(f).vector

                ports = []
                for a in rule.actions:
                    if a.name != "forward":
                        continue
                    ports.extend([
                        self.global_port(p) for p in a.ports
                    ])

                self.rule_ids[calc_rule_index(ti,ri)] = jsonrpc.add_rule(
                    self.sock,
                    self.tables['_'.join([model.node,table])],
                    rule.idx,
                    [],
                    ports,
                    rv.vector,
                    'x'*self.mapping.length if self.mapping.length else 'x'*8,
                    None
                )

    def delete_packet_filter(self,model):
        self.delete_rules(model)
        self.delete_wiring(model)
        self.delete_tables(model)

    delete_switch = delete_packet_filter

    """
    def delete_switch(self,model):
        self.delete_rules(model)
        self.delete_wiring(model)
        self.delete_tables(model)
    """


    def delete_rules(self,model):
        for t in model.tables:
            ti = self.tables['_'.join([model.node,t])]

            for ri,v,a in model.tables[t]:
                jsonrpc.remove_rule(self.rule_ids[calc_rule_index(ti,ri)])
                del self.rule_ids[calc_rule_index(ti,ri)]

    def delete_wiring(self,model):
        for p1,p2 in model.wiring:
            n1 = prefix(p1)
            n2 = prefix(p2)

            i1 = self.tables[n1]
            i2 = self.tables[n2]

            jsonrpc.remove_link(calc_port(i1,model,p1),calc_port(i2,model,p2))

    def delete_tables(self,model):
        for t in model.tables:
            name = '_'.join([model.node,t])

            if not self.models[model.node].tables[t]:
                jsonrpc.remove_table(self.sock,self.tables[name])
                del self.tables[name]




    def add_host(self,model):
        name = model.node
        if name in self.tables:
            self.delete_host(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx,model,port)

        self.ports[port] = portno

        outgoing = self.aligned_headerspace(model.outgoing,model.mapping)

        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )

        """
        incoming = self.aligned_headerspace(model.incoming,model.mapping)
        pid = jsonrpc.add_source_probe(
            self.sock,
            [portno],
            'universal',
            {
                "type" : "header",
                "hs_list" : [v.vector for v in incoming.hs_list],
                "hs_diff" : [v.vector for v in incoming.hs_diff]
            },
            None
        )
        """
        self.tables[name] = (idx,sid,model)


    def delete_host(self,node):
        idx,sid,model = self.tables[node]

        # delete links
        p1 = self.global_ports(node+'.1')
        p2 = self.links[p1]
        jsonrpc.remove_link(self.node,p1,p2)
        jsonrpc.remove_link(self.node,p2,p1)

        del self.links[p1]
        del self.links[p2]

        # delete source and probe
        jsonrpc.remove_source(sid)
        #jsonrpc.remove_source_probe(pid)

        del self.tables[node]


    def add_generator(self,model):
        name = model.node
        if name in self.tables:
            self.delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx,model,port)

        self.ports[port] = portno

        outgoing = self.aligned_headerspace(model.outgoing,model.mapping)

        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )
        self.tables[name] = (idx,sid,model)


    def delete_generator(self,node):
        idx,sid,model = self.tables[node]

        # delete links
        p1 = self.global_port(node+'.1')
        p2 = self.links[p1]
        jsonrpc.remove_link(self.node,p1,p2)
        jsonrpc.remove_link(self.node,p2,p1)

        del self.links[p1]
        del self.links[p2]

        # delete source and probe
        jsonrpc.remove_source(sid)

        del self.tables[node]


    def get_model_table(self,node):
        mtype = self.models[node].type
        if mtype == 'packet_filter':
            return self.tables[node+'_post_routing']
        else:
            return self.tables[node+'.1']


    def add_probe(self,model):
        name = model.node
        if name in self.tables:
            self.delete_probe(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx,model,port)

        self.ports[port] = portno

        mlength = self.mapping.length
        self.mapping.expand(model.mapping)
        if mlength < self.mapping.length:
            jsonrpc.expand(self.sock,self.mapping.length)

        filter_fields = self.aligned_headerspace(model.filter_fields,model.mapping)
        test_fields = self.aligned_headerspace(model.test_fields,model.mapping)

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

        pid = jsonrpc.add_source_probe(
            self.sock,
            [portno],
            model.quantor,
            filter_expr,
            test_expr
        )
        self.tables[name] = (idx,pid,model)



    def delete_probe(self,name):
        idx,sid,model = self.tables[node]

        # delete links
        p1 = self.global_port(node+'.1')
        p2 = self.links[p1]
        jsonrpc.remove_link(self.node,p1,p2)
        jsonrpc.remove_link(self.node,p2,p1)

        del self.links[p1]
        del self.links[p2]

        # delete source and probe
        jsonrpc.remove_source_probe(sid)

        del self.tables[node]



    def aligned_headerspace(self,hs,mapping):
        hs_list = []
        for vector in hs.hs_list:
            hs_list.append(self.aligned_vector(vector,mapping))

        hs_diff = []
        for vector in hs.hs_diff:
            hs_diff.append(self.aligned_vector(vector,mapping))

        return HeaderSpace(self.mapping.length,hs_list,hs_diff)


    def aligned_vector(self,vector,mapping):
        v = Vector(self.mapping.length)
        for f in mapping:
            copy_field_between_vectors(mapping,self.mapping,vector,v,f)

        return v


    def global_port(self,port):
        return self.ports[normalize_port(port)]


def main(argv):
    server = "127.0.0.1"
    port = 0

    try:
        opts,args = getopt.getopt(argv,"hs:p:",["help","server=","port="])
    except:
        print_help()
        sys.exit(2)

    for opt,arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-s':
            server = arg if is_ip(arg) or is_domain(arg) else arg if is_unix(arg) else server
        elif opt == '-p':
            port = int(arg) if is_port(arg) else port

    sock = None
    if port == 0:
        np = server
        sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    else:
        np = (server,port)
        sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    if not sock:
        print_help()
        sys.exit(1)

    sock.connect(np)

    global _aggregator
    _aggregator = Aggregator(sock)
    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    signal.signal(signal.SIGTERM,handle_sigterm)

    _aggregator.run()

if __name__ == "__main__":
    #cProfile.run('main(%s)' % sys.argv[1:],"aggregator.profile")
    main(sys.argv[1:])
