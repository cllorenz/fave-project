#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2015 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

import lxml.etree as et
from lxml import objectify


class XMLUtils:
    ADDRESS = "address"
    MASK = "mask"
    ACCEPT = "accept"
    DROP = "drop"
    INIT = "init"
    ATTRNAME = "name"
    ATTRKEY = "key"
    ATTRKEYREF = "keyref"
    ATTRTYPE = "type"
    ATTRTARGET = "target"
    ATTRNEGATED = "negated"
    ATTRVALUE = "value"
    ATTRVERSION = "version"
    ATTRDIRECTION = "direction"
    OUT = "out"
    IN = "in"
    VARIABLE = "variable"
    IF = "if"
    PORT = "port"
    JUMP = "jump"
    STATE = "state"
    FIREWALL = "firewall"
    RULE = "rule"
    NETWORK = "network"
    NODE = "node"
    TABLE = "table"
    ACTION = "action"
    INTERFACE = "interface"
    INGRESS = "ingress"
    EGRESS = "egress"
    IP = "ip"
    PROTO = "proto"
    ICMP6TYPE = "icmp6-type"
    ICMP6LIMIT = "icmp6-limit"
    RTTYPE = "rt-type"
    RTSEGSLEFT = "rt-segs-left"
    DST = "dst"
    SRC = "src"
    IPV6HEADER = "ipv6-header"
    IPV6ROUTE = "ipv6-route"
    VLAN = "vlan"
    TCPFLAGS = "tcp-flags"

    FIREWALLPATH = "/*/firewalls/"+FIREWALL
    NETWORKPATH = "/*/networks/"+NETWORK
    NODEPATH = "./"+NODE
    TABLEPATH = "./"+TABLE
    RULEPATH = "./"+RULE
    ACTIONPATH = "./"+ACTION
    INTERFACEPATH = "./"+INTERFACE
    REMOTEINTERFACEPATH = "./connections/"+INTERFACE
    IPPATH = "./"+IP
    REMOTEIPPATH = "./routes/"+IP
    PORTPATH = "./"+PORT
    PROTOPATH = "./"+PROTO
    IFPATH = "./"+IF
    STATEPATH = "./"+STATE
    ICMP6TYPEPATH = "./"+ICMP6TYPE
    ICMP6LIMITPATH = "./"+ICMP6LIMIT
    RTTYPEPATH = "./"+RTTYPE
    RTSEGSLEFTPATH = "./"+RTSEGSLEFT
    VLANPATH="./"+VLAN
    TCPFLAGSPATH="./"+TCPFLAGS
    RBODYPATHS = [
        PROTOPATH,
        IPPATH,
        PORTPATH,
        INTERFACEPATH,
        STATEPATH,
        ICMP6TYPEPATH,
        ICMP6LIMITPATH,
        RTTYPEPATH,
        RTSEGSLEFTPATH,
        VLANPATH,
        TCPFLAGSPATH
    ]

    DEFAULTINPUT = "input"
    DEFAULTOUTPUT = "output"
    DEFAULTFORWARD = "forward"
    DEFAULTTABLES = [
        DEFAULTINPUT,
        DEFAULTOUTPUT,
        DEFAULTFORWARD
    ]

    OTHERS = [
        ICMP6TYPE,
        PROTO,
        ICMP6LIMIT,
        STATE,
        RTTYPE,
        RTSEGSLEFT,
        TCPFLAGS
    ]

    NEGATION = "negation"
    CONJUNCTION = "conjunction"
    DISJUNCTION = "disjunction"
    IMPLICATION = "implication"
    EQUALITY = "equality"
    CONSTANT = "constant"
    FORMULA = "formula"

    NEW = "NEW"
    ESTABLISHED = "ESTABLISHED"
    RELATED = "RELATED"
    UNTRACKED = "UNTRACKED"

    STATES = {
        NEW : 0,
        ESTABLISHED : 1,
        RELATED : 2,
        UNTRACKED : 3
    }

    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ICMP6 = "icmp6"
    NONEXT = "nonext"
    IANA = {
        # TODO: expand to ipv6 extension header as well
        TCP : '6',
        UDP : '17',
        ICMP : '1',
        ICMP6 : '58',
        NONEXT : '59'
    }

    DSTUNREACHABLE = "destination-unreachable"
    PACKETTOOBIG = "packet-too-big"
    TIMEEXCEEDED = "time-exceeded"
    PARAMPROBLEM = "parameter-problem"
    ECHOREQUEST = "echo-request"
    ECHOREPLY = "echo-reply"
    NEIGHBORSOL = "neighbor-solicitation"
    NEIGHBORADV = "neighbor-advertisement"

    ICMP6TYPES = {
        DSTUNREACHABLE : 1,
        PACKETTOOBIG : 2,
        TIMEEXCEEDED : 3,
        PARAMPROBLEM : 4,
        ECHOREQUEST : 128,
        ECHOREPLY : 129,
        NEIGHBORSOL : 135,
        NEIGHBORADV : 136,
    }

    # TODO: test
    def deannotate(Element):
        comments = Element.xpath('//comment()')
        for comment in comments:
            comment.getparent().remove(comment)

        for Elem in Element.getiterator():
            i = Elem.tag.find('}')
            if i >= 0:
                Elem.tag = Elem.tag[i+1:]
        objectify.deannotate(Element,cleanup_namespaces=True)

    # test if two etrees are equal, TODO: test
    def equal(et1,et2):
        if et1.tag != et2.tag or et1.attrib != et2.attrib:
            return False
        if et1.text != et2.text or et1.tail != et2.tail:
            return False
        if len(et1) != len(et2):
            return False
        if any(not XMLUtils.equal(et1,et2) for et1,et2 in zip(et1,et2)):
            return False
        return True

    def pprint(Element):
        print(et.tostring(Element,pretty_print=True).decode('UTF-8'))

    def constant(value=True):
        return et.Element(XMLUtils.CONSTANT,{XMLUtils.ATTRVALUE:'true' if value else 'false'})

    def variable(Name,value=True):
        return et.Element(XMLUtils.VARIABLE,{XMLUtils.ATTRNAME:Name,XMLUtils.ATTRNEGATED:('false' if value else 'true')})

    def _BinaryOperator(tag):
        return et.Element(tag)

    def conjunction():
        return XMLUtils._BinaryOperator(XMLUtils.CONJUNCTION)

    def disjunction():
        return XMLUtils._BinaryOperator(XMLUtils.DISJUNCTION)

    def implication():
        return XMLUtils._BinaryOperator(XMLUtils.IMPLICATION)

    def equality():
        return XMLUtils._BinaryOperator(XMLUtils.EQUALITY)

    def negation():
        return et.Element(XMLUtils.NEGATION)

    def formula():
        return et.Element(XMLUtils.FORMULA)

    def unsat():
        Conjunction = XMLUtils.conjunction()
        Conjunction.extend([XMLUtils.variable('a'),XMLUtils.variable('a',False)])
        return Conjunction

    def CreateTransition(source,target,Flag=True):
        return XMLUtils.variable(source + ('_true_' if Flag else '_false_') + target)

    def NegateVariable(Var):
        Flag = Var.attrib[XMLUtils.ATTRNEGATED] == 'false'
        Var.attrib[XMLUtils.ATTRNEGATED] = 'true' if Flag else 'false'


    # canonizes ip addresses to BitVector
    def CanonizeIP(IP):
        Elem = IP
        Version = None
        try:
            Version = Elem.attrib[XMLUtils.ATTRVERSION]
        except Exception:
            print('error: no version')
            return
        if not Version in ['4','6']:
            print('error: no such version: ' + Version)
            return

        Address = Elem.find(XMLUtils.ADDRESS).text

        if Version == '4':
            try:
                Address,Mask = Address.split('/')
                return Address + '/' + Mask
            except:
                Mask = Elem.find(XMLUtils.MASK)

            AC = Address.split('.').count('*')
            if AC != 0:
                Mask = 32 - AC * 8

            Address = Address.replace('*','0')

            if not Mask:
                Mask = 32

            elif not type(Mask) is int:
                Mask = Mask.split('.')
                Mask = int(Mask[0]) << 24 + int(Mask[1]) << 16 + int(Mask[2]) << 8 + int(Mask[3])
                Tmp = 32
                while Tmp >= 0:
                    if Mask & 1:
                        break
                    Mask >>= 1
                    Tmp -= 1

                Mask = Tmp


        elif Version == '6':
            try:
                Address,Mask = Elem[0].text.split('/')
            except:
                Mask = 128

            try:
                Prefix,Postfix = Address.split('::')
            except:
                Postfix = Prefix
                Prefix = ''

            InLen = 8 - len(Prefix.split(':')) - len(Postfix.split(':'))
            Infix = ':'.join(['0' for i in range(InLen)])
            Address = Prefix + ':' + Infix + ':' + Postfix
        return Address + '/' + str(Mask)


    def CanonizePort(Port, Prefix=16):
        return XMLUtils._CanonizeBitvector(Port, 16)[:Prefix*2-1]


    def _CanonizeBitvector(Element,Length):
        Formatter = '{:0' + str(Length) + 'b}'
        return Formatter.format(int(Element)).replace('0','0 ').replace('1','1 ').rstrip()


    def CanonizeProto(Proto):
        Lookup = XMLUtils.IANA

        try:
            Code = Lookup[Proto]
        except:
            Code = Lookup[XMLUtils.NONEXT] # TODO: error handling

        return XMLUtils._CanonizeBitvector(Code,8)


    def ConvertToVariables(Config):
        XML = None

        if Config.tag == XMLUtils.PORT:
            Prefix = Config.attrib[XMLUtils.ATTRDIRECTION] + '_'+XMLUtils.PORT+'_'
            XML = XMLUtils.variable(Prefix + Config.text)

        if Config.tag == XMLUtils.VLAN:
            Prefix = Config.attrib[XMLUtils.ATTRDIRECTION] + '_'+XMLUtils.VLAN+'_'
            XML = XMLUtils.variable(Prefix + Config.text)

        elif Config.tag == XMLUtils.IP:
            CIDR = XMLUtils.CanonizeIP(Config)
            try:
                Direction = Config.attrib[XMLUtils.ATTRDIRECTION]
            except KeyError:
                Direction = XMLUtils.DST

            XML = XMLUtils.variable(Direction + '_' + XMLUtils.IP + Config.attrib[XMLUtils.ATTRVERSION] + '_' + CIDR)

        elif Config.tag == XMLUtils.IF:
            Prefix = XMLUtils.IF + '_' + Config.attrib[XMLUtils.ATTRKEYREF] + '_' + Config.attrib[XMLUtils.ATTRDIRECTION]
            XML = XMLUtils.variable(Prefix)


        elif Config.tag == XMLUtils.INTERFACE:
            Prefix = Config.attrib.get(XMLUtils.ATTRKEYREF, Config.text) + '_' + Config.attrib[XMLUtils.ATTRDIRECTION]
            XML = XMLUtils.variable(Prefix)

        elif Config.tag in [XMLUtils.PROTO,XMLUtils.ICMP6TYPE,XMLUtils.ICMP6LIMIT,XMLUtils.STATE]:
            XML = XMLUtils.variable(Config.tag + '_' + Config.text)


        elif Config.tag in [XMLUtils.RTTYPE,XMLUtils.RTSEGSLEFT]:
            XML = XMLUtils.variable(Config.tag + '_' + Config.text)
            Flag = XMLUtils.ATTRNEGATED in Config.attrib and Config.attrib[XMLUtils.ATTRNEGATED] == 'true'
            XML.attrib[XMLUtils.ATTRNEGATED] = 'true' if Flag else 'false'

        elif Config.tag in [XMLUtils.IPV6HEADER,XMLUtils.IPV6ROUTE]:
            XML = XMLUtils.variable(Config.tag)

        elif Config.tag == XMLUtils.TCPFLAGS:
            XML = XMLUtils.variable(Config.tag + '_' + Config.text)

        return XML


    def ConvertPortToVariables(Port,Direction):
        Port, Prefix = Port.split('/')
        BitVector = XMLUtils.CanonizePort(Port, Prefix=int(Prefix)).split(' ')
        XML = XMLUtils.conjunction()
        Prefix = Direction + '_'+XMLUtils.PORT+'_'
        for Index,Bit in enumerate(BitVector):
            Name = Prefix + str(Index) + '=' + Bit
            XML.append(XMLUtils.variable(Name))

        return XML


    def ConvertProtoToVariables(Proto):
        BitVector = XMLUtils.CanonizeProto(Proto).split(' ')
        XML = XMLUtils.conjunction()
        Prefix = XMLUtils.PROTO+'_'

        for Index,Bit in enumerate(BitVector):
            Name = Prefix + str(Index) + '=' + Bit
            XML.append(XMLUtils.variable(Name))

        return XML


    def ConvertCIDRToVariables(CIDR,Direction=DST):
        if CIDR.startswith((XMLUtils.DST+'_',XMLUtils.SRC+'_')):
            Direction,IPtype,CIDR = CIDR.split('_')

        Address,Count = CIDR.split('/')
        Count = int(Count)
        BitVector = ''

        if '.' in Address:
            Version = '4'
            Parts = Address.split('.')
            Size = 8
            Base = 10
        elif ':' in Address:
            Version = '6'
            Parts = Address.split(':')
            Size = 16
            Base = 16

        for Part in Parts:
            BitVector += XMLUtils._CanonizeBitvector(int(Part,Base),Size) + ' '

        BitVector = BitVector[:Count*2]
        BitVector = BitVector.replace(' ','')

        XML = XMLUtils.conjunction()
        Prefix = XMLUtils.IP + Version + '_' + Direction + '_'

        for Index,Bit in enumerate(BitVector):
            Name = Prefix + str(Index) + '=' + Bit
            XML.append(XMLUtils.variable(Name))
        return XML


    def ConvertICMP6TypeToVariables(TypeName):
        Types = ICMP6TYPES
        Prefix = XMLUtils.ICMP6TYPE+'_'
        try:
            TypeNo = Types[TypeName]
        except KeyError:
            TypeNo = 0

        BitVector = XMLUtils._CanonizeBitvector(TypeNo,16).split(' ')
        XML = XMLUtils.conjunction()

        for Index,Bit in enumerate(BitVector):
            XML.append(XMLUtils.variable(Prefix + str(Index) + '=' + Bit))

        return XML


    def ConvertICMP6LimitToVariables(Limit):
        return XMLUtils.variable(XMLUtils.ICMP6LIMIT+'_' + Limit)


    def ConvertStateToVariables(State):
        Prefix = XMLUtils.STATE+'_'

        BitVector = ['0' for _i in range(len(XMLUtils.STATES))]
        for State in State.split(','):
            BitVector[XMLUtils.STATES.get(State, 0)] = '1'

        XML = XMLUtils.conjunction()

        for Index,Bit in enumerate(BitVector):
            XML.append(XMLUtils.variable(Prefix + str(Index) + '=' + Bit))

        return XML


    def ConvertIPv6HeaderToVariables(Header):
        return XMLUtils.variable(Header)


    def ConvertIPv6RouteToVariables(Route):
        return XMLUtils.variable(Route)


    def ConvertRTTypeToVariables(Number):
        Prefix = XMLUtils.RTTYPE+'_'
        BitVector = XMLUtils._CanonizeBitvector(Number,8).split(' ')
        XML = XMLUtils.conjunction()

        for Index,Bit in enumerate(BitVector):
            XML.append(XMLUtils.variable(Prefix + str(Index) + '=' + Bit))

        return XML


    def ConvertRTSegsLeftToVariables(Number):
        Prefix = XMLUtils.RTSEGSLEFT+'_'
        BitVector = XMLUtils._CanonizeBitvector(Number,8).split(' ')
        XML = XMLUtils.conjunction()

        for Index,Bit in enumerate(BitVector):
            XML.append(XMLUtils.variable(Prefix + str(Index) + '=' + Bit))

        return XML

    def ConvertTCPFlagsToVariables(Flags):
        XML = XMLUtils.conjunction()

        for Flag in Flags.split(','):
            XML.append(XMLUtils.variable(XMLUtils.TCPFLAGS + '_' + Flag + '=1'))

        return XML

    def ConvertVLANToVariables(Vlan, Direction):
        Prefix = Direction+'_'+XMLUtils.VLAN+'_'
        BitVector = XMLUtils._CanonizeBitvector(Vlan, 12).split(' ')
        XML = XMLUtils.conjunction()

        for Index, Bit in enumerate(BitVector):
            XML.append(XMLUtils.variable(Prefix + str(Index) + '=' + Bit))

        return XML
