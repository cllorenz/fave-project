""" This module provides a combination of a flow generator and a probe to
    represent a host.
"""

import json

from util.packet_util import ETHER_TYPE_IPV6
from util.packet_util import normalize_ipv6_address, normalize_ipv6_proto
#from util.packet_util import normalize_upper_port
from netplumber.mapping import Mapping
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
#from ip6np.generator import field_value_to_bitvector
#from ip6np.packet_filter import Field

class HostModel(object):
    """ This class combines a flow generator and a probe to represent a host.
    """

    def __init__(self, node, address, ports=None):
        self.node = node
        self.type = "host"
        self.address = address
        self.uports = ports if ports is not None else []
        self.ports = {node+'_1' : 1}

        #incoming = []
        outgoing = []

        self.mapping = Mapping()
        self.mapping.extend('packet.ether.type')
        #self.mapping.extend('packet.ipv6.source')
        self.mapping.extend('packet.ipv6.destination')
        self.mapping.extend('packet.ipv6.proto')
        #self.mapping.extend('packet.upper.sport')
        self.mapping.extend('packet.upper.dport')

        for proto, portno in ports:
            #vin = Vector(self.mapping.length)
            #set_field_in_vector(
            #    self.mapping,
            #    vin,
            #    'packet.ether.type',
            #    ETHER_TYPE_IPV6
            #)
            #set_field_in_vector(
            #    self.mapping,
            #    vin,
            #    'packet.ipv6.destination',
            #    normalize_ipv6_address(address)
            #)
            #set_field_in_vector(
            #    self.mapping,
            #    vin,
            #    'packet.upper.dport',
            #    normalize_upper_port(int(no))
            #)
            #set_field_in_vector(
            #    self.mapping,
            #    vin,
            #    'packet.ipv6.proto',
            #    normalize_ipv6_proto(proto)
            #)

            vout = Vector(self.mapping.length)
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.ether.type',
                ETHER_TYPE_IPV6
            )
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.ipv6.destination', #'packet.ipv6.source',
                normalize_ipv6_address(address)
            )
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.upper.dport', #'packet.upper.sport',
                '{:016b}'.format(int(portno))
            )
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.ipv6.proto',
                normalize_ipv6_proto(proto)
            )

            #incoming.append(vin)
            outgoing.append(vout)

        #if incoming == []:
        #    vin = Vector(self.mapping.length)
        #    set_field_in_vector(
        #        self.mapping,
        #        vin,
        #        'packet.ether.type',
        #        ETHER_TYPE_IPV6
        #    )
        #    set_field_in_vector(
        #        self.mapping,
        #        vin,
        #        'packet.ipv6.destination',
        #        normalize_ipv6_address(address)
        #    )
        #    incoming.append(vin)

        if outgoing == []:
            vout = Vector(self.mapping.length)
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.ether.type',
                ETHER_TYPE_IPV6
            )
            set_field_in_vector(
                self.mapping,
                vout,
                'packet.ipv6.destination', #'packet.ipv6.source',
                normalize_ipv6_address(address)
            )
            outgoing.append(vout)

        #self.incoming = HeaderSpace(self.mapping.length,incoming)
        self.outgoing = HeaderSpace(self.mapping.length, outgoing)


    def to_json(self):
        """ Converts the host to JSON.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "address" : self.address,
            "mapping" : self.mapping.to_json(),
            #"incoming" : self.incoming.to_json(),
            "outgoing" : self.outgoing.to_json()
        }


    @staticmethod
    def from_json(j):
        """ Constructs host from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        model = HostModel(
            j["node"],
            j["address"]
        )
        model.mapping = Mapping.from_json(j["mapping"])
        #model.incoming = HeaderSpace.from_json(j["incoming"])
        model.outgoing = HeaderSpace.from_json(j["outgoing"])

        return model
