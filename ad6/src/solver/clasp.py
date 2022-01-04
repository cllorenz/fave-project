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

class ClaspAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        Variables, DIMACS = self._ConvertToDIMACSStr(CNF)
        self._Variables = Variables

        IFile = open(self._IFILE,'w')
        IFile.write(DIMACS)
        IFile.close()


    def _ReadResult(self):
        Results = []

        Content = self._Result.split('\n')
        Result = {}
        for Line in Content:
            if not Line.startswith('v'):
                continue
            elif Line.startswith('s') and 'USATISFIABLE' in Line:
                return []

            Line = Line.lstrip('v').lstrip().rstrip()
            Line = Line.split(' ')
            for Var in Line:
                if Var == '0':
                    Results += [Result]
                    Result = {}
                    break
                Index = int(Var)
                Flag = not Index < 0
                if self._Filter(self._Variables[abs(Index)-1]):
                    Result[self._Variables[abs(Index)-1]] = Flag

        return Results


    def _RunSolver(self):
        Process = subprocess.Popen(["clasp", "1", self._IFILE],stdout=subprocess.PIPE)
        Output,Err = Process.communicate()
        self._Result = Output.decode('utf-8')


    def Reset(self):
        self._Variables = []
        IFile = open(self._IFILE,'w')
        IFile.writeLine('')
        IFile.close()
        self._Result = ''


    # setter for the input file
    def SetInput(self,Value):
        self._IFILE = Value

    ifile = property(fset=SetInput)


    def __init__(self, IFile="./solver.in"):
        self._Variables = []
        self._IFILE = IFile
