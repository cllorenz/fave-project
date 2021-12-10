#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.


import re
import random

def _generic_port_check(port, offset, base):
    return port - offset > base and port  - 2  * offset < base

def is_intermediate_port(port, base):
    return _generic_port_check(port, 10000, base)

def is_output_port(port, base):
    return _generic_port_check(port, 20000, base)

def pick_port(ports, seed):
    random.seed(a=seed)
    return random.choice(list(ports))


def array_ipv4_to_cidr(array):
    assert 32 == len(array)
    cidr_regex = '(?P<pre>[01]*)(?P<post>x*)'
    m = re.match(cidr_regex, array)
    if m and 32 == len(m.group('pre')) + len(m.group('post')):
        pre = m.group('pre')
        plen = len(pre)
        post = '0'*len(m.group('post'))

        octal_regex = '(?P<i1>[01]{8})(?P<i2>[01]{8})(?P<i3>[01]{8})(?P<i4>[01]{8})'
        o = re.match(octal_regex, pre+post)
        octals = "%s.%s.%s.%s" % (
            int(o.group('i1'), 2),
            int(o.group('i2'), 2),
            int(o.group('i3'), 2),
            int(o.group('i4'), 2)
        )

        return "%s/%s" % (octals, plen)
    else:
        raise Exception("array not in cidr format: %s" % array)


def array_vlan_to_number(array):
    assert 16 == len(array)
    if 'x'*16 == array:
        return 0

    vlan_regex = '((xxxx)|(0000))(?P<vlan>[01]{12})'
    m = re.match(vlan_regex, array)
    if m:
        return int(m.group('vlan'), 2)
    else:
        raise Exception("array not a vlan number: %s" % array)


def array_to_int(array):
    try:
        return int(array, 2)
    except ValueError:
        return array
