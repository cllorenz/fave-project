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
import json
import ast
import argparse

from itertools import product

from util.aggregator_utils import FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT, FAVE_DEFAULT_UNIX
from util.aggregator_utils import connect_to_fave, fave_sendmsg
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
        for src, dst in j["links"].items():
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


def _parse_links(arg):
    to_link = lambda s, d, b: (s, d, b == 'True')
    return [to_link(*link.split(':')) for link in arg.split(',')]


def _parse_fields(arg):
    fields = {}
    for field in arg.split(';'):
        key, body = field.split('=')
        values = body.split(',')
        fields[key] = values
        if key.startswith('tcp') or key.startswith('udp'):
            fields['ip_proto'] = [key[:3]]
        elif key.startswith('icmp'):
            fields['ip_proto'] = [key[:4]]

    return fields


def _parse_probe_fields(arg):
    fields = {}
    for field in arg.split(';'):
        key, body = field.split('=')
        values = [RuleField(key, v) for v in body.split(',')]
        fields[key] = values

    return fields


def _parse_ports(arg):
    ports = []

    try:
        ports = list(range(1, int(arg)+1))
    except ValueError:
        ports = [str(i) for i in ast.literal_eval(arg)]

    return ports


def _parse_generators(arg):
    generators = []

    for generator in arg.split('|'):
        name, fields = generator.split('\\')
        generator_fields = {}
        for field in [f for f in fields.split(';') if f]:
            key, body = field.split('=')
            values = body.split(',')
            generator_fields[key] = [RuleField(key, v) for v in values]
        generators.append((name, generator_fields))

    return generators



def main(argv):
    """ Command line tool to manipulate the topology in FaVe.
    """


    topo = None

    parser = argparse.ArgumentParser(
        description="Command line too to manipulate the topology in FaVe."
    )
    parser.add_argument(
        '-a', '--add',
        dest="command",
        action='store_const',
        const='add',
        default='add',
        help="add device or links (default)"
    )
    parser.add_argument(
        '-d', '--delete',
        dest="command",
        action='store_const',
        const='del',
        default='add',
        help="delete device or links (default)"
    )
    parser.add_argument(
        '-t', '--type',
        dest="type",
        choices=[
            'switch', 'packet_filter', 'snapshot_packet_filter',
            'application_layer_gateway', 'links', 'generator', 'generators',
            'probe', 'router'
        ],
        help="apply command for a device type"
    )
    parser.add_argument(
        '-n', '--node',
        dest="node",
        help="apply command for the device with this node id"
    )
    parser.add_argument(
        '-p', '--ports',
        type=_parse_ports,
        dest="ports",
        help="add device with these ports (implies -a)"
    )
    parser.add_argument(
        '-l', '--links',
        dest="links",
        type=_parse_links,
        help="add links between port pi of device dj and port pk of device dl: d1.p1:d2.p2,d3.p3:d4.p4,..."
    )
    parser.add_argument(
        '-i', '--ip',
        dest="ip",
        help="add device with this ip address"
    )
    parser.add_argument(
        '-f', '--fields',
        dest="fields",
        type=_parse_fields,
        default={},
        help="add device with these fields f1=[v1,v2,v3,...];f2=[v4,v5,v6,...];..."
    )
    parser.add_argument(
        '-q', '--quantifier',
        dest="quantor",
        choices=['universal', 'existential'],
        help="add a quantor for a probe"
    )
    parser.add_argument(
        '-F', '--filter-fields',
        dest="filter_fields",
        type=_parse_probe_fields,
        default={},
        help="add filter fields for a probe"
    )
    parser.add_argument(
        '-G', '--generators',
        dest="generators",
        type=_parse_generators,
        default={},
        help="add list of generators of |-separated generators of the form <name/flow> where the flows follow the form of fields"
    )
    parser.add_argument(
        '-P', '--test-path',
        dest="test_path",
        type=lambda p: p.split(';'),
        default=[],
        help="add a test path for a probe"
    )
    parser.add_argument(
        '-I', '--table-ids',
        dest="table_ids",
        type=ast.literal_eval,
        help="add tables with these ids to the switch"
    )
    parser.add_argument(
        '-T', '--test-fields',
        dest="test_fields",
        type=_parse_probe_fields,
        default={},
        help="add test fields for a probe"
    )
    parser.add_argument(
        '-r', '--ruleset',
        dest="ruleset",
        help="use a router acls rule set with this filename"
    )
    parser.add_argument(
        '-s', '--suppress-interweaving',
        dest="use_interweaving",
        action='store_const',
        const=False,
        default=True,
        help="suppress the state shell interweaving for this device"
    )
    parser.add_argument(
        '-u', '--use-unix',
        dest="use_unix",
        action='store_const',
        const=True,
        default=False,
        help="use unix socket to connect to fave"
    )

    args = parser.parse_args(argv)

    if args.links: args.type = 'links'
    if args.ports: args.command = 'add'

    if args.command == 'add':
        model = {
            'switch' : lambda: SwitchModel(args.node, ports=args.ports, table_ids=args.table_ids),
            'packet_filter' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(args.ruleset),
                args.node,
                args.ip,
                args.ports,
                interweaving=args.use_interweaving
            ),
            'application_layer_gateway' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(args.ruleset),
                args.node,
                args.ip,
                args.ports,
                interweaving=args.use_interweaving
            ),
            'snapshot_packet_filter' : lambda: ip6np_generate(
                IP6TABLES_PARSER.parse(args.ruleset),
                args.node,
                args.ip,
                args.ports,
                state_snap=True
            ),
            'links' : lambda: LinksModel(args.links),
            'generator' : lambda: GeneratorModel(
                args.node,
                {f : [
                    RuleField(f, v) for v in fl
                ] for f, fl in args.fields.items()}
            ),
            'generators' : lambda: GeneratorsModel(
                [GeneratorModel(d, f) for d, f in args.generators]
            ),
            'probe' : lambda: ProbeModel(
                args.node,
                args.quantor,
                Match([RuleField(f, *v) for f, v in args.fields.items()]),
                filter_fields=args.filter_fields,
                test_fields=args.test_fields,
                test_path=args.test_path
            ),
            'router' : lambda: RouterModel(
                args.node,
                ports=args.ports,
                acls=parse_cisco_acls(args.ruleset),
                vlan_to_ports=parse_cisco_interfaces(args.ruleset)[1],
                vlan_to_acls=parse_cisco_interfaces(args.ruleset)[3],
                if_to_vlans=parse_cisco_interfaces(args.ruleset)[4],
            )}[args.type]()

        topo = TopologyCommand(args.node, args.command, model=model)

    elif args.command == 'del':
        if dtype == 'links':
            model = LinksModel(args.links)
            topo = TopologyCommand("links", args.command, model)
        else:
            topo = TopologyCommand(args.node, args.command)

    fave = connect_to_fave(
        FAVE_DEFAULT_UNIX
    ) if args.use_unix else connect_to_fave(
        FAVE_DEFAULT_IP, FAVE_DEFAULT_PORT
    )
    fave_sendmsg(fave, json.dumps(topo.to_json()))
    fave.close()


if __name__ == '__main__':
    main(sys.argv[1:])
