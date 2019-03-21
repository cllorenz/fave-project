#!/usr/bin/env python2

""" This module provides the inventory for the IFI workload.
"""

WITH_IP = [
    "internal", "admin", "office", "staff-1", "staff-2", "pool", "lab",
    "hpc-mgt", "hpc-ic", "slb"
]

WITHOUT_IP = ["mgt", "san", "vmo", "prt", "cam"]

SUBNETS = WITH_IP + WITHOUT_IP
