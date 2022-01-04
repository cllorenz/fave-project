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
        if CNF.tag == XMLUtils.FORMULA:
            CNF = CNF[0]

        Variables = []
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
                    Variables.append(Name)
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
                        Variables.append(Name)
                        Reverse[Name] = LastIndex
                        Index = LastIndex
                        LastIndex += 1

                    Flag = Literal.attrib[XMLUtils.ATTRNEGATED] == "false"
                    Line.append(Index if Flag else -Index)

            DIMACS.append(Line)
        return Variables, DIMACS

    def _ConvertToDIMACSStr(self, CLF):
        Variables, DIMACS = self._ConvertToDIMACS(CLF)

        Header = "p cnf {} {}".format(len(Variables), len(DIMACS))
        Content = "\n".join([(' '.join([str(v) for v in Clause]) + " 0") for Clause in DIMACS])

        return Variables, Header + '\n' + Content + '\n'

    def _Filter(self,Name):
        return not (Name.startswith(SATUtils.SUB+'_') or Name.endswith('_'+Instantiator.GAMMA))
