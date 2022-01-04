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

from copy import deepcopy
from functools import reduce

from src.xml.xmlutils import XMLUtils
from src.sat.satutils import SATUtils
from src.core.kripke import KripkeUtils


class Instantiator:
    _REACH = 'reach'
    _CYCLE = 'cycle'
    _SHADOW = 'shadow'
    _CROSS = 'cross'
    _KRIPKE = 'kripke'
    _BASE = 'base'
    GAMMA = 'gamma'

    DB = {}

    def Instantiate(Config,Reach=True,Cycle=False,Shadow=False,Cross=False):
        """ DEPRECATED: Reads a distributed firewall Configuration and transforms it into model checking Instances.
        """
        Kripke,Encoding = Instantiator.InstantiateBase(Config)
        Instances = {}

        if Reach:
            ReachInstances = Instantiator.InstantiateReach(Kripke,Encoding)
            for Instance in ReachInstances:
                Instances[Instance+'_'+Instantiator._REACH] = ReachInstances[Instance]

        if Cycle:
            Instances[Instantiator._CYCLE] = Instantiator.InstantiateCycle(Kripke,Encoding)

        if Shadow:
            ShadowInstances = Instantiator.InstantiateShadow(Kripke,Encoding,Instances)
            for Instance in ShadowInstances:
                Instances[Instance+'_'+Instantiator._SHADOW] = ShadowInstances[Instance]

        if Cross:
            Instances[Instantiator._CROSS] = Instantiator.InstantiateCross(Kripke,Encoding)

        return Instances


    def InstantiateBase(Config, Inits=[]):
        DB = Instantiator.DB

        Kripke = KripkeUtils.ConvertToKripke(Config)
        for Init in Inits:
            InitNode = Kripke.GetNode(Init)
            if XMLUtils.INIT not in InitNode.Props: InitNode.Props.append(XMLUtils.INIT)
            Kripke.PutInit(Init, InitNode)

        LastKripke = DB.get(Instantiator._KRIPKE)
        Diff = []
        if LastKripke is not None:
            LastKripke = LastKripke
            Diff = Kripke.Diff(LastKripke)
            DiffKripke = Kripke.SubStructure(Diff)
        else:
            Diff = list(Kripke.IterNodes())
            DiffKripke = Kripke

        if Diff:
            DB[Instantiator._KRIPKE] = Kripke

        Intersection = set(LastKripke.IterNodes()).intersection(Diff) if LastKripke is not None else set()
        for Node in Intersection:
            DB.delete(Node+'_'+Instantiator._BASE)
            DB.delete(Node+'_'+Instantiator.GAMMA)


        Encoding = Instantiator._InstantiateBase(DiffKripke)
        Complement = set(Kripke.IterNodes()).difference(Diff)
        for Node in Complement:
            Implications = DB.get(Node+'_'+Instantiator._BASE)
            Encoding[0].extend(Implications)
            Gammas = DB.get(Node+'_'+Instantiator.GAMMA)
            Encoding[0].extend(Gammas)

        Variables = Encoding.iterdescendants(XMLUtils.VARIABLE)
        Handled = {}

        for Variable in Variables:
            Instantiator._HandlePrefixes(Variable, Handled)
            Instantiator._HandlePorts(Variable, Handled)
            Instantiator._HandleVlans(Variable, Handled)
            Instantiator._HandleOthers(Variable, Handled)

        Keys = list(Handled)

        SrcKeys = [key for key in Keys if key.startswith('src_')]
        DstKeys = [key for key in Keys if key.startswith('dst_')]

        Instantiator._ShortenPrefixes(Handled,SrcKeys)
        Instantiator._ShortenPrefixes(Handled,DstKeys)

        Encoding[0].extend(list(Handled.values()))

        Encoding[0].extend(Instantiator._CreateGlobalConstraints(Kripke,Encoding))

        SATUtils.ConvertToCNF(Encoding)

        return Kripke,Encoding


    def InstantiateReach(Kripke,Encoding,Node=""):
        if Node != "":
            Instance = deepcopy(Encoding)
            try:
                BTransitions = Kripke.IterBTransitions(Node)
                Transitions = [XMLUtils.CreateTransition(Transition,Node,Flag) for Transition,Flag in BTransitions]
            except KeyError:
                if XMLUtils.INIT in Kripke.GetNode(Node).Props:
                    Transitions = [XMLUtils.constant()]
                else:
                    Transitions = [XMLUtils.unsat()]
            if len(Transitions) > 1:
                Disjunction = XMLUtils.disjunction()
                Disjunction.extend(Transitions)
            elif len(Transitions) == 1:
                if Transitions[0].tag == XMLUtils.CONSTANT:
                    Disjunction = XMLUtils.variable('a')
                else:
                    Disjunction = Transitions[0]
            else:
                Disjunction = XMLUtils.unsat()

            Conjunction = Instance[0]
            Conjunction.append(Disjunction)


            return Instance

        Instances = {}
        Nodes = Kripke.IterNodes()
        for Node in Nodes:
            Disjunction = XMLUtils.disjunction()
            try:
                BTransitions = Kripke.IterBTransitions(Node)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Node,Flag))

                if len(list(Disjunction)) == 1:
                    tmp = Disjunction[0]
                    Disjunction.remove(tmp)
                    Disjunction = tmp
            except KeyError:
                if XMLUtils.INIT in Kripke.GetNode(Node).Props:
                    Disjunction = XMLUtils.constant()
                else:
                    Disjunction = XMLUtils.unsat()

            Instance = deepcopy(Encoding)
            Conjunction = Instance[0]
            Conjunction.append(Disjunction)

            Instances[Node] = Instance

        return Instances


    def InstantiateEndToEnd(Kripke, Encoding, Source, Destination):
        Instance = deepcopy(Encoding)

        FTransitions = Kripke.IterFTransitions(Source)
        Transitions = [XMLUtils.CreateTransition(Source, Transition, Flag) for Transition, Flag in FTransitions]

        if len(Transitions) > 1:
            DisjSrc = XMLUtils.disjunction()
            DisjSrc.extend(Transitions)
        elif len(Transitions) == 1:
            if Transitions[0].tag == XMLUtils.CONSTANT:
                DisjSrc = XMLUtils.variable('a')
            else:
                DisjSrc = Transitions[0]
        else:
            DisjSrc = XMLUtils.unsat()

        BTransitions = Kripke.IterBTransitions(Destination)
        Transitions = [XMLUtils.CreateTransition(Transition, Destination, Flag) for Transition, Flag in BTransitions]

        if len(Transitions) > 1:
            DisjDst = XMLUtils.disjunction()
            DisjDst.extend(Transitions)
        elif len(Transitions) == 1:
            if Transitions[0].tag == XMLUtils.CONSTANT:
                DisjDst = XMLUtils.variable('a')
            else:
                DisjDst = Transitions[0]
        else:
            DisjDst = XMLUtils.unsat()

        Conjunction = Instance[0]
        Conjunction.append(DisjSrc)
        Conjunction.append(DisjDst)

        return Instance


    def _CreateCycle(Kripke):
        Implications = []
        FTransitions = Kripke.IterFTransitions(None)
        for Transition in FTransitions:

            Targets = Kripke.IterFTransitions(Transition)
            for Target,Flag in Targets:
                Implication = XMLUtils.disjunction()

                try:
                    NextTargets = list(Kripke.IterFTransitions(Target))
                    if len(NextTargets) > 1:
                        Disjunction = []
                        for NextTarget,NextFlag in NextTargets:
                            Disjunction.append(XMLUtils.CreateTransition(Target,NextTarget,NextFlag))
                    elif len(NextTargets) == 1:
                        NextTarget,NextFlag = NextTargets[0]
                        Disjunction = [XMLUtils.CreateTransition(Target,NextTarget,NextFlag)]
                    else:
                        Disjunction = []
                except KeyError:
                    Disjunction = []

                Implicant = XMLUtils.CreateTransition(Transition,Target,Flag)
                Implicant.attrib[XMLUtils.ATTRNEGATED] = 'true'
                if Disjunction != []:
                    Implication.append(Implicant)
                    Implication.extend(Disjunction)
                    Implications.append(Implication)
                else:
                    Implications.append(Implicant)

        return Implications


    def InstantiateCycle(Kripke,Encoding):
        Instance = deepcopy(Encoding)
        Cycle = Instantiator._CreateCycle(Kripke)
        Conjunction = Instance[0]
        Conjunction.extend(Cycle)


        Disjunction = XMLUtils.disjunction()
        Inits = Kripke.IterInits(None)
        for Init in Inits:
            FTransitions = Kripke.IterFTransitions(Init)
            for Target,Flag in FTransitions:
                Disjunction.append(XMLUtils.CreateTransition(Init,Target,Flag))

        if len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Disjunction = tmp

        Conjunction.append(Disjunction)

        return Instance


    def _GetVariables(Formula,Variables={}):
        if Formula.tag == XMLUtils.VARIABLE:
            Variables[Formula.attrib[XMLUtils.ATTRNAME]] = True
        else:
            for SubFormula in Formula:
                Instantiator._GetVariables(SubFormula,Variables)

        return Variables


    def InstantiateShadow(Kripke,Encoding,Instances={},Node=""):
        if Node != "":
            Instance = Instantiator.InstantiateReach(Kripke,Encoding,Node)
            Instance[0].append(XMLUtils.variable(Node+'_'+Instantiator.GAMMA))
            return Instance

        if not any(map(lambda x: x.endswith('_'+Instantiator._REACH),Instances)):
            ShadowInstances = Instantiator.InstantiateReach(Kripke,Encoding)
        else:
            ShadowInstances = { Instance[:len(Instance)-6] : deepcopy(Instances[Instance]) for Instance in Instances if Instance.endswith('_'+Instantiator._REACH)}

        for Instance in ShadowInstances:
            Formula = ShadowInstances[Instance]
            Formula[0].append(XMLUtils.variable(Instance+'_'+Instantiator.GAMMA))

        return ShadowInstances


    def InstantiateCross(Kripke,Encoding):
        Instance = deepcopy(Encoding)
        Conjunction = []

        Accepts = filter(lambda x: 'accept' in Kripke.GetNode(x).Props, Kripke.IterNodes())
        Drops = filter(lambda x: 'drop' in Kripke.GetNode(x).Props, Kripke.IterNodes())

        Disjunction = XMLUtils.disjunction()
        for Accept in Accepts:
            try:
                BTransitions = Kripke.IterBTransitions(Accept)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Accept,Flag))
            except KeyError:
                continue

        if len(Disjunction) > 1:
            Conjunction.append(Disjunction)
        elif len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Conjunction.append(tmp)

        Disjunction = XMLUtils.disjunction()
        for Drop in Drops:
            try:
                BTransitions = Kripke.IterBTransitions(Drop)
                for Transition,Flag in BTransitions:
                    Disjunction.append(XMLUtils.CreateTransition(Transition,Drop,Flag))
            except KeyError:
                continue

        if len(Disjunction) > 1:
            Conjunction.append(Disjunction)
        elif len(Disjunction) == 1:
            tmp = Disjunction[0]
            Disjunction.remove(tmp)
            Conjunction.append(tmp)

        Instance[0].extend(Conjunction)

        return Instance


    def _ConvertNodesToImplications(Kripke):
        Implications = []
        DB = Instantiator.DB

        FTransitions = Kripke.IterFTransitions(None)
        for NodeKey in FTransitions:
            Node = Kripke.GetNode(NodeKey)
            Targets = Kripke.IterFTransitions(NodeKey)
            NodeImplications = []
            for Target,Flag in Targets:
                Implication = XMLUtils.implication()
                Implicant = XMLUtils.CreateTransition(NodeKey,Target,Flag)
                Conclusio = XMLUtils.conjunction()
                Equality = XMLUtils.equality()
                Equality.append(XMLUtils.constant(Flag))
                Equality.append(XMLUtils.variable(NodeKey+'_'+Instantiator.GAMMA))

                try:
                    Predecessors = Kripke.IterBTransitions(NodeKey)
                    Transitions = []
                    for Predecessor,Flag in Predecessors:
                        Transition = XMLUtils.CreateTransition(Predecessor,NodeKey,Flag)
                        Transitions.append(Transition)

                    if len(Transitions) > 1:
                        Disjunction = XMLUtils.disjunction()
                        Disjunction.extend(Transitions)
                    elif len(Transitions) == 1:
                        Disjunction = Transitions[0]
                    else:
                        Disjunction = XMLUtils.constant(False)
                except KeyError:
                    if XMLUtils.INIT in Node.Props:
                        Disjunction = XMLUtils.constant()
                    else:
                        Disjunction = XMLUtils.constant(False)

                Conclusio.extend([Equality,Disjunction])
                Implication.extend([Implicant,Conclusio])

                Dummy = XMLUtils.formula()
                Conjunction = XMLUtils.conjunction()
                Dummy.append(Conjunction)
                Conjunction.append(Implication)

                SATUtils.ConvertToCNF(Dummy)
                Conjunction = Dummy[0]
                Dummy.remove(Conjunction)

                if Conjunction.tag == XMLUtils.CONJUNCTION:
                    NodeImplications.extend(list(Conjunction))
                else:
                    NodeImplications.append(Conjunction)

            DB[NodeKey+'_'+Instantiator._BASE] = NodeImplications
            Implications.extend(NodeImplications)

        return Implications


    def _CreateGlobalConstraints(Kripke,Encoding):
        Constraints = []
        Variables = Instantiator._GetVariables(Encoding)

        Constraints.extend(Instantiator._CreateBitConstraints(Variables))
        Constraints.extend(Instantiator._CreateInitConstraints(Kripke))

        return Constraints


    def _xor(Variables):
        Implications = []

        Variables = set(Variables)

        for Variable in Variables:
            Others = Variables - {Variable}

            for Other in Others:
                Implication = XMLUtils.disjunction()

                var = deepcopy(Variable)
                XMLUtils.NegateVariable(var)

                Other = deepcopy(Other)
                XMLUtils.NegateVariable(Other)

                Implication.extend([var,Other])
                Implications.append(Implication)

        return Implications


    def _CreateInitConstraints(Kripke):
        Constraints = []
        Inits = list(filter(lambda x: XMLUtils.INIT in Kripke.GetNode(x).Props,Kripke.IterNodes()))
        InitTransitions = []
        for Init in Inits:
            InitTransitions.extend(map(lambda x: (Init,) + x, Kripke.IterFTransitions(Init)))

        Length = len(InitTransitions)
        if Length > 3:
            for i in range(2,Length-3):
                if i == 2:
                    a = XMLUtils.CreateTransition(*InitTransitions[0])
                    b = XMLUtils.CreateTransition(*InitTransitions[1])
                    c = XMLUtils.variable('xor_0')
                elif i == Length-3:
                    a = XMLUtils.variable('xor_'+str(Length-2),False)
                    b = XMLUtils.CreateTransition(*InitTransitions[Length-2])
                    c = XMLUtils.CreateTransition(*InitTransitions[Length-1])
                else:
                    a = XMLUtils.variable('xor_'+str(i-2))
                    b = XMLUtils.CreateTransition(*InitTransitions[i])
                    c = XMLUtils.variable('xor_'+str(i-2),False)

                Constraints.extend(Instantiator._xor([a,b,c]))

        elif Length in [2,3]:
            Transitions = [XMLUtils.CreateTransition(*InitTransitions[i]) for i in range(Length)]
            Constraints.extend(Instantiator._xor(Transitions))

        elif Length == 1:
            Constraints.append(XMLUtils.CreateTransition(*InitTransitions[0]))

        else:
            Constraints.append(XMLUtils.unsat())

        return Constraints


    def _HandleGammas(Kripke):
        DB = Instantiator.DB
        Gammas = []
        Nodes = Kripke.IterNodes()
        for NodeKey in Nodes:
            Equality = XMLUtils.equality()
            Equality.append(XMLUtils.variable(NodeKey+'_'+Instantiator.GAMMA))
            Equality.append(deepcopy(Kripke.GetNode(NodeKey).Gamma))

            Dummy = XMLUtils.formula()
            Conjunction = XMLUtils.conjunction()
            Dummy.append(Conjunction)
            Conjunction.append(Equality)

            SATUtils.ConvertToCNF(Dummy)
            Conjunction = Dummy[0]
            Dummy.remove(Conjunction)

            if Conjunction.tag == XMLUtils.CONJUNCTION:
                Gammas.extend(list(Conjunction))
                DB[NodeKey+'_'+Instantiator.GAMMA] = Conjunction
            else:
                Gammas.append(Conjunction)
                DB[NodeKey+'_'+Instantiator.GAMMA] = Conjunction

        return Gammas


    def _CreateBitConstraints(Variables):
        Handled = {}
        Constraints = []
        for Variable in Variables:
            Varbody = Variable.rstrip('01')
            if '=' in Variable and not Varbody in Handled:
                Disjunction = XMLUtils.disjunction()
                v0 = XMLUtils.variable(Varbody + '0', False)
                v1 = XMLUtils.variable(Varbody + '1', False)
                Disjunction.extend([v0,v1])
                Constraints.append(Disjunction)
                Handled[Varbody] = True
        return Constraints

    def _InstantiateBase(Kripke):
        Encoding = XMLUtils.formula()
        Encoding.append(XMLUtils.conjunction())
        Encoding[0].extend(Instantiator._ConvertNodesToImplications(Kripke))
        Encoding[0].extend(Instantiator._HandleGammas(Kripke))

        return Encoding


    def _HandlePorts(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not Name.startswith(('dst_port_','src_port_')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Direction,tmp,Port = Name.split('_')
        Equality.append(XMLUtils.ConvertPortToVariables(Port,Direction))

        Handled[Name] = Equality


    def _HandleVlans(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not Name.startswith(('ingress_vlan_', 'egress_vlan_')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Direction,tmp,Vlan = Name.split('_')
        Equality.append(XMLUtils.ConvertVLANToVariables(Vlan,Direction))

        Handled[Name] = Equality


    def _HandleOthers(Variable, Handled):
        Name = Variable.attrib[XMLUtils.ATTRNAME]
        if Name in Handled or not any(Name.startswith(x) for x in XMLUtils.OTHERS):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib[XMLUtils.ATTRNEGATED] = 'false'
        Equality.append(var)

        Prefix,Postfix = Name.split('_')
        Functions = {
            XMLUtils.PROTO : XMLUtils.ConvertProtoToVariables,
            XMLUtils.ICMP6TYPE : XMLUtils.ConvertICMP6TypeToVariables,
            XMLUtils.ICMP6LIMIT : XMLUtils.ConvertICMP6LimitToVariables,
            XMLUtils.STATE : XMLUtils.ConvertStateToVariables,
            XMLUtils.RTTYPE : XMLUtils.ConvertRTTypeToVariables,
            XMLUtils.RTSEGSLEFT : XMLUtils.ConvertRTSegsLeftToVariables,
            XMLUtils.TCPFLAGS : XMLUtils.ConvertTCPFlagsToVariables
        }

        try:
            Equality.append(Functions[Prefix](Postfix))
        except KeyError:
            Equality.append(deepcopy(Variable))

        Handled[Name] = Equality


    def _HandlePrefixes(Variable, Handled):
        Name = Variable.attrib['name']
        if Name in Handled or not Name.startswith(('dst_ip','src_ip')):
            return

        Equality = XMLUtils.equality()
        var = deepcopy(Variable)
        var.attrib['negated'] = 'false'
        Equality.append(var)

        Direction,IPType,CIDR = Name.split('_')
        Equality.append(XMLUtils.ConvertCIDRToVariables(CIDR,Direction))

        Handled[Name] = Equality


    def _ShortenPrefixes(Handled,Keys):
        Splits = []
        Mapping = {}

        Concat = lambda x,y: x+'_'+y
        Stringify = lambda collection: reduce(Concat,map(str,collection))
        Canonize6 = lambda x: '{:016b}'.format(int(x,16))
        Canonize4 = lambda x: '{:08b}'.format(int(x,10))

        # bring addresses into canonical form and add them to mapping
        for Key in Keys:
            Addr,CIDR = Key.split('_')[-1].split('/')
            if Key[6] == '6':
                SplitAddr = Addr.split(':')
                CanonAddr = ''.join(map(Canonize6,SplitAddr))
            else:
                SplitAddr = Addr.split('.')
                CanonAddr = ''.join(map(Canonize4,SplitAddr))

            Split = (CanonAddr,int(CIDR,10))

            Splits.append(Split)
            Mapping[Stringify(Split)] = Key

        # sort addresses according to their significance
        Splits.sort(key = lambda x: x[0][:x[1]],reverse=True)

        # retrieve last element (least significant)
        if Splits != []:
            LastSplit = Splits.pop()
            LastAddr,lastCIDR = LastSplit

        while Splits != []:
            StLastSplit = Splits.pop()
            StLastAddr,StLastCIDR = StLastSplit

            # if less significant Prefix is included in more significant Prefix
            if StLastAddr[:StLastCIDR].startswith(LastAddr[:lastCIDR]):
                LastKey = Mapping[Stringify(LastSplit)]
                StLastKey = Mapping[Stringify(StLastSplit)]

                Equality = Handled[StLastKey]
                Conjunction = Equality[1]

                # remove Prefix of more significant address
                for Variable in Conjunction[:lastCIDR]:
                    Conjunction.remove(Variable)

                # and substitute with less significant address
                Conjunction.insert(0,XMLUtils.variable(LastKey))

            LastSplit,LastAddr,lastCIDR = StLastSplit,StLastAddr,StLastCIDR
