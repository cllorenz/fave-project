#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>
# List of co-authors:
#    Jan Sohre

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

""" This module provides methods for interacting with a NetPlumber service via RPC.
"""

import json
import time
import socket

#import util.dynamic_distribution as dynamic_distribution  # XXX

NET_PLUMBER_DEFAULT_UNIX = '/dev/shm/np1.socket'
NET_PLUMBER_DEFAULT_IP = '127.0.0.1'
NET_PLUMBER_DEFAULT_PORT = 44001


def _sendrecv(sock, msg):
    """ Synchronous RPC call.
    """
    sock.sendall(msg.encode('utf8'))
    result = ''
    while True:
        part = sock.recv(4096)
        result += part
        if len(part) < 4096:
            break

    return result


def _async_send(socks, msg):
    """ Asynchronous RPC call send.
    """

    for sock in socks:
        sock.sendall((msg+'\n').encode('utf8'))


def _parse_msg(msg):
    data = json.loads(msg)
    if "error" in data and data["error"]["code"] != 0:
        raise RPCError(data["error"]["message"])

    return data


def _sync_recv(socks):
    results = []
    for sock in socks:
        result = ''
        while True:
            chunk = sock.recv(4096, socket.MSG_PEEK).decode('utf8')
            pos = chunk.find('\n')

            if pos == -1:
                result += sock.recv(4096).decode('utf8')
            else:
                result += chunk[:pos]
                sock.recv(pos+1).decode('utf8')
                break

        results.append(_parse_msg(result))

    return results


def _asend_recv(socks, msg):
    _async_send(socks, msg)
    return _sync_recv(socks)



def _extract_node(msg):
    """ Extracts the node ID from node-related RPC call results.
    """
    return msg["result"]


def _extract_nodes(msg):
    """ Extracts the node IDs from node-related batch RPC call results.
    """
    return msg["result"]


def _extract_index(msg):
    """ Extracts the index encoded in the message ID.
    """
    return msg["id"]


def _basic_rpc(idx=0):
    """ Creates basic RPC structure.
    """
    return {"id" : idx, "jsonrpc" : "2.0"}


class RPCError(Exception):
    """ This class provides an exception type for RPC operations.
    """
    pass

def connect_to_netplumber(server, port=0):
    """ Creates a connected socket to NetPlumber.

    Keyword arguements:
    server - A server address to connect to. May be either an IPv4 address or a
             UNIX domain socket.
    port - An optional TCP port if IPv4 is used.
    """

    backend = server if port == 0 else (server, port)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) if port == 0 else \
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if not sock:
        raise RPCError(
            "could not create socket for %s" % ('unix' if port == 0 else 'tcp/ip')
        )

    sock.setblocking(1)

    tries = 10
    while tries > 0:
        try:
            sock.connect(backend)
            break
        except socket.error:
            time.sleep(0.1)
            tries -= 1

    try:
        sock.getpeername()
    except socket.error:
        raise RPCError(
            "could not connect to net_plumber at %s" % (server if port == 0 else (server, port))
        )

    return sock


def stop(socks):
    """ Stops the NetPlumber service.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "stop"
    data["params"] = None
    _asend_recv(socks, json.dumps(data))
    for sock in socks:
        sock.close()


def init(socks, length):
    """ Initializes NetPlumber instances with vectors of a certain length.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    length -- The vector length
    """

    data = _basic_rpc()
    data["method"] = "init"
    data["params"] = {"length":length}
    _asend_recv(socks, json.dumps(data))


def destroy(socks):
    """ Destroys the active NetPlumber instances.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "destroy"
    _asend_recv(socks, json.dumps(data))


def add_table(socks, t_idx, ports):
    """ Adds a table.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    t_idx -- The table's ID
    ports -- The table's ports
    """

    data = _basic_rpc()
    data["method"] = "add_table"
    data["params"] = {"id":t_idx, "in":ports}
    _asend_recv(socks, json.dumps(data))


def remove_table(socks, t_idx):
    """ Removes a table.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    t_idx -- The table's ID
    """

    data = _basic_rpc()
    data["method"] = "remove_table"
    data["params"] = {"id":t_idx}
    _asend_recv(socks, json.dumps(data))


def add_rule(socks, t_idx, r_idx, in_ports, out_ports, match, mask, rewrite):
    """ Adds a rule to a table.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    t_idx -- The table's ID
    r_idx -- The rule's ID
    in_ports -- The rule's matched ports
    out_ports -- The rule's forwarding ports
    match -- The rule's matching vector
    mask -- The rule's mask bits as vector
    rewrite -- The rule's rewriting as vector
    """

    data = _basic_rpc()
    data["method"] = "add_rule"
    data["params"] = {
        "table":t_idx,
        "index":r_idx,
        "in":in_ports,
        "out":out_ports,
        "match":match,
        "mask":mask,
        "rw":rewrite
    }
    res = _asend_recv(socks, json.dumps(data))
    return _extract_node(res[0])


def add_rules_batch(socks, rules):
    """ Adds a list of rules.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    rules -- The list of rules. Each rule is a tuple containing the following:
        t_idx -- The table's ID
        r_idx -- The rule's ID
        in_ports -- The rule's matched ports
        out_ports -- The rule's forwarding ports
        match -- The rule's matching vector
        mask -- The rule's mask bits as vector
        rewrite -- The rule's rewriting as vector
    """

    data = _basic_rpc()
    data["method"] = "add_rules"
    data["params"] = {
        "rules" : [
            {
                "table":t_idx,
                "index":r_idx,
                "in":in_ports,
                "out":out_ports,
                "match":match,
                "mask":mask,
                "rw":rewrite
            } for _np_rid, t_idx, r_idx, in_ports, out_ports, match, mask, rewrite in rules
        ]
    }
    res = _asend_recv(socks, json.dumps(data))
    return _extract_nodes(res[0])


def remove_rule(socks, r_idx):
    """ Removes a rule.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    r_idx -- The rule's ID as returned by its previous add call.
    """

    data = _basic_rpc()
    data["method"] = "remove_rule"
    data["params"] = {"node":r_idx}
    _asend_recv(socks, json.dumps(data))


def add_link(socks, from_port, to_port):
    """ Adds a directed link between two ports.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    from_port -- The link's start port
    to_port -- The link's target port
    """

    data = _basic_rpc()
    data["method"] = "add_link"
    data["params"] = {"from_port":from_port, "to_port":to_port}
    _asend_recv(socks, json.dumps(data))


def add_links_bulk(socks, links, use_dynamic=False):
    """ Adds directed links.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    links -- A list of source and destination port pairs
    """

    for idx, from_port, to_port in links:
        if use_dynamic: break

        data = _basic_rpc(idx)
        data["method"] = "add_link"
        data["params"] = {"from_port":from_port, "to_port":to_port}

        msg = json.dumps(data)

        if idx != -1:
            _async_send(socks[idx % len(socks):idx % len(socks)+1], msg)
        else:
            _async_send(socks, msg)

    for idx, from_port, to_port in links:
        if use_dynamic:
            data = _basic_rpc(idx)
            data["method"] = "add_link"
            data["params"] = {"from_port":from_port, "to_port":to_port}

            msg = json.dumps(data)

            #dynamic_distribution.add_link_to_dict(idx, msg) # XXX
        else:
            if idx != -1:
                _sync_recv(socks[idx % len(socks):idx % len(socks)+1])
            else:
                _sync_recv(socks)

    if use_dynamic:
        pass #dynamic_distribution.distribute_nodes_and_links()  # XXX


def remove_link(socks, from_port, to_port):
    """ Removes a link.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    from_port -- The link's start port.
    to_port -- The link's target port.
    """

    data = _basic_rpc()
    data["method"] = "remove_link"
    data["params"] = {"from_port":from_port, "to_port":to_port}
    _asend_recv(socks, json.dumps(data))


def add_source(socks, idx, hs_list, hs_diff, ports, use_dynamic=False):
    """ Adds a source node.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    hs_list -- A list of vectors emitted by the source
    hs_diff -- A list of vectors subtracted by the source's emission
    ports -- The source's egress ports
    """

    data = _basic_rpc()
    data["method"] = "add_source"
    if not hs_diff and len(hs_list) == 1:
        data["params"] = {
            "id":idx,
            "hs":hs_list[0],
            "ports":ports
        }
    else:
        data["params"] = {
            "id":idx,
            "hs":{
                "list":hs_list,
                "diff":hs_diff
            },
            "ports":ports
        }

    msg = json.dumps(data)

    if use_dynamic:
        #dynamic_distribution.add_node_to_dict(idx, msg) # XXX
        return idx

    res = _asend_recv(socks[idx%len(socks):idx%len(socks)+1], json.dumps(data))
    return _extract_node(res[0])


def add_sources_bulk(socks, sources, use_dynamic=False):
    """ Adds source nodes as bulk operation.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    sources -- An index, a list of tuples containing a list of emitted vectors, a list of
               vectors to be subtracted from the source's emission, a list of
               egress ports
    """

    sids = {}

    for idx, hs_list, hs_diff, ports in sources:
        data = _basic_rpc(idx)
        data["method"] = "add_source"

        if not hs_diff and len(hs_list) == 1:
            data["params"] = {
                "id":idx,
                "hs":hs_list[0],
                "ports":ports
            }
        else:
            data["params"] = {
                "id":idx,
                "hs":{
                    "list":hs_list,
                    "diff":hs_diff
                },
                "ports":ports
            }

        msg = json.dumps(data)

        if use_dynamic:
            #dynamic_distribution.add_node_to_dict(idx, msg) # XXX
            sids[idx] = idx
        else:
            _async_send(socks[idx % len(socks):idx % len(socks)+1], msg)

    if not use_dynamic:
        for idx, _hs_list, _hs_diff, _ports in sources:
            res = _sync_recv(socks[idx % len(socks):idx % len(socks)+1])
            for node in res:
                sids[_extract_index(node)] = _extract_node(node)

    return sids


def remove_source(socks, s_idx):
    """ Removes a source node.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    s_idx -- The source's ID as returned by its previous add call
    """

    data = _basic_rpc()
    data["method"] = "remove_source"
    data["params"] = {"id":s_idx}
    _asend_recv(socks, json.dumps(data))


def add_source_probe(socks, ports, mode, match, filterexp, test, idx):
    """ Adds a probe node.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    ports -- The probe's ingress ports
    mode -- The probe's mode (existential|universal)
    match -- The probe's match
    filterexp -- The probe's filter expression
    test -- The probe's test expression
    """

    data = _basic_rpc()
    data["method"] = "add_source_probe"
    data["params"] = {
        "ports":ports,
        "mode":mode,
        "match":match,
        "filter":filterexp,
        "test":test,
        "id" : idx
    }
    res = _asend_recv(socks, json.dumps(data))
    return _extract_node(res[0])


def remove_source_probe(socks, sp_idx):
    """ Removes probe node.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    sp_idx -- The probe's ID as returned by its previous add call
    """

    data = _basic_rpc()
    data["method"] = "remove_source_probe"
    data["params"] = {"id":sp_idx}
    _asend_recv(socks, json.dumps(data))


def add_slice(socks, nid, ns_list, ns_diff):
    """ Adds a network slice.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    nid -- The slice's ID
    ns_list -- A list of vectors included in the slice
    ns_diff -- A list of vectors subtracted from the slice
    """
    data = _basic_rpc()
    data["method"] = "add_slice"
    data["params"] = {
        "id":nid,
        "net_space":{
            "type":"header",
            "list":ns_list,
            "diff":ns_diff
        }
    }
    _asend_recv(socks, json.dumps(data))


def remove_slice(socks, nid):
    """ Removes a network slice.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    nid -- The slice's ID
    """

    data = _basic_rpc()
    data["method"] = "remove_slice"
    data["params"] = {"id":nid}
    _asend_recv(socks, json.dumps(data))


def add_slice_matrix(socks, matrix):
    """ Adds a reachability matrix to a network slice.

    The (directed) matrix represents pairs of slice ids
    between which reachability is allowed.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    matrix -- The reachability matrix as CSV
    """

    data = _basic_rpc()
    data["method"] = "add_slice_matrix"
    data["params"] = {"matrix":matrix}
    _asend_recv(socks, json.dumps(data))


def remove_slice_matrix(socks):
    """ Clears all contents from reachability matrix
        for network slices.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "remove_slice_matrix"
    _asend_recv(socks, json.dumps(data))


def add_slice_allow(socks, id1, id2):
    """ Adds a specific (directional) allowed pair
        id1->id2 between which reachability is allowed

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    id1  --- src slice id
    id2  --- dst slice id
    """

    data = _basic_rpc()
    data["method"] = "add_slice_allow"
    data["params"] = {"id1": id1,
                      "id2": id2}
    _asend_recv(socks, json.dumps(data))


def remove_slice_allow(socks, id1, id2):
    """ Removes a specific (directional) allowed pair
        id1->id2 between which reachability is allowed

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    id1  --- src slice id
    id2  --- dst slice id
    """

    data = _basic_rpc()
    data["method"] = "remove_slice_allow"
    data["params"] = {"id1": id1,
                      "id2": id2}
    _asend_recv(socks, json.dumps(data))


def print_slice_matrix(socks):
    """ Prints the reachability matrix to slice logger.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "print_slice_matrix"
    _asend_recv(socks, json.dumps(data))


def print_table(socks, t_idx):
    """ Prints a table using NetPlumber's default logger.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    t_idx -- The table's ID
    """

    data = _basic_rpc()
    data["method"] = "print_table"
    data["params"] = {"id":t_idx}
    _asend_recv(socks, json.dumps(data))


def print_topology(socks):
    """ Prints NetPlumber's topology using its default logger.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "print_topology"
    data["params"] = None
    _asend_recv(socks, json.dumps(data))


def print_plumbing_network(socks):
    """ Prints NetPlumber's plumbing network using its default logger.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "print_plumbing_network"
    data["params"] = None
    _asend_recv(socks, json.dumps(data))

def reset_plumbing_network(socks):
    """ Resets NetPlumber to its defaults.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    """

    data = _basic_rpc()
    data["method"] = "reset_plumbing_network"
    data["params"] = None
    _asend_recv(socks, json.dumps(data))


def expand(socks, new_length):
    """ Expands NetPlumber's vectors to a new length.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    new_length -- The vector's new length
    """

    data = _basic_rpc()
    data["method"] = "expand"
    data["params"] = {"length":new_length}
    _asend_recv(socks, json.dumps(data))


def dump_plumbing_network(socks, odir):
    """ Dumps NetPlumber's plumbing network as JSON including tables and rules.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    odir -- The output directory for the JSON files
    """

    data = _basic_rpc()
    data["method"] = "dump_plumbing_network"
    data["params"] = {"dir" : odir}
    _asend_recv(socks[:1], json.dumps(data))


def dump_flows(socks, odir):
    """ Dumps the flows residing in NetPlumber.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    odir -- The output directory for the JSON file
    """
    data = _basic_rpc()
    data["method"] = "dump_flows"
    data["params"] = {"dir" : odir}
    _asend_recv(socks, json.dumps(data))


def dump_flow_trees(socks, odir, keep_simple=False):
    """ Dumps the flows residing in NetPlumber as trees.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    odir -- The output directory for the JSON file
    """
    data = _basic_rpc()
    data["method"] = "dump_flow_trees"
    data["params"] = {"dir" : odir, "simple" : keep_simple}
    _asend_recv(socks, json.dumps(data))


def dump_pipes(socks, odir):
    """ Dumps the pipelines residing in NetPlumber.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    odir -- The output directory for the JSON file
    """

    data = _basic_rpc()
    data["method"] = "dump_pipes"
    data["params"] = {"dir" : odir}
    _asend_recv(socks, json.dumps(data))


def dump_slices_pipes(socks, odir):
    """ Dumps the pipelines with slice information residing in NetPlumber.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    odir -- The output directory for the JSON file
    """

    data = _basic_rpc()
    data["method"] = "dump_slices_pipes"
    data["params"] = {"dir" : odir}
    _asend_recv(socks, json.dumps(data))

def check_anomalies(socks, table=0, use_shadow=False, use_reach=False, use_general=False):
    """ Checks whether a table contains anomalies such as shadowed or unreachable rules.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    table -- The table ID (0 if all tables should be checked)
    """

    data = _basic_rpc()
    data["method"] = "check_anomalies"
    data["params"] = {
        "table" : table,
        "use_shadow" : use_shadow,
        "use_reach" : use_reach,
        "use_general" : use_general
    }
    _asend_recv(socks, json.dumps(data))

def check_compliance(socks, rules):
    """ Checks a set of policy rules for compliance.

    Keyword arguments:
    socks -- A list of sockets connected to NetPlumber instances
    rules -- The compliance rules
    """

    data = _basic_rpc()
    data["method"] = "check_compliance"
    data["params"] = {"rules":rules}
    _asend_recv(socks, json.dumps(data))
