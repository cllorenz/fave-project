#!/usr/bin/env python3

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

""" This module provides utilities to dynamically distribute FaVe workloads over
    a cluster of NetPlumber instances.
"""

import queue
#import asyncore # XXX
import socket
import logging

NODE_LINK_QUEUE = queue.Queue()
NODE_LINK_DICT = {}

def add_node_to_dict(idx, node):
    """ Store a node for distribution.

    Arguments:
    idx -- a pair index
    node -- the node's send message
    """

    NODE_LINK_DICT.setdefault(idx, {})
    NODE_LINK_DICT[idx]['node'] = node

def add_link_to_dict(idx, link):
    """ Store a link for distribution.

    Arguments:
    idx -- a pair index
    link -- the link's send message
    """

    NODE_LINK_DICT.setdefault(idx, {})
    NODE_LINK_DICT[idx]['link'] = link

def _prepare_node_link_queue():
    for pair in list(NODE_LINK_DICT.values()):
        NODE_LINK_QUEUE.put((pair['node'], pair['link']))

def distribute_nodes_and_links():
    """ Distribute stored nodes and links dynamically.
    """

    _prepare_node_link_queue()
    for _fd, obj in list(asyncore.socket_map.items()):
        obj.send_next_pair()
    asyncore.loop()


class NodeLinkDispatcher(asyncore.dispatcher):
    """ An asyncore dispatcher that dynamically distributes nodes and links over
        a cluster of NetPlumber instances.
    """

    def __init__(self, host, port, logger=None):
        asyncore.dispatcher.__init__(self)

        if logger:
            self.debug = logger.isEnabledFor(logging.DEBUG)
            self.logger = logger
        else:
            self.debug = False
            self.logger = logging.getLogger('Dispatcher')

        socket_family = socket.AF_UNIX if port == 0 else socket.AF_INET

        self.create_socket(socket_family, socket.SOCK_STREAM)
        # Start connection process asynchronously
        # for actions after connection successful see handle_connect
        if port == 0:
            self.connect(host)
        else:
            self.connect((host, port))

        self.host = host
        self.port = port

        # Keep track of expected messages before closing the channel
        self.recv_queue = queue.Queue()

        self.raw_msg_buf = ''

    def send_next_pair(self):
        """ Sends the next node-link-pair
        """

        try:
            # Try sending a message if there are still open messages
            node_msg, link_msg = NODE_LINK_QUEUE.get_nowait()
            if self.logger.isEnabledFor(logging.DEBUG):
                debug_msg = "Sending node message: {}".format(node_msg)
                self.logger.debug(debug_msg)
            self.send((node_msg + '\n').encode('utf8'))
            if self.logger.isEnabledFor(logging.DEBUG):
                debug_msg = "Sending link message: {}".format(link_msg)
                self.logger.debug(debug_msg)
            self.send((link_msg + '\n').encode('utf8'))
            # Add "message expected" signal to recv queue
            self.recv_queue.put(node_msg)
            self.recv_queue.put(link_msg)

        except queue.Empty:
            if self.recv_queue.empty():
                if self.logger.isEnabledFor(logging.DEBUG):
                    debug_msg = "Closing send_next_pair {}".format((self.host, self.port))
                    self.logger.debug(debug_msg)
                self.close()

    def handle_read(self):
        """ Handle response messages.
        """

        results = self._recv_whole_buffer()
        if self.logger.isEnabledFor(logging.DEBUG):
            debug_msg = "Receiving ({}): {}".format((self.host, self.port), results)
            self.logger.debug(debug_msg)

        for _result in results:
            try:
                # Remove one entry for an expected message
                self.recv_queue.get_nowait()
            except queue.Empty:
                # no messages expected anymore, close the channel
                if self.logger.isEnabledFor(logging.DEBUG):
                    debug_msg = "Closing {}".format((self.host, self.port))
                    self.logger.debug(debug_msg)

        # channel still open, try sending another message
        self.send_next_pair()

    def _recv_whole_buffer(self):
        results = []
        raw = self.recv(4096)
        chunk = self.raw_msg_buf + raw.decode('utf8')
        self.raw_msg_buf = ''

        pos = chunk.rfind('\n')

        if pos == -1:
            self.raw_msg_buf = chunk
            return []

        elif pos != len(chunk) - 1:
            self.raw_msg_buf = chunk[(pos+1):]
            chunk = chunk[:pos]

        results = [m for m in chunk.split('\n') if m]

        return results
