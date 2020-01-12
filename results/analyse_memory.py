#!/usr/bin/env python3

import numpy

files = ['small.memory.log','medium.memory.log','large.memory.log']


for f in files:
    f = open(f,'r')

    premem = []
    inmem = []
    postmem = []

    line = f.readline()
    while(True):
        if len(line) == 0:
            break

        elems = zip([premem,inmem,postmem],[float(elem) for elem in line.rstrip('\n').split('\t')])
        for ary,elem in elems:
            ary.append(elem)

        line = f.readline()

    print('Mean (Pre): ' + str(numpy.mean(premem)))
    print('Mean (In): ' + str(numpy.mean(inmem)))
    print('Mean (Post): ' + str(numpy.mean(postmem)))

    print('Median (Pre): ' + str(numpy.median(premem)))
    print('Median (In): ' + str(numpy.median(inmem)))
    print('Median (Post): ' + str(numpy.median(postmem)))

    print('Std (Pre): ' + str(numpy.std(premem)))
    print('Std (In): ' + str(numpy.std(inmem)))
    print('Std (Post): ' + str(numpy.std(postmem)))

    f.close()
