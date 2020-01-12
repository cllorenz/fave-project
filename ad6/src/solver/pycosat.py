import pycosat

from src.solver.solver import AbstractSolver
from src.xml.xmlutils import XMLUtils

class PycoSATAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        self._DIMACS = self.ConvertToDIMACS(CNF)

    def ConvertToDIMACS(self,CNF):
        if CNF.tag == XMLUtils.FORMULA:
            CNF = CNF[0]

        self._Variables = []
        DIMACS = []
        Reverse = {}
        LastIndex = 1

        Clauses = list(CNF)
        for Clause in Clauses:
            Line = []
            if Clause.tag == XMLUtils.VARIABLE:
                Name = Clause.attrib[XMLUtils.ATTRNAME]
                try:
                    Index = Reverse[Name]
                except KeyError:
                    self._Variables.append(Name)
                    Reverse[Name] = LastIndex
                    Index = LastIndex
                    LastIndex += 1

                Flag = Clause.attrib[XMLUtils.ATTRNEGATED] == "false"
                Line.append(Index if Flag else -Index)

            elif Clause.tag == XMLUtils.DISJUNCTION:
                Literals = list(Clause)
                for Literal in Literals:
                    try:
                        Name = Literal.attrib[XMLUtils.ATTRNAME]
                    except:
                        print("Exception while conversion to DIMACS caused by:")
                        XMLUtils.pprint(Clause)
                        exit(1)
                    try:
                        Index = Reverse[Name]
                    except KeyError:
                        self._Variables.append(Name)
                        Reverse[Name] = LastIndex
                        Index = LastIndex
                        LastIndex += 1

                    Flag = Literal.attrib[XMLUtils.ATTRNEGATED] == "false"
                    Line.append(Index if Flag else -Index)

            DIMACS.append(Line)
        return DIMACS

    def _ReadResult(self):
        Results = []
        Result = {}

        if self._Result == []:
            return self._Result
        for Var in self._Result:
            Flag = not Var < 0
            if self._Filter(self._Variables[abs(Var)-1]):
                Result[self._Variables[abs(Var)-1]] = Flag
        Results.append(Result)

        return Results


    def _RunSolver(self):
        result = pycosat.solve(self._DIMACS)
        if result == 'UNSAT':
            self._Result = []
        else:
            self._Result = result

    def Reset(self):
        self._DIMACS = []
        self._Result = []
        self._Variables = []

    def __init__(self):
        self._DIMACS = []
        self._Result = []
        self._Variables = []
