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

from src.xml.xmlutils import XMLUtils
import lxml.etree as et
import ast
from pprint import pprint

class KripkeNode:
    def __init__(self,Props=[], Gamma=None, Desc=None, RawRuleNo=None):
        self.Props = Props
        self.Gamma = Gamma
        self.Desc = Desc
        self.RawRuleNo = RawRuleNo


    def tostring(self):
        return str(self)


    def totuple(self):
        Gamma = et.tostring(self.Gamma, encoding='unicode', pretty_print=False) if self.Gamma is not None else []
        return (self.Props, Gamma)

    def __str__(self):
        Gamma = et.tostring(self.Gamma, encoding='unicode', pretty_print=False) if self.Gamma is not None else []
        return "(%s, %s)" % (self.Props, Gamma)


    def fromstring(NodeStr):
        Props,Gamma = ast.literal_eval(NodeStr)
        Gamma = et.fromstring(Gamma)
        return KripkeNode(Props,Gamma)


    def __eq__(self,Other):
        try:
            return self.Props == Other.Props and XMLUtils.equal(self.Gamma,Other.Gamma)
        except RuntimeError:
            return False


class KripkeStructure:
    NODES = "nodes"
    FTRANSITIONS = "ftrans"
    BTRANSITIONS = "btrans"
    INITS = "inits"

    def __init__(self,Nodes={},FTransitions={},BTransitions={},Inits={}):
        self._Nodes = Nodes
        self._FTransitions = FTransitions
        self._BTransitions = BTransitions
        self._Inits = Inits


    def __str__(self):
        return "Nodes: %s\n\nforward Transitions: %s\n\nback Transitions: %s\n\nInits: %s" % (
            self._Nodes, self._FTransitions, self._BTransitions, self._Inits
        )


    def tostring(self):
        Nodes = { Node:self._Nodes[Node].tostring() for Node in self._Nodes }
        Inits = { Node:self._Inits[Node].tostring() for Node in self._Inits }

        return str([Nodes,self._FTransitions,self._BTransitions,Inits])


    def fromstring(StructureStr):
        Nodes,FTransitions,BTransitions,Inits = ast.literal_eval(StructureStr)

        for Node in Nodes:
            Nodes[Node] = KripkeNode.fromstring(Nodes[Node])

        return KripkeStructure(Nodes,FTransitions,BTransitions,Inits)


    def pprint(self,Element=NODES):
        if Element == KripkeStructure.FTRANSITIONS:
            pprint(self._FTransitions)
        elif Element == KripkeStructure.BTRANSITIONS:
            pprint(self._BTransitions)
        elif Element == KripkeStructure.INITS:
            pprint({Name : Node.totuple() for Name, Node in self._Inits.items()})
        else:
            pprint({Name : Node.totuple() for Name, Node in self._Nodes.items()})


    def GetNode(self,Key):
        return self._Nodes[Key]


    def _AppendTransition(self,Target,Key,Element):
        try:
            if not Element in Target[Key]:
                Target[Key].append(Element)
        except KeyError:
            Target[Key] = [Element]


    def PutInit(self,Key,Element):
        self._Inits[Key] = Element


    def Put(self,Key,Element):
        if isinstance(Element,tuple):
            FKey,Flag = Element
            self._AppendTransition(self._FTransitions,Key,Element)
            self._AppendTransition(self._BTransitions,FKey,(Key,Flag))
        elif isinstance(Element,KripkeNode):
            self._Nodes[Key] = Element


    def Remove(self,Key,Element=None):
        if Key is not None:
            if Element is None:
                if self._Nodes[Key]:
                    del self._Nodes[Key]
                if self._FTransitions[Key]:
                    del self._FTransitions[Key]
                if self._BTransitions[Key]:
                    del self._BTransitions[Key]
                if self._Inits[Key]:
                    del self._Inits[Key]

            elif isinstance(Element,str):
                FilterTransitions = lambda x: x[0] == Element
                try:
                    Transitions = filter(FilterTransitions,self._FTransitions[Key])
                except KeyError:
                    Transitions = []
                for Transition in Transitions:
                    self._FTransitions[Key].remove(Transition)
                try:
                    Transitions = filter(FilterTransitions,self._BTransitions[Key])
                except KeyError:
                    Transitions = []
                for Transition in Transitions:
                    self._BTransitions[Key].remove(Transition)

            elif isinstance(Element,tuple):
                FKey,Flag = Element
                try:
                    self._FTransitions[Key].remove(Element)
                except KeyError:
                    pass
                try:
                    self._BTransitions[FKey].remove((Key,Flag))
                except KeyError:
                    pass

            elif isinstance(Element,KripkeNode):
                self.remove(KripkeNode.Props[0])


    def _TraverseRecursion(self,Node,FilterStr,Visited={}):
        if Node in Visited:
            return []
        elif FilterStr is not None and FilterStr in self._Nodes[Node].Props:
            return [Node]
        else:
            Result = []
            Visited[Node] = True
            try:
                Transitions = self._FTransitions[Node]
            except KeyError:
                Transitions = []
            for Transition,Flag in Transitions:
                Result.extend(self._tranverseRecursion(Transition,FilterStr,Visited))
            return Result


    def TraverseStructure(self,start,FilterStr=None):
        return self._TraverseRecursion(start,FilterStr,{})


    def _IterDict(self,Target,Key=None):
        if Key is None:
            return iter(Target)
        elif Key in Target:
            return iter(Target[Key])
        else:
            return []


    def IterNodes(self):
        return self._IterDict(self._Nodes)


    def IterFTransitions(self,Key=None):
        return self._IterDict(self._FTransitions,Key)


    def IterBTransitions(self,Key=None):
        return self._IterDict(self._BTransitions,Key)


    def IterInits(self,Key=None):
        return self._IterDict(self._Inits, Key)


    def Sort(self):
        for Node in self._FTransitions:
            self._FTransitions[Node].sort()
        for Node in self._BTransitions:
            self._BTransitions[Node].sort()


    def Diff(self,other):
        Diff = set()

        SelfNodes = set(list(self._Nodes))
        SelfFTrans = set(list(self._FTransitions))
        SelfBTrans = set(list(self._BTransitions))
        OtherNodes = set(list(other.IterNodes()))
        OtherFTrans = set(list(other.IterFTransitions()))
        OtherBTrans = set(list(other.IterBTransitions()))

        Diff.update(SelfNodes.symmetric_difference(OtherNodes))
        Diff.update(SelfFTrans.symmetric_difference(OtherFTrans))
        Diff.update(SelfBTrans.symmetric_difference(OtherBTrans))

        NodesInter = SelfNodes.intersection(OtherNodes)
        FTransInter = SelfFTrans.intersection(OtherFTrans)
        BTransInter = SelfBTrans.intersection(OtherBTrans)

        Check = lambda Node: self._Nodes[Node] != other.GetNode(Node)
        tmp = [Node for Node in NodesInter if Check(Node)]
        Diff.update(set(tmp))

        Check = lambda Node: self._FTransitions[Node] != list(other.IterFTransitions(Node))
        tmp = [Node for Node in FTransInter if Check(Node)]
        Diff.update(tmp)

        Check = lambda Node: self._BTransitions[Node] != list(other.IterBTransitions(Node))
        tmp = [Node for Node in BTransInter if Check(Node)]
        Diff.update(set(tmp))

        return list(Diff)


    def SubStructure(self,Diff):
        if Diff == []:
            return KripkeStructure()

        Nodes = { Node:self._Nodes[Node] for  Node in Diff if Node in self._Nodes }
        FTransitions = { Node:self._FTransitions[Node] for Node in Diff if Node in self._FTransitions }
        BTransitions = { Node:self._BTransitions[Node] for Node in Diff if Node in self._BTransitions }
        Inits = { Node:self._Inits[Node] for Node in Diff if Node in self._Inits }

        return KripkeStructure(Nodes,FTransitions,BTransitions,Inits)
