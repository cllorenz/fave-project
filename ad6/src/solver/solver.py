from src.xml.xmlutils import XMLUtils
from src.core.instantiator import Instantiator
from src.sat.satutils import SATUtils

class AbstractSolver:
    def Solve(self,CNF):
        self._Prepare(CNF)
        self._RunSolver()
        Result = self._ReadResult()

        return Result

    def _Prepare(self,CNF):
        raise Exception("TODO: implement")

    def _RunSolver(self):
        raise Exception("TODO: implement")

    def _ReadResult(self):
        raise Exception("TODO: implement")

    def _ConvertToDIMACS(self,CNF):
        Header = "p cnf "
        Content = ""

        if CNF.tag == XMLUtils.FORMULA:
            CNF = CNF[0]

        self._Variables = []
        Reverse = {}
        Clauses = list(CNF)
        LastIndex = 1
        for Clause in Clauses:
            Line = "\n"
            if Clause.tag == XMLUtils.VARIABLE:
                # add to set with new Index
                Name = Clause.attrib[XMLUtils.ATTRNAME]
                try:
                    Index = Reverse[Name]
                except KeyError:
                    self._Variables.append(Name)
                    Reverse[Name] = LastIndex
                    Index = LastIndex
                    LastIndex += 1
                
                # add to Line
                Flag = Clause.attrib[XMLUtils.ATTRNEGATED] == "false"
                Line += str(Index) + " " if Flag else "-" + str(Index) + " "

            elif Clause.tag == XMLUtils.DISJUNCTION:
                Literals = list(Clause)
                for Literal in list(Literals):
                    # add to set with new Index
                    Name = Literal.attrib[XMLUtils.ATTRNAME]
                    try:
                        Index = Reverse[Name]
                    except KeyError:
                        self._Variables.append(Name)
                        Reverse[Name] = LastIndex
                        Index = LastIndex
                        LastIndex += 1
 
                    # add to Line
                    Flag = Literal.attrib[XMLUtils.ATTRNEGATED] == "false"
                    Line += str(Index) + " " if Flag else "-" + str(Index) + " "

            Content += Line + "0"

        Header += str(LastIndex-1) + " " + str(len(Clauses))

        return Header + Content + '\n'

    def _Filter(self,Name):
        return not (Name.startswith(SATUtils.SUB+'_') or Name.endswith('_'+Instantiator.GAMMA))
