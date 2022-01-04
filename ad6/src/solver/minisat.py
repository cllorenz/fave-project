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

import os
import sys
import subprocess

from src.solver.solver import AbstractSolver

class MiniSATAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        Variables, DIMACS = self._ConvertToDIMACSStr(CNF)
        self._Variables = Variables

        IFile = open(self._IFILE,'w')
        IFile.write(DIMACS)
        IFile.close()


    def _ReadResult(self):
        OFile = open(self._OFILE,'r')
        Line = OFile.readline()
        if Line.strip() == 'SAT': #TODO: do something useful with this info like raising an exception if UNSAT
            None #print('SAT')
        else:
            None #print('UNSAT')
            return []

        result = {}
        Line = OFile.readline()
        Line = Line.rstrip().rstrip('0').rstrip()
        Line = Line.split(' ')
        for Var in Line:
            Index = int(Var)
            Flag = not Index < 0
            if self._Filter(self._Variables[abs(Index)-1]):
                result[self._Variables[abs(Index)-1]] = Flag

        self.Reset()

        return [result]


    def _RunSolver(self):
        FNULL = open(os.devnull,'w')
        subprocess.call(["minisat", self._IFILE, self._OFILE], stdout=FNULL)


    def Reset(self):
        self._Variables = []


    # setter for the input and output files
    def SetInput(self,Value):
        self._IFILE = Value

    def SetOutput(self,Value):
        self._OFILE = Value

    IFile = property(fset=SetInput)
    OFile = property(fset=SetOutput)


    def __init__(self, IFile="./solver.in", OFile="./solver.out"):
        self._Variables = []
        self._IFILE = IFile
        self._OFILE = OFile
