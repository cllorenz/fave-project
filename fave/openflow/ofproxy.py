
import json

import asyncore
import errno
import os
import socket
import logging
import threading

from ryu.lib import dpid as dpid_lib
from ryu.ofproto import ofproto_parser
from ryu.ofproto import ofproto_v1_0
from ryu.ofproto import ofproto_v1_0_parser
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ofproto_v1_3_parser
from ryu.ofproto import ofproto_protocol

from netplumber.vector import Vector

from openflow.switch import Match,SwitchRule,SwitchRuleField,SwitchCommand,Forward,Rewrite
from util.match_util import oxm_field_to_match_field

log = logging.getLogger('tcp_proxy')
logging.basicConfig(level=logging.INFO)


class FixedDispatcher(asyncore.dispatcher):
    def handle_error(self):
        log.error("",exc_info=True)
        raise


class Sock(FixedDispatcher):
    write_buffer = ''

    def __init__(self,sock,map={},relay=None):
        asyncore.dispatcher.__init__(self,sock,map=map)
        self.relay = relay

    def readable(self):
        return not self.other.write_buffer

    def writeable(self):
        return (len(self.write_buffer) > 0)

    def handle_read(self):
        self.other.write_buffer += self.recv(4096*4)

    def handle_write(self):
        if self.relay:
            self.relay.handle_stream(self.write_buffer)
        sent = self.send(self.write_buffer)
        self.write_buffer = self.write_buffer[sent:]

    def handle_close(self):
        log.info(' [-] %i -> %i (closed)' % \
                     (self.getsockname()[1], self.getpeername()[1]))

        self.relay.close()

        self.close()
        if self.other.other:
            self.other.close()
            self.other = None


class Server(FixedDispatcher):
    def __init__(self, dst_port, src_port=0, map=None,relay=None):
        self.dst_port = dst_port
        self.map = map
        self.relay = relay
        asyncore.dispatcher.__init__(self, map=self.map)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('localhost', src_port))
        self.src_port = self.getsockname()[1]
        log.info(' [*] Proxying %i ==> %i' % \
                     (self.src_port, self.dst_port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if not pair:
            return
        left, addr = pair
        try:
            right = socket.create_connection(('localhost', self.dst_port))
        except socket.error, e:
            if e.errno is not errno.ECONNREFUSED: raise
            log.info(' [!] %i -> %i ==> %i refused' % \
                         (addr[1], self.src_port, self.dst_port))
            left.close()
        else:
            log.info(' [+] %i -> %i ==> %i -> %i' % \
                         (addr[1], self.src_port,
                          right.getsockname()[1], self.dst_port))
            a,b = Sock(left, map=self.map, relay=self.relay), \
                  Sock(right, map=self.map, relay=self.relay)
            a.other, b.other = b, a

    def close(self):
        log.info(' [*] Closed %i ==> %i' % \
                     (self.src_port, self.dst_port))
        asyncore.dispatcher.close(self)


class OFProxy(object):
    def __init__(self,map=None):
        self.srv = Server(dst_port=6653,src_port=6633,map=map,relay=OFRelay())
        self.port = self.srv.src_port
        self.map = map

    def close(self):
        self.srv.close()
        self.srv = None

    def reopen(self):
        self.srv = Server(src_port=self.port, dst_port=6653, map=self.map,relay=OFRelay())

    def __str__(self):
        return 'of://localhost:%s' % (self.port,)


class Relay(object):
    def handle_stream(self,buf):
        pass

    def close(self):
        pass


def make_match(match):
    m = match.to_jsondict()
    fields = m['OFPMatch']['oxm_fields']
    mf = []

    for field in fields:
        f = field['OXMTlv']
        k = oxm_field_to_match_field[f['field']]
        v = f['value']

        mf.append(SwitchRuleField(k,v))

    return Match(fields=mf)


class OFRelay(Relay):
    def __init__(self):
        self.dpid = 0
        self.aggregator = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.aggregator.connect("/tmp/np_aggregator.socket")


    def handle_stream(self,buf):
        if not buf:
            return

        # get parser for openflow message
        try:
            (version, msg_type, msg_len, xid) = ofproto_parser.header(buf)
        except:
            return

        cls = ofproto_protocol.ProtocolDesc(version=version)
        ofp = cls.ofproto
        ofp_parser = cls.ofproto_parser


        if not msg_type in ofp_parser._MSG_PARSERS:
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
                    if type(action) == ofp_parser.OFPActionOutput:
                        fwd_ports.append(action.port)
                    elif type(action) == ofp_parser.OFPActionSetField:
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

            rule = SwitchRule(node,idx,match=match,actions=actions)

            model = SwitchCommand(node,command,rule)

            self.aggregator.send(json.dumps(model.to_json()))


    def close(self):
        self.aggregator.close()


if __name__ == '__main__':
    import time

    map = {}

    proxy = OFProxy(map=map)
    asyncore.loop(map=map,timeout=5.0)
    while True:
        time.sleep(1)
