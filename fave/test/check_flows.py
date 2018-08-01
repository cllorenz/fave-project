#/usr/bin/env python2

""" This module provides functionality to check FaVe dumps for flow conformity.
"""

import sys
import json
from util.json_util import equal

DUMP = sys.argv[1]
CFLOWS = sys.argv[2]

def check_flow(cflow, pflow, inv_fave):
    """ Checks flows .

    Keyword arguments:
    cflow --
    pflow --
    inv_fave --
    """

    nflow = []
    for node in cflow:
        if '.' in node:
            table, idx = node.split('.')
            crule = inv_fave["table_to_id"][table] << 32 + int(idx)
            nflow.append(crule)
        elif node in inv_fave["generator_to_id"]:
            crule = inv_fave["generator_to_id"][node]
            nflow.append(crule)
        elif node in inv_fave["probe_to_id"]:
            crule = inv_fave["probe_to_id"][node]
            nflow.append(crule)
        else:
            raise "no such generator or probe: %s" % node

    print "\nnflow:", nflow
    print "pflow:", pflow

    return equal(nflow, pflow)

with open(DUMP+"/fave.json", "r") as ifile:
    fave = json.loads(ifile.read())
    SWAP = lambda x, y: (y, x)
    inv_fave = {
        "table_to_id" : dict([SWAP(int(k), v) for k, v in fave["id_to_table"].items()]),
        "generator_to_id" : dict([SWAP(int(k), v) for k, v in fave["id_to_generator"].items()]),
        "probe_to_id" : dict([SWAP(int(k), v) for k, v in fave["id_to_probe"].items()])
    }

with open(DUMP+"/flows.json") as ifile:
    pflows = json.loads(ifile.read())["flows"]

CFLOWS = [json.loads(flow) for flow in CFLOWS.split(';')]

any_flow = False
for cflow in CFLOWS:
    for pflow in pflows:

        if check_flow(cflow, pflow, inv_fave):
            any_flow = True
            break

    if any_flow:
        print " true ",
    else:
        print " false ",
    any_flow = False
