#!/usr/bin/env python
import lxml.etree as et
import os
import sys

class Main:
    def Clear(self,elem):
        for child in elem:
            self.Clear(child)

        elem.Clear()


    def Main(self):
        Config = self._Configs.pop()

        # Instantiate base
        Kripke,Encoding = Instantiator.InstantiateBase(Config)

        # check cycle
        print('Check for cycles...')
        Instance = Instantiator.InstantiateCross(Kripke,Encoding)
        Result = self._Solver.Solve(Instance)
        if Result == []:
            print('\tCycle detected')
        else:
            print('\tNo cycles detected')

        # check cross
        print('Check for cross-path...')
        Instance = Instantiator.InstantiateCross(Kripke,Encoding)
        Result = self._Solver.Solve(Instance)
        if Result == []:
            print('\tCross-Path detected')
        else:
            print('\tNo Cross-Path detected')

        # check reach
        print('Check for Unreachable Nodes...')
        Unreach = []
        Nodes = list(Kripke.IterNodes())
        for Node in Nodes:
            Instance = Instantiator.InstantiateReach(Kripke,Encoding,Node)
            Result = self._Solver.Solve(Instance)
            if Result == []:
                Unreach.append(Node)
                print('\tNot reachable: '+Node)

        # check shadow
        print('Check for shadowed Nodes...')
        Nodes = list(Kripke.IterNodes())
        for Node in Nodes:
            Instance = Instantiator.InstantiateShadow(Kripke,Encoding,{},Node)
            Result = self._Solver.Solve(Instance)
            if Result == []:
                print('\tShadowed: '+Node)

        # check improved reach
        print('Use improved reachability detection...')
        Nodes = list(Kripke.IterNodes())
        while Nodes != []:
            Node = Nodes.pop()
            if 'init' in Kripke.GetNode(Node).Props:
                continue

            Instance = Instantiator.InstantiateReach(Kripke,Encoding,Node)
            Result = self._Solver.Solve(Instance)
            if Result == []:
                print('\tNot reachable: '+Node)
                continue

            Result = Result[0]
            FilterTrans = lambda Transition: Result[Transition] and ('_true_' in Transition or '_false_' in Transition)
            Transitions = [Transition for Transition in Result if FilterTrans(Transition)]
            for Transition in Transitions:
                Labels = Transition.split('_')
                try:
                    Nodes.remove('_'.join(Labels[:5]))
                except:
                    pass
                try:
                    Nodes.remove('_'.join(Labels[6:]))
                except:
                    pass


        # check improved shadow
        print('Use improved shadowing detection...')
        Nodes = set(Kripke.IterNodes())
        Nodes.difference_update(set(Unreach))

        for Node in Unreach:
            print('\tShadowed: '+Node)

        for Node in Nodes:
            if 'init' in Kripke.GetNode(Node).Props:
                continue

            Instance = Instantiator.InstantiateShadow(Kripke,Encoding,{},Node)
            Result = self._Solver.Solve(Instance)
            if Result == []:
                print('\tShadowed: '+Node)



    def __init__(self,ifiles=[]):
        self._Configs = [et.parse(ifile).getroot() for ifile in ifiles]
        for Config in self._Configs:
            XMLUtils.deannotate(Config)

        self._Solver = ClaspAdapter('/dev/shm/solver.in')


if __name__ == "__main__":
    os.environ['PROJ_ROOT'] = os.getcwd()
    os.environ['PROJ_SRC'] = os.environ['PROJ_ROOT']+'/src'
    os.environ['PROJ_CONF'] = os.environ['PROJ_ROOT']+'/conf'

    sys.path.insert(0,os.environ['PROJ_ROOT'])
    sys.path.insert(1,os.environ['PROJ_SRC'])
    sys.path.insert(2,os.environ['PROJ_CONF'])

    from src.core.instantiator import Instantiator
    from src.solver.clasp import ClaspAdapter
    from src.xml.xmlutils import XMLUtils

    Main = Main(['./test/core/testReach.xml'])
    Main.Main()
