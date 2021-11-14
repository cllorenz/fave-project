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

""" This module provides classes for link models and topology command as well as
    a command line tool to manipulate the topology in FaVe.
"""

import sys
import getopt
import json
import ast

from itertools import product

from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.aggregator_utils import connect_to_fave, fave_sendmsg
from util.print_util import eprint
from rule.rule_model import RuleField, Match

from devices.switch import SwitchModel
from devices.packet_filter import PacketFilterModel
from devices.snapshot_packet_filter import SnapshotPacketFilterModel
from devices.application_layer_gateway import ApplicationLayerGatewayModel
from devices.generator import GeneratorModel
from devices.probe import ProbeModel
from devices.router import RouterModel, parse_cisco_acls, parse_cisco_interfaces

from iptables.generator import generate as ip6np_generate
from iptables.parser_singleton import PARSER as IP6TABLES_PARSER

class LinksModel(object):
    """ This class provides a model to store links in FaVe.
    """

    def __init__(self, links):
        """ Creates a link model.

        Keyword arguments:
        links -- a list of triples of origin and destination ports as well as the bulk flag
        """

        self.type = 'links'
        self.links = [(p1, p2, bulk) for p1, p2, bulk in links]


    def to_json(self):
        """ Converts the model to JSON.
        """
        links = {}
        for src, dst, bulk in self.links:
            links.setdefault(src, [])
            links[src].append((dst, bulk))

        return {"type" : self.type, "links" : links}


    @staticmethod
    def from_json(j):
        """ Creates a links model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        links = []
        for src, dst in j["links"].iteritems():
            links.extend([(src, d, b) for d, b in dst])

        return LinksModel(links)


    def __iter__(self):
        return self.links.__iter__()


    def __eq__(self, other):
        assert isinstance(other, LinksModel)
        return \
            self.type == other.type and \
            len(self.links) == len(other.links) and \
            all([link in other.links for link in self.links])


class GeneratorsModel(object):
    """ This class provides a model to store generators in FaVe.
    """

    def __init__(self, generators):
        """ Creates a generators model.

        Keyword arguments:
        generators -- a list of generators name and generator
        """

        self.type = 'generators'
        self.generators = generators


    def to_json(self):
        """ Converts the model to JSON.
        """
        return {"type" : self.type, "generators" : [g.to_json() for g in self.generators]}


    @staticmethod
    def from_json(j):
        """ Creates a generators model from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return GeneratorsModel(
            [GeneratorModel.from_json(g) for g in j["generators"]]
        )


    def __iter__(self):
        return self.generators.__iter__()


    def __eq__(self, other):
        assert isinstance(other, GeneratorsModel)
        return self.type == other.type and \
            len(self.generators) == len(other.generators) and \
            len(self.generators) == len(
                [(g, o) for g, o in product(
                    self.generators, other.generators
                ) if g == o]
            )


class TopologyCommand(object):
    """ This class provides a structure to store commands for manipulating the
        topology in Fave.
    """

    def __init__(self, node, command, model=None, mtype=""):
        """ Constructs a command for manipulating the topology in FaVe.

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
                "snapshot_packet_filter" : SnapshotPacketFilterModel,
                "application_layer_gateway" : ApplicationLayerGatewayModel,
                "links" : LinksModel,
                "generator" : GeneratorModel,
                "generators" : GeneratorsModel,
                "probe" : ProbeModel,
                "router" : RouterModel
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
        "\t-t \"switch|packet_filter|snapshot_packet_filter|" +
        "application_layer_gateway|links|generator|generators|probe|router\" " +
        "apply command for a device of type <type>",
        "\t-n <dev> apply command for the device <dev> (default: \"\")",
        "\t-p <ports> add device with <ports> ports (implies -a)",
        "\t-l <links> add links between port pi of device dj and port pk of " +
        "device dl: d1.p1:d2.p2, d3.p3:d4.p4, ...]",
        "\t-i <ip> add device with ip address <ip>",
        "\t-f <fields> add device with fields f1=[v1, v2, v3, ...];f2=[v4, v5, v6...];...",
        "\t-q \"universal, existential\" add a quantor for a probe",
        "\t-F <fields> add filter fields for a probe",
        "\t-G <generators> add list of |-separated generators of the form " +
        "<name/flow> where the flow follow the form of fields",
        "\t-P <test_path> add a test path for a probe",
        "\t-T <fields> add test fields for a probe",
        "\t-r <ruleset> use a router acls ruleset with filename <ruleset>",
        "\t-s suppress state shell interweaving",
        sep="\n"
    )


def main(argv):
    """ Command line tool to manipulate the topology in FaVe.
    """

    command = "add"
    dev = ""
    dtype = ""
    ports = []
    table_ids = None
    links = []
    topo = TopologyCommand(command, dev)
    address = None
    fields = {}
    filter_fields = {}
    test_fields = {}
    test_path = []
    ruleset = ""
    generators = []
    use_unix = False
    use_interweaving = True

    try:
        opts, _args = getopt.getopt(argv, "hadn:p:l:ui:I:f:q:F:G:P:t:T:r:s")
    except getopt.GetoptError:
        eprint("cannot parse arguments: %s" % argv)
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
        elif opt == '-u':
            use_unix = True
        elif opt == '-t':
            if arg in [
                    'switch',
                    'packet_filter',
                    'snapshot_packet_filter',
                    'application_layer_gateway',
                    'links',
                    'generator',
                    'generators',
                    'probe',
                    'router'
            ]:
                dtype = arg
            else:
                eprint("No such type: "+arg, sep="\n")
                print_help()
                sys.exit(2)
        elif opt == '-n':
            dev = arg
        elif opt == '-p':
            command = 'add'
            try:
                ports = range(1, int(arg)+1)
            except ValueError:
                ports = [str(i) for i in ast.literal_eval(arg)]
        elif opt == '-l':
            dtype = 'links'
            dev = 'links'
            to_link = lambda s, d, b: (s, d, b == 'True')
            links = [to_link(*link.split(':')) for link in arg.split(',')]
        elif opt == '-i':
            address = arg
        elif opt == '-I':
            table_ids = ast.literal_eval(arg)
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
                values = [RuleField(key, v) for v in body.split(',')]
                filter_fields[key] = values
        elif opt == '-G':
            for generator in arg.split('|'):
                name, fields = generator.split('\\')
                generator_fields = {}
                for field in [f for f in fields.split(';') if f]:
                    key, body = field.split('=')
                    values = body.split(',')
                    generator_fields[key] = [RuleField(key, v) for v in values]
                generators.append((name, generator_fields))
        elif opt == '-T':
            test_fields = {}
            for field in arg.split(';'):
                key, body = field.split('=')
                values = [RuleField(key, v) for v in body.split(',')]
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

        elif opt == '-r':
            ruleset = arg

        elif opt == '-s':
            use_interweaving = False

    if command == 'add':
        model = {
            'switch' : lambda: SwitchModel(dev, ports=ports, table_ids=table_ids),
            'packet_filter' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(ruleset),
                dev,
                address,
                ports,
                interweaving=use_interweaving
            ),
            'application_layer_gateway' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(ruleset),
                dev,
                address,
                ports,
                interweaving=use_interweaving
            ),
            'snapshot_packet_filter' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(ruleset),
                dev,
                address,
                ports,
                state_snap=True
            ),
            'links' : lambda: LinksModel(links),
            'generator' : lambda: GeneratorModel(
                dev,
                {f : [
                    RuleField(f, v) for v in fl
                ] for f, fl in fields.iteritems()}
            ),
            'generators' : lambda: GeneratorsModel(
                [GeneratorModel(d, f) for d, f in generators]
            ),
            'probe' : lambda: ProbeModel(
                dev,
                quantor,
                Match([RuleField(f, *v) for f, v in fields.iteritems()]),
                filter_fields=filter_fields,
                test_fields=test_fields,
                test_path=test_path
            ),
            'router' : lambda: RouterModel(
                dev,
                ports=ports,
                acls=parse_cisco_acls(ruleset),
                vlan_to_ports=parse_cisco_interfaces(ruleset)[1],
                vlan_to_acls=parse_cisco_interfaces(ruleset)[3],
                if_to_vlans=parse_cisco_interfaces(ruleset)[4],
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

    fave = connect_to_fave(
        FAVE_DEFAULT_UNIX
    ) if use_unix else connect_to_fave(
        FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
    )
    topo_str = json.dumps(topo.to_json())
    fave_sendmsg(fave, topo_str)
    fave.close()


if __name__ == '__main__':
    main(sys.argv[1:])
