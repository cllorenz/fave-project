import os
import sys
import subprocess

from src.solver.solver import AbstractSolver

class ClaspAdapter(AbstractSolver):
    def _Prepare(self,CNF):
        DIMACS = self._ConvertToDIMACS(CNF)

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
        self._Variables = set()
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
