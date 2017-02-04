#!/usr/bin/env python2

import sys,getopt
from util.print_util import eprint

import re
import socket

import os

import json

import daemon

from threading import Thread

from Queue import Queue

from netplumber.model import Model
from netplumber.mapping import Mapping, field_sizes
from netplumber.vector import Vector
import netplumber.jsonrpc as jsonrpc

from ip6np.packet_filter import PacketFilterModel
from openflow.switch import SwitchModel, SwitchCommand


UDS_ADDR = "/tmp/np_aggregator.socket"

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


def is_port(s):
    try:
        p = int(s)
        if 0 > p or p > 0xffff:
            return False
    except:
        return False

    return True


def model_from_string(s):
    j = json.loads(s)
    try:
        return {
            "model" : Model,
            "packet_filter" : PacketFilterModel,
            "switch" : SwitchModel,
            "switch_command" : SwitchCommand
        }[j["type"]].from_json(j)
    except KeyError:
        raise Exception("model type not implemented")


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

    def handler(self):
        while True:
            command,data = self.queue.get()
            model = model_from_string(data)

            self.sync_diff(model)

            """
            if model.node in self.models:
                diff,common = models[model.node].diff(model)
                self.sync_diff(diff=diff,common=common)

            else:
                self.models[model.node] = model
                self.sync_diff(common=model)
            """
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
            conn,addr = uds.accept()

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


    def sync_diff(self,model):
        # extend global mapping
        if self.mapping.length <= model.mapping.length:
            jsonrpc.expand(self.sock,model.mapping.length)

        self.extend_mapping(model.mapping)

        # handle minor model changes (e.g. updates by the control plane)
        if model.type == "switch_command":
            if model.node in self.models:
                switch = self.models[model.node]

                if model.command == "add_rule":
                    switch.add_rule(model.idx,model.rule)
                elif model.command == "remove_rule":
                    switch.remove_rule(model.idx)
                elif model.command == "update_rule":
                    switch.update_rule(model.idx,model.rule)
                else:
                    # ignore unknown command
                    return

                model = switch

            else:
                ports = self.query_ports(model.node)
                test_command = lambda x: x in ["add_rule","update_rule"]
                rules = [model.rule] if test_command(model.command) else []
                model = SwitchModel(model.node,ports=ports,rules=rules)

        if model.node in self.models:
            # calculate items to remove and items to add
            add = model - self.models[model.node]
            sub = self.models[model.node] - model

            # remove unecessary items
            self.delete_model(sub)

            # add new items
            self.add_model(add)

        else:
            self.models[model.node] = model

            # add model completely
            self.add_model(model)


    def extend_mapping(self,m):
        assert(type(m) == Mapping)
        for f in m:
            if not f in self.mapping:
                self.mapping.extend(f)

    def add_model(self,model):
        # add tables
        for t in model.tables:
            name = model.node + '_' + t
            idx = 1

            if name in self.tables:
                idx = self.tables[t]
            else:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

            ports = []
            for p in model.ports:
                if p.startswith(t):
                    port_no = (idx << 16) + model.ports[p]
                    ports.append(port_no)
                    self.ports[model.node+'_'+p] = port_no

            #ports = [(idx << 16)+model.ports[p] for p in model.ports if p.startswith(t)]
            #ports += [(idx << 16)+model.ports[p] for p in ["internals_in","internals_out","post_routing"] if p in model.ports]

            jsonrpc.add_table(self.sock,idx,ports)


        # add links between tables
        for p1,p2 in model.wiring:

            # TODO: handle special ports properly
            if p1 in ["internals_in","internals_out","post_routing"] or \
                p2 in ["internals_in","internals_out","post_routing"]:
                continue

            prefix = lambda x: '_'.join(x.split('_')[:2])
            n1 = model.node + '_' + prefix(p1)
            n2 = model.node + '_' + prefix(p2)

            i1 = self.tables[n1]
            i2 = self.tables[n2]

            jsonrpc.add_link(
                self.sock,
                (i1<<16)+model.ports[p1],
                (i2<<16)+model.ports[p2]
            )

        # add rules to tables
        for t in model.tables:
            ti = self.tables[model.node+'_'+t]

            for ri,v,a in model.tables[t]:
                rv = Vector(length=self.mapping.length)
                for f in model.mapping:
                    offset = model.mapping[f]
                    size = field_sizes[f]
                    rv[offset:offset+size] = v[offset:offset+size]

                self.rule_ids[(ti<<16)+ri] = jsonrpc.add_rule(
                    self.sock,
                    ti,
                    ri,
                    [],
                    [self.ports[model.node+'_'+t+'_accept']] if a == 'ACCEPT' else [],
                    rv.vector,
                    'x'*self.mapping.length,
                    None
                )

    def delete_model(self,model):
        # delete rules
        for t in model.tables:
            ti = self.tables[model.node+'_'+t]

            for ri,v,a in model.tables[t]:
                jsonrpc.remove_rule(self.rule_ids[(ti<<16)+ri])
                del self.rule_ids[(ti<<16)+ri]


        # delete links
        for p1,p2 in model.wiring:
            n1 = prefix(p1)
            n2 = prefix(p2)

            i1 = self.tables[n1]
            i2 = self.tables[n2]

            jsonrpc.remove_link((i1<<16)+model.ports[p1],(i2<<16)+model.ports[p2])


        # delete tables if possible
        for t in model.tables:
            name = model.node + '_' + t
            if not self.models[model.name][t]:
                jsonrpc.remove_table(self.sock,self.tables[name])
                del self.tables[name]


def main(argv):
    server = "127.0.0.1"
    port = 1234

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
            server = arg if is_ip(arg) or is_domain(arg) else server
        elif opt == '-p':
            port = int(arg) if is_port(arg) else port

    np = (server,port)
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.connect(np)

    aggregator = Aggregator(sock)
    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    aggregator.run()

if __name__ == "__main__":
    main(sys.argv[1:])
