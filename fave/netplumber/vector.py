#!/usr/bin/env python2

class Vector(object):
    def __init__(self,length=0,preset="x"):
        assert(length >= 0 and preset in ["0","1","x"])

        self.length = length
        self.vector = preset*length


    def enlarge(self,size):
        self.length += size
        self.vector += "x"*size

    def __setslice__(self,i,j,y):
        assert(j>=i) # and j-i == len(y))
        a = self.vector[:i]
        b = self.vector[j:]
        self.vector = a + y + b

    def __str__(self):
        return "vector:\n\t%s\nlength:\n\t%s" % (self.vector,self.length)

    def __len__(self):
        return self.length
