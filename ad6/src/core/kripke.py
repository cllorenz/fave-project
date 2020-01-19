from src.xml.xmlutils import XMLUtils
from src.core.structure import *

class KripkeUtils:
    def ConvertToKripke(Config):
        Kripke = KripkeUtils._GetTransitions(Config)
        KripkeUtils._RedirectInputs(Kripke)
        KripkeUtils._ConnectOutputs(Kripke)
        return Kripke


    def _GetTransitions(Config):
        Kripke = KripkeStructure({},{},{},{})
        IfRules = []

        Firewalls = Config.xpath(XMLUtils.FIREWALLPATH)
        for Firewall in Firewalls:
            KripkeUtils._HandleFirewall(Kripke,IfRules,Firewall)

        Networks = Config.xpath(XMLUtils.NETWORKPATH)
        for Network in Networks:
            KripkeUtils._HandleNetwork(Kripke,Network)

        KripkeUtils._EnhanceInterfaceRules(IfRules,Kripke)

        return Kripke


    def _HandleFirewall(Kripke,IfRules,Firewall):
        FwKey = Firewall.attrib[XMLUtils.ATTRKEY]

        Tables = Firewall.xpath(XMLUtils.TABLEPATH)
        for Table in Tables:
            KripkeUtils._HandleTable(Kripke,IfRules,Table,FwKey)


    def _HandleTable(Kripke,IfRules,Table,FwKey):
        TKey = FwKey + '_' + Table.attrib[XMLUtils.ATTRNAME]

        Rules = Table.xpath(XMLUtils.RULEPATH)
        for Index,Rule in enumerate(Rules):
            KripkeUtils._HandleRule(Kripke,IfRules,Index,Rule,Table,TKey)


    def _HandleRule(Kripke,IfRules,Index,Rule,Table,TKey):
        RKey = TKey + '_r' + str(Index)
        Node = KripkeNode(Props=[RKey],Gamma=None)
        Kripke.Put(RKey,Node)

        if XMLUtils.ACCEPT in RKey:
            Node.Props.append(XMLUtils.ACCEPT)
        if XMLUtils.DROP in RKey:
            Node.Props.append(XMLUtils.DROP)

        RuleFilter = lambda x: x in RKey
        TableStarts = [Table + '_r0' for Table in XMLUtils.DEFAULTTABLES]
        if any(map(RuleFilter,TableStarts)):
            Labels = RKey.split('_')
            Node.Props.append(Labels[len(Labels)-2])
        if XMLUtils.DEFAULTOUTPUT+'_r0' in RKey:
            Node.Props.append(XMLUtils.INIT)
            Kripke.PutInit(RKey,Node)


        Gamma = Rule.xpath('|'.join(XMLUtils.RBODYPATHS))
        if not Gamma:
            Node.Gamma = XMLUtils.constant()
        elif len(Gamma) == 1:
            if Gamma[0].tag == XMLUtils.IF:
                IfRules.append(Node)
            Node.Gamma = XMLUtils.ConvertToVariables(Gamma[0])
        else:
            if any(x.tag == XMLUtils.IF for x in Gamma):
                IfRules.append(Node)

            PortFilter = lambda x: x.tag == XMLUtils.PORT
            Ports = list(filter(PortFilter,Gamma))
            PortList = []
            for Port in Ports:
                Gamma.remove(Port)
                PortList.append(Port)

            if len(PortList) == 1:
                Ports = XMLUtils.ConvertToVariables(PortList[0])
            elif len(PortList) > 1:
                Ports = XMLUtils.disjunction()
                Ports.extend(list(map(XMLUtils.ConvertToVariables,PortList)))

            StateFilter = lambda x: x.tag == XMLUtils.STATE
            States = list(filter(StateFilter,Gamma))
            StateList = []
            for State in States:
                Gamma.remove(State)
                StateList.append(State)
            if len(StateList) == 1:
                States = XMLUtils.ConvertToVariables(StateList[0])
            elif len(StateList) > 1:
                States = XMLUtils.disjunction()
                States.extend(map(XMLUtils.ConvertToVariables,StateList))

            Gamma = list(map(XMLUtils.ConvertToVariables,Gamma))
            Node.Gamma = XMLUtils.conjunction()
            Node.Gamma.extend(Gamma)
            if PortList:
                Node.Gamma.append(Ports)
            if StateList:
                Node.Gamma.append(States)


        # true Transition
        Action = Rule.xpath(XMLUtils.ACTIONPATH)[0]
        if Action.attrib[XMLUtils.ATTRTYPE] == XMLUtils.JUMP:
            Target = Action.attrib[XMLUtils.ATTRTARGET]
            Kripke.Put(RKey,(Target,True))

        # false Transition
        Target = TKey + '_r' + str(Index+1)
        if Table.xpath('./'+XMLUtils.RULE+'[@'+XMLUtils.ATTRNAME+'="r' + str(Index+1) + '"]'):
            Kripke.Put(RKey,(Target,False))


    def _HandleNetwork(Kripke,Network):
        NetKey = Network.attrib[XMLUtils.ATTRNAME]

        NetNodes = Network.xpath(XMLUtils.NODEPATH)
        for Node in NetNodes:
            KripkeUtils._HandleNode(Kripke,Node,NetKey)


    def _HandleNode(Kripke,Node,NetKey):
        Nodekey = NetKey + '_' + Node.attrib[XMLUtils.ATTRNAME]

        FwKey = Node.xpath(XMLUtils.FIREWALL)[0].attrib[XMLUtils.ATTRKEYREF]

        Interfaces = Node.xpath(XMLUtils.INTERFACEPATH)
        for Interface in Interfaces:
            KripkeUtils._HandleInterface(Kripke,Interface,FwKey,Node,Nodekey)


    def _HandleInterface(Kripke,Interface,FwKey,Node,Nodekey):
        IFaceKey = Nodekey + '_' + Interface.attrib[XMLUtils.ATTRNAME]

        InNode = KripkeNode(Props=[IFaceKey+'_'+XMLUtils.IN],Gamma=None)
        Kripke.Put(IFaceKey+'_'+XMLUtils.IN,InNode)
        InNode.Gamma = XMLUtils.constant()

        OutNode = KripkeNode(Props=[IFaceKey+'_'+XMLUtils.OUT],Gamma=None)
        Kripke.Put(IFaceKey+'_'+XMLUtils.OUT,OutNode)
        ROutes = Interface.xpath(XMLUtils.REMOTEIPPATH)
        if ROutes:
            IPs = []
            for ROute in ROutes:
                KripkeUtils._HandleROute(ROute,IPs)

            if len(IPs) > 1:
                Disjunction = XMLUtils.disjunction()
                Disjunction.extend(IPs)
                OutNode.Gamma = Disjunction
            elif len(IPs) == 1:
                OutNode.Gamma = IPs[0]
            else:
                OutNode.Gamma = XMLUtils.constant()

        else:
            OutNode.Gamma = XMLUtils.constant()

        IP = Node.xpath(XMLUtils.IPPATH)
        if IP:
            Kripke.GetNode(IFaceKey+'_'+XMLUtils.IN).Gamma = XMLUtils.ConvertToVariables(IP[0])

        InKey = FwKey+'_'+XMLUtils.DEFAULTINPUT+'_r0'
        Nodes = list(Kripke.IterNodes())
        if InKey in Nodes:
            Kripke.Put(IFaceKey+'_'+XMLUtils.IN,(InKey,True))

        FwdKey = FwKey+'_'+XMLUtils.DEFAULTFORWARD+'_r0'
        if FwdKey in Nodes:
            Flag = not Node.xpath(XMLUtils.IPPATH)
            Kripke.Put(IFaceKey+'_'+XMLUtils.IN,(FwdKey,Flag))

        Connections = Interface.xpath(XMLUtils.REMOTEINTERFACEPATH)
        for Connection in Connections:
            ConKey = Connection.attrib[XMLUtils.ATTRKEYREF]

            Kripke.Put(IFaceKey+'_'+XMLUtils.OUT,(ConKey+'_'+XMLUtils.IN,True))
            Kripke.Put(ConKey+'_'+XMLUtils.OUT,(IFaceKey+'_'+XMLUtils.IN,True))


    def _HandleROute(ROute,IPs):
        IP = XMLUtils.ConvertToVariables(ROute)
        try:
            Flag = ROute.attrib[XMLUtils.ATTRNEGATED] == 'false'
        except KeyError:
            Flag = True

        if not Flag:
            XMLUtils.NegateVariable(IP)
        IPs.append(IP)


    def _EnhanceInterfaceRules(Rules,Kripke):
        for Rule in Rules:
            if Rule.Gamma.tag == XMLUtils.VARIABLE:
                Transitions = []
                FKey = Rule.Gamma.attrib[XMLUtils.ATTRNAME][3:]
                try:
                    BTransitions = Kripke.IterBTransitions(FKey)
                except KeyError:
                    Rule.Gamma = XMLUtils.constant(False)
                    continue
                for Key,Flag in BTransitions:
                    Transitions.append(XMLUtils.CreateTransition(Key,FKey,Flag))
                if len(Transitions) == 1:
                    Rule.Gamma = Transitions[0]
                else:
                    Rule.Gamma = XMLUtils.disjunction()
                    Rule.Gamma.extend(Transitions)
            else:
                Transitions = []
                Parent = Rule.Gamma
                TermFilter = lambda x: x.tag == XMLUtils.VARIABLE and x.attrib[XMLUtils.ATTRNAME].startswith(XMLUtils.IF+'_')
                Terms = [Term for Term in Parent if TermFilter(Term)]
                for Term in Terms:
                    Transitions = []
                    FKey = Term.attrib[XMLUtils.ATTRNAME][3:]
                    try:
                        BTransitions = Kripke.IterBTransitions(FKey)
                    except KeyError:
                        Parent.replace(Term,XMLUtils.constant(False))
                        continue
                    for Key,Flag in BTransitions:
                        Transitions.append(XMLUtils.CreateTransition(Key,FKey,Flag))
                    if len(Transitions) == 1:
                        Parent.replace(Term,Transitions[0])
                    else:
                        tmp = XMLUtils.disjunction()
                        tmp.extend(Transitions)
                        Parent.replace(Term,tmp)


    def _ConnectOutputs(Kripke):
        Outs = KripkeUtils._GetOutputs(Kripke)
        for Out in Outs:
            Nodekey = '_'.join(Out.split('_')[:2])
            OutFilter = lambda x: x.startswith(Nodekey) and x.endswith('_'+XMLUtils.OUT)
            for Out in Outs[Out]:
                Interfaces = filter(OutFilter,Kripke.IterNodes())
                for Interface in Interfaces:
                    Kripke.Put(Out,(Interface,True))
                    try:
                        Kripke.GetNode(Out).Props.remove(XMLUtils.ACCEPT)
                    except ValueError:
                        pass


    def _GetOutputsRecurse(Nodekey,Kripke,Visited={}):
        Node = Kripke.GetNode(Nodekey)

        if XMLUtils.ACCEPT in Node.Props:
            Node.Props.append(XMLUtils.OUT)
            return [Nodekey]
        elif Nodekey in Visited:
            return []
        else:
            Visited[Nodekey] = True
            Result = []
            try:
                Transitions = Kripke.IterFTransitions(Nodekey)
            except KeyError:
                Transitions = []
            for Target,Flag in Transitions:
                Result.extend(KripkeUtils._GetOutputsRecurse(Target,Kripke,Visited))
            return Result


    def _GetOutputs(Kripke):
        Outs = {}
        Inits = Kripke.IterNodes()
        for Init in Inits:
            Props = Kripke.GetNode(Init).Props
            if XMLUtils.DEFAULTFORWARD in Props or XMLUtils.DEFAULTOUTPUT in Props:
                Outs[Init] = KripkeUtils._GetOutputsRecurse(Init,Kripke,{})
        return Outs


    def _GetAcceptsRecurse(Node,Kripke,Visited={}):
        Nodekey = Node
        Node = Kripke.GetNode(Node)
        if XMLUtils.ACCEPT in Node.Props:
            return [],True
        elif Nodekey in Visited:
            return [],False
        else:
            Visited[Nodekey] = True
            Result = []
            try:
                Transitions = Kripke.IterFTransitions(Nodekey)
            except KeyError:
                Transitions = []
            for Target,Flag in Transitions:
                Tmp, TmpFlag = KripkeUtils._GetAcceptsRecurse(Target,Kripke,Visited)
                Result.extend(Tmp)
                if TmpFlag:
                    Result.append((Nodekey,Target,Flag))
            return Result, False


    def _GetInputAccepts(Kripke):
        ATransitions = {}
        Inits = Kripke.IterNodes()
        for Init in Inits:
            Props = Kripke.GetNode(Init).Props
            if XMLUtils.DEFAULTINPUT in Props:
                ATransitions[Init],Flag = KripkeUtils._GetAcceptsRecurse(Init,Kripke,{})
        return ATransitions


    def _RedirectInputs(Kripke):
        ATransitions = KripkeUtils._GetInputAccepts(Kripke)
        for Node in ATransitions:
            Nodekey = Node+'_'+XMLUtils.ACCEPT
            Kripke.Put(Nodekey,KripkeNode(Props=[Nodekey,XMLUtils.ACCEPT],Gamma=XMLUtils.constant()))
            Transitions = ATransitions[Node]
            for Key,FKey,Flag in Transitions:
                Kripke.Remove(Key,(FKey,Flag))
                Props = Kripke.GetNode(Key).Props
                if XMLUtils.ACCEPT in Props:
                    Props.remove(XMLUtils.ACCEPT)

                Kripke.Put(Key,(Nodekey,Flag))