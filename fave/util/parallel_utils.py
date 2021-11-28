#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Lukas Golombek <lgolombe@uni-potsdam.de>

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

# Authors: lgolombe@uni-potsdam.de (Lukas Golombek)
#          claas_lorenz@genua.de (Claas Lorenz)

""" This module provides utilities to manage NetPlumber instances in a SLURM
    managed cluster of compute nodes.
"""

import os
import re

import netplumber.jsonrpc as jsonrpc

class ParallelException(Exception):
    """ An exception for issues of parallel execution.
    """
    pass


def stop_all_np_instances():
    """ Stops all running NetPlumber instances.
    """

    print("Stopping all NP instances")
    socklist = _get_socklist()
    for sock in socklist:
        try:
            jsonrpc.stop(sock)
            print("Successfully stopped instance: {}".format(sock))
        except jsonrpc.RPCError as err:
            print("Could not stop socket {}: {}".format(sock, repr(err)))


def _get_socklist():
    """ Connects sockets to all running netplumber instances
    """

    # open sockets to multiple netplumber instances on the given hosts
    serverlist = get_serverlist()
    try:
        socklist = [
            jsonrpc.connect_to_netplumber(
                server['host'], server['port']
            ) for server in serverlist
        ]
        print("Socklist:", socklist)
    except jsonrpc.RPCError as err:
        raise ParallelException(
            'get_socklist(): could not connect all sockets: {}'.format(repr(err))
        )

    if not socklist: raise ParallelException('No netplumber instances found')

    return socklist


def get_serverlist():
    """ Builds list of host addresses for all running netplumber instances
    """

    start_port = int(os.environ['start_port'])
    end_port = int(os.environ['end_port'])
    portlist = [port for port in range(start_port, end_port + 1)]

    serverlist = []

    nodelist = os.environ['SLURM_JOB_NODELIST']
    print(nodelist)
    #master_node_id = os.environ['slurm_node_id'] # assumes no instances on master node

    nodes = set(_parse_slurm_nodelist(nodelist))
    #nodes.remove(master_node_id)

    for node in nodes:
        for port in portlist:
            serverlist.append({'host': node, 'port': port})

    return serverlist


def _parse_slurm_nodelist(nodelist):
    nodes = []
    next_delim = ''
    while next_delim != ']':
        next_id, next_delim, nodelist = _get_next_node_id_and_delim(nodelist)
        if next_delim == ',':
            nodes.append("node{}".format(next_id))
            end_id, next_delim, nodelist = _get_next_node_id_and_delim(nodelist)
            nodes.append("node{}".format(end_id))
            continue
        if next_delim == '-':
            start_id = next_id
            end_id, next_delim, nodelist = _get_next_node_id_and_delim(nodelist)
            for node_id in range(int(start_id), int(end_id) + 1):
                nodes.append("node{}".format(node_id))
            continue
        if next_delim == '':
            nodes.append("node{}".format(next_id))
            break
        if next_delim != ']':
            raise ParallelException(
                'parse_slurm_nodelist(): Unexpected character in nodelist: {}'.format(next_delim)
            )

    return nodes


def _get_next_node_id_and_delim(nodelist):
    next_int_match = re.search(r'\d+', nodelist)
    remaining_string = nodelist[next_int_match.span()[1]:]
    try:
        next_char = remaining_string[0]
    except IndexError:
        return next_int_match.group(), '', ''
    return next_int_match.group(), next_char, remaining_string
