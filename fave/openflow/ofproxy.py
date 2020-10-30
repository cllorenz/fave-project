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

""" This module provides an openflow proxy serving as event source for FaVe.
"""

import json
import time
import asyncore
import errno
import socket
import logging

from ryu.ofproto import ofproto_parser
from ryu.ofproto import ofproto_protocol

from openflow.switch import Match, Forward, Rewrite
from openflow.switch import SwitchRule, SwitchRuleField, SwitchCommand
from util.match_util import OXM_FIELD_TO_MATCH_FIELD

LOGGER = logging.getLogger('tcp_proxy')
logging.basicConfig(level=logging.INFO)


class FixedDispatcher(asyncore.dispatcher):
    def handle_error(self):
        LOGGER.error("", exc_info=True)
        raise Exception("Error while handling data...")


class Sock(FixedDispatcher):
    write_buffer = ''


    def __init__(self, sock, pmap=None, relay=None):
        asyncore.dispatcher.__init__(self, sock, map=pmap if pmap is not None else {})
        self.relay = relay
        self.other = None


    def readable(self):
        return not self.other.write_buffer


    def writeable(self):
        return len(self.write_buffer) > 0


    def handle_read(self):
        self.other.write_buffer += self.recv(4096*4)


    def handle_write(self):
        if self.relay:
            self.relay.handle_stream(self.write_buffer)
        sent = self.send(self.write_buffer)
        self.write_buffer = self.write_buffer[sent:]


    def handle_close(self):
        LOGGER.info(' [-] %i -> %i (closed)' % \
                     (self.getsockname()[1], self.getpeername()[1]))

        self.relay.close()

        self.close()
        if self.other.other:
            self.other.close()
            self.other = None


class Server(FixedDispatcher):
    def __init__(self, dst_port, src_port=0, pmap=None, relay=None):
        self.dst_port = dst_port
        self.pmap = pmap
        self.relay = relay
        asyncore.dispatcher.__init__(self, map=self.pmap)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('localhost', src_port))
        self.src_port = self.getsockname()[1]
        LOGGER.info(' [*] Proxying %i ==> %i' % \
                     (self.src_port, self.dst_port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if not pair:
            return
        left, addr = pair
        try:
            right = socket.create_connection(('localhost', self.dst_port))
        except socket.error, err:
            if err.errno is not errno.ECONNREFUSED:
                raise
            LOGGER.info(' [!] %i -> %i ==> %i refused' % \
                         (addr[1], self.src_port, self.dst_port))
            left.close()
        else:
            LOGGER.info(' [+] %i -> %i ==> %i -> %i' % \
                         (addr[1], self.src_port,
                          right.getsockname()[1], self.dst_port))
            sock_a, sock_b = Sock(left, pmap=self.pmap, relay=self.relay), \
                  Sock(right, pmap=self.pmap, relay=self.relay)
            sock_a.other, sock_b.other = sock_b, sock_a

    def close(self):
        LOGGER.info(' [*] Closed %i ==> %i' % \
                     (self.src_port, self.dst_port))
        asyncore.dispatcher.close(self)


class OFProxy(object):
    def __init__(self, pmap=None):
        self.srv = Server(dst_port=6653, src_port=6633, pmap=pmap, relay=OFRelay())
        self.port = self.srv.src_port
        self.pmap = pmap

    def close(self):
        self.srv.close()
        self.srv = None

    def reopen(self):
        self.srv = Server(src_port=self.port, dst_port=6653, pmap=self.pmap, relay=OFRelay())

    def __str__(self):
        return 'of://localhost:%s' % (self.port, )


class Relay(object):
    def handle_stream(self, buf):
        pass

    def close(self):
        pass


def make_match(match):
    mat = match.to_jsondict()
    fields = mat['OFPMatch']['oxm_fields']
    mfields = []

    for field in fields:
        fld = field['OXMTlv']
        key = OXM_FIELD_TO_MATCH_FIELD[fld['field']]
        val = fld['value']

        mfields.append(SwitchRuleField(key, val))

    return Match(fields=mfields)


class OFRelay(Relay):
    def __init__(self):
        self.dpid = 0
        self.aggregator = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.aggregator.connect("/tmp/np_aggregator.socket")


    def handle_stream(self, buf):
        if not buf:
            return

        # get parser for openflow message
        try:
            version, msg_type, msg_len, xid = ofproto_parser.header(buf)
        except ValueError:
            return

        cls = ofproto_protocol.ProtocolDesc(version=version)
        ofp = cls.ofproto
        ofp_parser = cls.ofproto_parser


        if msg_type not in ofp_parser._MSG_PARSERS:
            return
        msg = ofp_parser.msg_parser(cls, version, msg_type, msg_len, xid, buf[:msg_len])

        if msg.msg_type == ofp.OFPT_FEATURES_REPLY:
            self.dpid = msg.datapath_id

        if msg.msg_type == ofp.OFPT_FLOW_MOD:
            match = make_match(msg.match)

            actions = []

            fwd_ports = []
            rw_ports = []

            for inst in msg.instructions:
                for action in inst.actions:
                    if isinstance(action, ofp_parser.OFPActionOutput):
                        fwd_ports.append(action.port)
                    elif isinstance(action, ofp_parser.OFPActionSetField):
                        rw_ports.append(action.port)

            if fwd_ports:
                actions.append(Forward(fwd_ports))
            if rw_ports:
                actions.append(Rewrite(rw_ports))


            node = self.dpid
            idx = msg.priority

            command = {
                ofp.OFPFC_ADD : "add_rule",
                ofp.OFPFC_DELETE : "remove_rule",
                ofp.OFPFC_MODIFY : "update_rule"
            }[msg.command]

            rule = SwitchRule(node, self.dpid, idx, match=match, actions=actions)

            model = SwitchCommand(node, command, rule)

            self.aggregator.send(json.dumps(model.to_json()))


    def close(self):
        self.aggregator.close()


if __name__ == '__main__':

    PMAP = {}
    PROXY = OFProxy(pmap=PMAP)

    asyncore.loop(map=PMAP, timeout=5.0)
    while True:
        time.sleep(1)
