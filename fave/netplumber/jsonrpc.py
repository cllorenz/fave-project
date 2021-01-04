#!/usr/bin/env python2

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
import cProfile

PROFILE = cProfile.Profile()

def profile_method(method):
    """ Enriches a method with profiling capabilities.
    """

    def profile_wrapper(*args, **kwargs):
        """ Wrapper for profiling.
        """

        PROFILE.enable()
        method(*args, **kwargs)
        PROFILE.disable()

    return profile_wrapper


def dump_stats():
    """ Dumps profiling results.
    """
    PROFILE.dump_stats("jsonrpc.stats")


def _sendrecv(sock, msg):
    """ Synchronous RPC call.
    """
    sock.sendall(msg)
    result = ''
    while True:
        part = sock.recv(4096)
        result += part
        if len(part) < 4096:
            break

    return result


def _extract_node(msg):
    """ Extracts the node ID from node-related RPC call results.
    """

    data = json.loads(msg)
    if "error" in data and data["error"]["code"] != 0:
        raise RPCError(data["error"]["message"])

    return data["result"]


def _basic_rpc():
    """ Creates basic RPC structure.
    """
    return {"id":"0", "jsonrpc":"2.0"}


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
            "could not create socket from %s" % "address %s" % (
                server if port == 0 else "address %s and port %s" % (server, port)
            )
        )

    tries = 5
    while tries > 0:
        try:
            sock.connect(backend)
            break
        except socket.error:
            time.sleep(1)
            tries -= 1

    try:
        sock.getpeername()
    except socket.error:
        raise RPCError("could not connect to net_plumber")

    return sock


def stop(sock):
    """ Stops the NetPlumber service.

    Keyword arguments:
    sock - A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "stop"
    data["params"] = None
    _sendrecv(sock, json.dumps(data))
    sock.close()


#@profile_method
def init(sock, length):
    """ Initializes a NetPlumber instance with vectors of a certain length.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    length -- The vector length
    """

    data = _basic_rpc()
    data["method"] = "init"
    data["params"] = {"length":length}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def destroy(sock):
    """ Destroys the active NetPlumber instance.

    Keyword arguments:
    sock - A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "destroy"
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_table(sock, t_idx, ports):
    """ Adds a table.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    t_idx -- The table's ID
    ports -- The table's ports
    """

    data = _basic_rpc()
    data["method"] = "add_table"
    data["params"] = {"id":t_idx, "in":ports}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def remove_table(sock, t_idx):
    """ Removes a table.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    t_idx -- The table's ID
    """

    data = _basic_rpc()
    data["method"] = "remove_table"
    data["params"] = {"id":t_idx}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_rule(sock, t_idx, r_idx, in_ports, out_ports, match, mask, rewrite):
    """ Adds a rule to a table.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
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
    return _extract_node(_sendrecv(sock, json.dumps(data)))


#@profile_method
def remove_rule(sock, r_idx):
    """ Removes a rule.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    r_idx -- The rule's ID as returned by its previous add call.
    """

    data = _basic_rpc()
    data["method"] = "remove_rule"
    data["params"] = {"node":r_idx}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_link(sock, from_port, to_port):
    """ Adds a directed link between two ports.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    from_port -- The link's start port
    to_port -- The link's target port
    """

    data = _basic_rpc()
    data["method"] = "add_link"
    data["params"] = {"from_port":from_port, "to_port":to_port}
    _sendrecv(sock, json.dumps(data))


def add_links_bulk(sock, links):
    """ Adds directed links.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    links -- A list of source and destination port pairs
    """

    data = _basic_rpc()
    data["method"] = "add_link"

    for from_port, to_port in links:
        data["params"] = {"from_port":from_port, "to_port":to_port}
        _sendrecv(sock, json.dumps(data))


#@profile_method
def remove_link(sock, from_port, to_port):
    """ Removes a link.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    from_port -- The link's start port.
    to_port -- The link's target port.
    """

    data = _basic_rpc()
    data["method"] = "remove_link"
    data["params"] = {"from_port":from_port, "to_port":to_port}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_source(sock, hs_list, hs_diff, ports):
    """ Adds a source node.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    hs_list -- A list of vectors emitted by the source
    hs_diff -- A list of vectors subtracted by the source's emission
    ports -- The source's egress ports
    """

    data = _basic_rpc()
    data["method"] = "add_source"
    if not hs_diff and len(hs_list) == 1:
        data["params"] = {
            "hs":hs_list[0],
            "ports":ports
        }
    else:
        data["params"] = {
            "hs":{
                "list":hs_list,
                "diff":hs_diff
            },
            "ports":ports
        }
    return _extract_node(_sendrecv(sock, json.dumps(data)))


def add_sources_bulk(sock, sources):
    """ Adds source nodes as bulk operation.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    sources -- A list of tuples containing a list of emitted vectors, a list of
               vectors to be subtracted from the source's emission, a list of
               egress ports
    """

    data = _basic_rpc()
    data["method"] = "add_source"

    sids = []

    for hs_list, hs_diff, ports in sources:
        if not hs_diff and len(hs_list) == 1:
            data["params"] = {
                "hs":hs_list[0],
                "ports":ports
            }
        else:
            data["params"] = {
                "hs":{
                    "list":hs_list,
                    "diff":hs_diff
                },
                "ports":ports
            }
        sids.append(_extract_node(_sendrecv(sock, json.dumps(data))))

    return sids


#@profile_method
def remove_source(sock, s_idx):
    """ Removes a source node.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    s_idx -- The source's ID as returned by its previous add call
    """

    data = _basic_rpc()
    data["method"] = "remove_source"
    data["params"] = {"id":s_idx}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_source_probe(sock, ports, mode, filterexp, test):
    """ Adds a probe node.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    ports -- The probe's ingress ports
    mode -- The probe's mode (existential|universal)
    filterexp -- The probe's filter expression
    test -- The probe's test expression
    """

    data = _basic_rpc()
    data["method"] = "add_source_probe"
    data["params"] = {
        "ports":ports,
        "mode":mode,
        "filter":filterexp,
        "test":test
    }
    return _extract_node(_sendrecv(sock, json.dumps(data)))


#@profile_method
def remove_source_probe(sock, sp_idx):
    """ Removes probe node.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    sp_idx -- The probe's ID as returned by its previous add call
    """

    data = _basic_rpc()
    data["method"] = "remove_source_probe"
    data["params"] = {"id":sp_idx}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_slice(sock, nid, ns_list, ns_diff):
    """ Adds a network slice.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
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
    _sendrecv(sock, json.dumps(data))


#@profile_method
def remove_slice(sock, nid):
    """ Removes a network slice.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    nid -- The slice's ID
    """

    data = _basic_rpc()
    data["method"] = "remove_slice"
    data["params"] = {"id":nid}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_slice_matrix(sock, matrix):
    """ Adds a reachability matrix to a network slice.

    The (directed) matrix represents pairs of slice ids
    between which reachability is allowed.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    matrix -- The reachability matrix as CSV
    """

    data = _basic_rpc()
    data["method"] = "add_slice_matrix"
    data["params"] = {"matrix":matrix}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def remove_slice_matrix(sock):
    """ Clears all contents from reachability matrix
        for network slices.

    Keyword arguments:
    sock --- A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "remove_slice_matrix"
    _sendrecv(sock, json.dumps(data))


#@profile_method
def add_slice_allow(sock, id1, id2):
    """ Adds a specific (directional) allowed pair
        id1->id2 between which reachability is allowed

    Keyword arguments:
    sock --- A socket connected to NetPlumber
    id1  --- src slice id
    id2  --- dst slice id
    """

    data = _basic_rpc()
    data["method"] = "add_slice_allow"
    data["params"] = {"id1": id1,
                      "id2": id2}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def remove_slice_allow(sock, id1, id2):
    """ Removes a specific (directional) allowed pair
        id1->id2 between which reachability is allowed

    Keyword arguments:
    sock --- A socket connected to NetPlumber
    id1  --- src slice id
    id2  --- dst slice id
    """

    data = _basic_rpc()
    data["method"] = "remove_slice_allow"
    data["params"] = {"id1": id1,
                      "id2": id2}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def print_slice_matrix(sock):
    """ Prints the reachability matrix to slice logger.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "print_slice_matrix"
    _sendrecv(sock, json.dumps(data))


#@profile_method
def dump_slices_pipes(sock, odir):
    """ Dumps NetPlumber's plumbing network including pipes with slice ids.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON files
    """

    data = _basic_rpc()
    data["method"] = "dump_slices_pipes"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def print_table(sock, t_idx):
    """ Prints a table using NetPlumber's default logger.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    t_idx -- The table's ID
    """

    data = _basic_rpc()
    data["method"] = "print_table"
    data["params"] = {"id":t_idx}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def print_topology(sock):
    """ Prints NetPlumber's topology using its default logger.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "print_topology"
    data["params"] = None
    _sendrecv(sock, json.dumps(data))


#@profile_method
def print_plumbing_network(sock):
    """ Prints NetPlumber's plumbing network using its default logger.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "print_plumbing_network"
    data["params"] = None
    _sendrecv(sock, json.dumps(data))

#@profile_method
def reset_plumbing_network(sock):
    """ Resets NetPlumber to its defaults.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    """

    data = _basic_rpc()
    data["method"] = "reset_plumbing_network"
    data["params"] = None
    _sendrecv(sock, json.dumps(data))


#@profile_method
def expand(sock, new_length):
    """ Expands NetPlumber's vectors to a new length.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    new_length -- The vector's new length
    """

    data = _basic_rpc()
    data["method"] = "expand"
    data["params"] = {"length":new_length}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def dump_plumbing_network(sock, odir):
    """ Dumps NetPlumber's plumbing network as JSON including tables and rules.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON files
    """

    data = _basic_rpc()
    data["method"] = "dump_plumbing_network"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def dump_flows(sock, odir):
    """ Dumps the flows residing in NetPlumber.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON file
    """
    data = _basic_rpc()
    data["method"] = "dump_flows"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def dump_flow_trees(sock, odir):
    """ Dumps the flows residing in NetPlumber as trees.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON file
    """
    data = _basic_rpc()
    data["method"] = "dump_flow_trees"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))


#@profile_method
def dump_pipes(sock, odir):
    """ Dumps the pipelines residing in NetPlumber.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON file
    """

    data = _basic_rpc()
    data["method"] = "dump_pipes"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))

#@profile_method
def dump_slices_pipes(sock, odir):
    """ Dumps the pipelines with slice information residing in NetPlumber.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON file
    """

    data = _basic_rpc()
    data["method"] = "dump_slices_pipes"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))
    
#@profile_method
def dump_slices(sock, odir):
    """ Dumps the slices residing in NetPlumber.

    Keyword arguments:
    sock -- A socket connected to NetPlumber
    odir -- The output directory for the JSON file
    """

    data = _basic_rpc()
    data["method"] = "dump_slices"
    data["params"] = {"dir" : odir}
    _sendrecv(sock, json.dumps(data))
