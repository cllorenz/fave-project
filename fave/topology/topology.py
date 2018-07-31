""" This module provides classes for link models and topology command as well as
    a command line tool to manipulate the topology in FaVe.
"""

import sys
import getopt
import socket
import json

from util.print_util import eprint

from openflow.switch import SwitchModel
from host import HostModel
from ip6np.packet_filter import PacketFilterModel
from generator import GeneratorModel
from probe import ProbeModel


class LinksModel(object):
    """ This class provides a model to store links in FaVe.
    """

    def __init__(self, links):
        """ Creates a link model.

        Keyword arguments:
        links -- a list of pairs of origin and destination ports
        """

        self.type = 'links'
        self.links = [(p1, p2) for p1, p2 in links]


    def to_json(self):
        """ Converts the model to JSON.
        """
        return {"type" : self.type, "links" : {p1:p2 for p1, p2 in self.links}}


    @staticmethod
    def from_json(j):
        """ Creates a link model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return LinksModel(
            [(p, j["links"][p]) for p in j["links"]]
        )


    def __iter__(self):
        return self.links.__iter__()


    def __eq__(self, other):
        assert isinstance(other, LinksModel)
        return self.type == other.type and \
            len(self.links) == len(other.links) and \
            all([link in other.links for link in self.links])


class TopologyCommand(object):
    """ This class provides a structure to store commands for manipulating the
        topology in Fave.
    """

    def __init__(self, node, command, model=None, mtype=""):
        """

        Keyword arguments:
        node -- the name of the node to be manipulated
        command -- the action applied to the node (add|del)
        model -- a model to be applied (default: None)
        mtype -- the model's type
        """

        self.node = node
        self.type = "topology_command"
        self.command = command
        self.model = model
        self.mtype = mtype
        if model:
            self.mtype = model.type


    def to_json(self):
        """ Converts the command to JSON.
        """

        j = {
            "node" : self.node,
            "type" : self.type,
            "command" : self.command,
        }
        if self.model:
            j["model"] = self.model.to_json()
        if self.mtype:
            j["mtype"] = self.mtype

        return j


    @staticmethod
    def from_json(j):
        """ Constructs a command from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        model = None
        if "model" in j:
            model = {
                "switch" : SwitchModel,
                "packet_filter" : PacketFilterModel,
                "links" : LinksModel,
                "host" : HostModel,
                "generator" : GeneratorModel,
                "probe" : ProbeModel
            }[j["model"]["type"]].from_json(j["model"])

        mtype = ""
        if "mtype" in j:
            mtype = j["mtype"]

        return TopologyCommand(
            j["node"],
            j["command"],
            model=model,
            mtype=mtype
        )


    def __eq__(self, other):
        assert isinstance(other, TopologyCommand)
        return self.node == other.node and \
            self.type == other.type and \
            self.command == other.command and \
            self.model == other.model


def print_help():
    """ Prints a usage message to stderr.
    """

    eprint(
        "topology -ad [-n <id>] [-t <type>] [-p <ports>] [-l <links>]",
        "\t-a add device or links (default)",
        "\t-d delete device or links",
        "\t-t \"switch|packet_filter|links|host|generator|probe\" apply command" +
        "for a device of type <type> (default: switch)",
        "\t-n <dev> apply command for the device <dev> (default: \"\")",
        "\t-p <ports> add device with <ports> ports (implies -a)",
        "\t-l <links> add links between port pi of device dj and port pk of" +
        "device dl: d1.p1:d2.p2, d3.p3:d4.p4, ...]",
        "\t-u <uports> add device with a list of upper layer ports of the form" +
        "proto1:no1[, proto2:no2...] (implies -a)",
        "\t-i <ip> add device with ip address <ip> (host only)",
        "\t-f <fields> add device with fields f1=[v1, v2, v3, ...];f2=[v4, v5, v6...];...",
        "\t-q \"universal, existential\" add a quantor for a probe",
        "\t-F <fields> add filter fields for a probe",
        "\t-P <test_path> add a test path for a probe",
        "\t-T <fields> add test fields for a probe",
        sep="\n"
    )


def main(argv):
    """ Command line tool to manipulate the topology in FaVe.
    """

    command = "add"
    dev = ""
    dtype = ""
    ports = []
    links = []
    topo = TopologyCommand(command, dev)
    address = ""
    fields = {}
    filter_fields = {}
    test_fields = {}
    test_path = []

    try:
        opts, args = getopt.getopt(argv, "hadt:n:p:l:u:i:f:q:F:P:T:")
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit(0)
        elif opt == '-a':
            command = 'add'
        elif opt == '-d':
            command = 'del'
        elif opt == '-t':
            if arg in ['switch', 'packet_filter', 'links', 'host', 'generator', 'probe']:
                dtype = arg
            else:
                eprint("No such type: "+arg, sep="\n")
                print_help()
                sys.exit(2)
        elif opt == '-n':
            dev = arg
        elif opt == '-p':
            command = 'add'
            ports = range(1, int(arg)+1)
        elif opt == '-l':
            dtype = 'links'
            dev = 'links'
            links = [link.split(':') for link in arg.split(',')]
        elif opt == '-u':
            dtype = 'host'
            command = 'add'
            ports = [port.split(':') for port in arg.split(',')]
        elif opt == '-i':
            address = arg
        elif opt == '-f':
            fields = {}
            for field in arg.split(';'):
                key, body = field.split('=')
                values = body.split(',')
                fields[key] = values
                if key.startswith('tcp') or key.startswith('udp'):
                    fields['ip_proto'] = [key[:3]]
                elif key.startswith('icmp'):
                    fields['ip_proto'] = [key[:4]]
        elif opt == '-F':
            filter_fields = {}
            for field in arg.split(';'):
                key, body = field.split('=')
                values = body.split(',')
                filter_fields[key] = values
        elif opt == '-T':
            test_fields = {}
            for field in arg.split(';'):
                key, body = field.split('=')
                values = body.split(',')
                test_fields[key] = values
        elif opt == '-P':
            test_path = arg.split(';')

        elif opt == '-q':
            if arg in ['universal', 'existential']:
                quantor = arg
            else:
                eprint("No such quantor: "+arg, sep="\n")
                print_help()
                sys.exit(2)

    if command == 'add':
        model = {
            'switch' : lambda: SwitchModel(dev, ports=ports),
            'host' : lambda: HostModel(
                dev,
                address,
                ports=ports if ports != 0 else []
            ),
            'packet_filter' : lambda: PacketFilterModel(
                dev,
                ports=range(1, len(ports)*2+1)
            ),
            'links' : lambda: LinksModel(links),
            'generator' : lambda: GeneratorModel(dev, fields),
            'probe' : lambda: ProbeModel(
                dev,
                quantor,
                filter_expr={'filter_fields' : filter_fields},
                test_expr={'test_fields' : test_fields, 'test_path' : test_path}
            )}[dtype]()

        topo = TopologyCommand(dev, command, model=model)

    elif command == 'del':
        if dtype == 'links':
            model = LinksModel(links)
            topo = TopologyCommand("links", command, model)
        else:
            topo = TopologyCommand(dev, command)

    else:
        print_help()
        return

    aggregator = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    aggregator.connect("/tmp/np_aggregator.socket")

    aggregator.send(json.dumps(topo.to_json()))

    aggregator.close()


if __name__ == '__main__':
    main(sys.argv[1:])
