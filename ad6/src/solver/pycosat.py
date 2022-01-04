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

import pycosat

from src.solver.solver import AbstractSolver
from src.xml.xmlutils import XMLUtils

class PycoSATAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        self._Variables, self._DIMACS = self._ConvertToDIMACS(CNF)


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
