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
