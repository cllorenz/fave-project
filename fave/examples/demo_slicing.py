#!/usr/bin/env python

# -*- coding: utf-8 -*-

# Copyright 2019 Jan Sohre

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

import socket
from netplumber.jsonrpc import *

def connect(HOST='127.0.0.1', PORT=1234):
    s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST,PORT))
    return s

def minimal(s):
    reset_plumbing_network(s)

    # add slices
    add_slice(s, 1, ['100xxxxx'], None)
    add_slice(s, 2, ['101xxxxx'], None)

    # add forwarding tables
    add_table(s, 1, [101, 102])
    add_table(s, 2, [201, 202])
    add_table(s, 3, [301, 302])

    # add links
    add_link(s, 0, 101)
    add_link(s, 0, 201)
    add_link(s, 0, 301)
    add_link(s, 102, 103)
    add_link(s, 202, 203)
    add_link(s, 302, 303)

    # add rules
    add_rule(s, 1, 1, [101], [102], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '101xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], 'xxxxxxxx', 'xxxxxxxx', None)

    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])

    # add probes
    add_source_probe(s, [103], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [203], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [303], 'existential', {'type':'false'}, {'type':'true'})

def demo_overlap(s):
    reset_plumbing_network(s)

    add_slice(s, 1, ['10xxxxxx'], None)
    add_slice(s, 2, ['101xxxxx'], None)

def demo_base(s):
    reset_plumbing_network(s)
    
    # add slices
    add_slice(s, 1, ['000xxxxx'], None)
    add_slice(s, 2, ['001xxxxx'], None)
    add_slice(s, 3, ['010xxxxx'], None)
    add_slice(s, 4, ['011xxxxx'], None)
    add_slice(s, 5, ['100xxxxx'], None)
    add_slice(s, 6, ['101xxxxx'], None)

    # add forwarding tables
    add_table(s, 1, (101,102))
    add_table(s, 2, (201,202))
    add_table(s, 3, (301,302))
    add_table(s, 4, (401,402))
    add_table(s, 5, (501,502))
    add_table(s, 6, (601,602))
    add_table(s, 7, (1,11,12,13,14,15,16))

    # add links
    add_link(s, 0, 1)
    add_link(s, 11, 101)
    add_link(s, 12, 201)
    add_link(s, 13, 301)
    add_link(s, 14, 401)
    add_link(s, 15, 501)
    add_link(s, 16, 601)

    add_link(s, 102, 103)
    add_link(s, 202, 203)
    add_link(s, 302, 303)
    add_link(s, 402, 403)
    add_link(s, 502, 503)
    add_link(s, 602, 603)
    
    # add rules
    add_rule(s, 7, 1, [1], [11], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 2, [1], [12], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 3, [1], [13], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 4, [1], [14], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 5, [1], [15], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 6, [1], [16], '101xxxxx', 'xxxxxxxx', None)

    # add dummy in rules in slice tables
    add_rule(s, 1, 1, [101], [102], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 4, 1, [401], [402], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 5, 1, [501], [502], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 1, [601], [602], '101xxxxx', 'xxxxxxxx', None)

    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])

    # add probes
    add_source_probe(s, [103], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [203], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [303], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [403], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [503], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [603], 'existential', {'type':'false'}, {'type':'true'})

def demo_leak1(s):
    reset_plumbing_network(s)
    
    # add slices
    add_slice(s, 1, ['000xxxxx'], None)
    add_slice(s, 2, ['001xxxxx'], None)
    add_slice(s, 3, ['010xxxxx'], None)
    add_slice(s, 4, ['011xxxxx'], None)
    add_slice(s, 5, ['100xxxxx'], None)
    add_slice(s, 6, ['101xxxxx'], None)

    # add slice matrix
    add_slice_matrix(s, ",0,1,2,3,4,5,6\n" +
                        "0,x,x,x,x,x,x,x\n" +
                        "1,x,,,,,,\n" +
                        "2,x,,,,,,\n" +
                        "3,x,,,,,,\n" +
                        "4,x,,,,,,\n" +
                        "5,x,,,,,,\n" +
                        "6,x,,,,,,\n")
    
    # add forwarding tables
    add_table(s, 1, (101,102))
    add_table(s, 2, (201,202))
    add_table(s, 3, (301,302))
    add_table(s, 4, (401,402))
    add_table(s, 5, (501,502))
    add_table(s, 6, (601,602,603,604))
    add_table(s, 7, (1,11,12,13,14,15,16))

    # add links
    add_link(s, 0, 1)
    add_link(s, 11, 101)
    add_link(s, 12, 201)
    add_link(s, 13, 301)
    add_link(s, 14, 401)
    add_link(s, 15, 501)
    add_link(s, 16, 601)
    add_link(s, 2, 603)
    add_link(s, 604, 501)

    add_link(s, 102, 103)
    add_link(s, 202, 203)
    add_link(s, 302, 303)
    add_link(s, 402, 403)
    add_link(s, 502, 503)
    add_link(s, 602, 605)

    # add rules
    add_rule(s, 7, 1, [1], [11], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 2, [1], [12], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 3, [1], [13], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 4, [1], [14], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 5, [1], [15], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 6, [1], [16], '101xxxxx', 'xxxxxxxx', None)

    # add dummy in rules in slice tables
    add_rule(s, 1, 1, [101], [102], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 4, 1, [401], [402], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 5, 1, [501], [502], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 1, [601], [602], '101xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 2, [603], [604], '101xxxxx', '000xxxxx', '100xxxxx')

    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])
    add_source(s, ['101xxxxx'], None, [2])

    # add probes
    add_source_probe(s, [103], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [203], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [303], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [403], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [503], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [605], 'existential', {'type':'false'}, {'type':'true'})

def demo_leak2(s):
    reset_plumbing_network(s)
    
    # add slices
    add_slice(s, 1, ['000xxxxx'], None)
    add_slice(s, 2, ['001xxxxx'], None)
    add_slice(s, 3, ['010xxxxx'], None)
    add_slice(s, 4, ['011xxxxx'], None)
    add_slice(s, 5, ['100xxxxx'], None)
    add_slice(s, 6, ['101xxxxx'], None)

    # add slice matrix
    add_slice_matrix(s, ",0,1,2,3,4,5,6\n" +
                        "0,x,x,x,x,x,x,x\n" +
                        "1,x,x,x,x,x,x,x\n" +
                        "2,x,x,,,,x,x\n" +
                        "3,x,x,,x,,x,x\n" +
                        "4,x,x,,,,x,x\n" +
                        "5,x,x,x,x,x,x,x\n" +
                        "6,x,x,x,x,x,x,\n")
    print_slice_matrix(s)

    # add forwarding tables
    add_table(s, 1, (101,102))
    add_table(s, 2, (201,202))
    add_table(s, 3, (301,302))
    add_table(s, 4, (401,402))
    add_table(s, 5, (501,502))
    add_table(s, 6, (601,602,603,604))
    add_table(s, 7, (1,11,12,13,14,15,16))

    # add links
    add_link(s, 0, 1)
    add_link(s, 11, 101)
    add_link(s, 12, 201)
    add_link(s, 13, 301)
    add_link(s, 14, 401)
    add_link(s, 15, 501)
    add_link(s, 16, 601)
    add_link(s, 2, 603)
    add_link(s, 604, 501)

    add_link(s, 102, 103)
    add_link(s, 202, 203)
    add_link(s, 302, 303)
    add_link(s, 402, 403)
    add_link(s, 502, 503)
    add_link(s, 602, 605)
    
    # add rules
    add_rule(s, 7, 1, [1], [11], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 2, [1], [12], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 3, [1], [13], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 4, [1], [14], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 5, [1], [15], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 6, [1], [16], '101xxxxx', 'xxxxxxxx', None)

    # add dummy in rules in slice tables
    add_rule(s, 1, 1, [101], [102], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 4, 1, [401], [402], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 5, 1, [501], [502], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 1, [601], [602], '101xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 2, [603], [604], '101xxxxx', '000xxxxx', 'xxxxxxxx')
    
    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])
    add_source(s, ['101xxxxx'], None, [2])

    # add probes
    add_source_probe(s, [103], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [203], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [303], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [403], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [503], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [605], 'existential', {'type':'false'}, {'type':'true'})

def demo_leak3(s):
    reset_plumbing_network(s)
    
    # add slices
    add_slice(s, 1, ['000xxxxx'], None)
    add_slice(s, 2, ['001xxxxx'], None)
    add_slice(s, 3, ['010xxxxx'], None)
    add_slice(s, 4, ['011xxxxx'], None)
    add_slice(s, 5, ['100xxxxx'], None)
    add_slice(s, 6, ['101xxxxx'], None)

    # add slice matrix
    add_slice_matrix(s,",0,1,2,3,4,5,6\n"+
                       "0,x,x,x,x,x,x,x\n"+
                       "1,x,x,x,x,x,x,x\n"+
                       "2,x,x,x,,,x,x\n"+
                       "3,x,x,,x,,x,x\n"+
                       "4,x,x,,,x,x,x\n"+
                       "5,x,x,x,x,x,x,x\n"+
                       "6,x,x,x,x,x,x,x")

    # add forwarding tables
    add_table(s, 1, (101,102,103,104))
    add_table(s, 2, (201,202,203,204))
    add_table(s, 3, (301,302,303,304))
    add_table(s, 4, (401,402,403,404))
    add_table(s, 5, (501,502,503,504))
    add_table(s, 6, (601,602,603,604))
    add_table(s, 7, (1,11,12,13,14,15,16))

    # add links
    add_link(s, 0, 1)
    add_link(s, 11, 101)
    add_link(s, 12, 201)
    add_link(s, 13, 301)
    add_link(s, 14, 401)
    add_link(s, 15, 501)
    add_link(s, 16, 601)

    # add source links for slices
    add_link(s, 2, 103)
    add_link(s, 3, 203)
    add_link(s, 4, 303)
    add_link(s, 5, 403)
    add_link(s, 6, 503)
    add_link(s, 7, 603)

    # add sink links
    add_link(s, 102, 105)
    add_link(s, 202, 205)
    add_link(s, 302, 305)
    add_link(s, 402, 405)
    add_link(s, 502, 505)
    add_link(s, 602, 605)

    # add links between slices
    add_link(s, 104, 201)
    add_link(s, 104, 301)
    add_link(s, 104, 401)
    add_link(s, 104, 501)
    add_link(s, 104, 601)
    add_link(s, 204, 101)
    add_link(s, 204, 501)
    add_link(s, 204, 601)
    add_link(s, 304, 101)
    add_link(s, 304, 501)
    add_link(s, 304, 601)
    add_link(s, 404, 101)
    add_link(s, 404, 501)
    add_link(s, 404, 601)
    add_link(s, 504, 101)
    add_link(s, 504, 201)
    add_link(s, 504, 301)
    add_link(s, 504, 401)
    add_link(s, 504, 601)
    add_link(s, 604, 101)
    add_link(s, 604, 201)
    add_link(s, 604, 301)
    add_link(s, 604, 401)
    add_link(s, 604, 501)
    
    # add rules
    add_rule(s, 7, 1, [1], [11], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 2, [1], [12], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 3, [1], [13], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 4, [1], [14], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 5, [1], [15], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 6, [1], [16], '101xxxxx', 'xxxxxxxx', None)

    # add dummy in rules in slice tables
    add_rule(s, 1, 1, [101], [102], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 4, 1, [401], [402], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 5, 1, [501], [502], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 1, [601], [602], '101xxxxx', 'xxxxxxxx', None)

    # add outgoing rules from slices to other slices
    add_rule(s, 1, 2, [103], [104], '000xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 2, 2, [203], [204], '001xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 3, 2, [303], [304], '010xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 4, 2, [403], [404], '011xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 5, 2, [503], [504], '100xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 6, 2, [603], [604], '101xxxxx', '000xxxxx', 'xxxxxxxx')    

    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])
    add_source(s, ['xxxxxxxx'], None, [2])
    add_source(s, ['xxxxxxxx'], None, [3])
    add_source(s, ['xxxxxxxx'], None, [4])
    add_source(s, ['xxxxxxxx'], None, [5])
    add_source(s, ['xxxxxxxx'], None, [6])
    add_source(s, ['xxxxxxxx'], None, [7])
    
    # add probes
    add_source_probe(s, [105], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [205], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [305], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [405], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [505], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [605], 'existential', {'type':'false'}, {'type':'true'})

def demo_leak4(s):
    reset_plumbing_network(s)
    
    # add slices
    add_slice(s, 1, ['000xxxxx'], None)
    add_slice(s, 2, ['001xxxxx'], None)
    add_slice(s, 3, ['010xxxxx'], None)
    add_slice(s, 4, ['011xxxxx'], None)
    add_slice(s, 5, ['100xxxxx'], None)
    add_slice(s, 6, ['101xxxxx'], None)

    # add slice matrix
    add_slice_matrix(s,",0,1,2,3,4,5,6\n"+
                       "0,x,x,x,x,x,x,x\n"+
                       "1,x,x,x,x,x,x,x\n"+
                       "2,x,x,x,,,x,x\n"+
                       "3,x,x,,x,,x,x\n"+
                       "4,x,x,,,x,x,x\n"+
                       "5,x,x,x,x,x,x,x\n"+
                       "6,x,x,x,x,x,x,x")

    # add forwarding tables
    add_table(s, 1, (101,102,103,104))
    add_table(s, 2, (201,202,203,204))
    add_table(s, 3, (301,302,303,304))
    add_table(s, 4, (401,402,403,404))
    add_table(s, 5, (501,502,503,504))
    add_table(s, 6, (601,602,603,604))
    add_table(s, 7, (1,11,12,13,14,15,16))

    # add links
    add_link(s, 0, 1)
    add_link(s, 11, 101)
    add_link(s, 12, 201)
    add_link(s, 13, 301)
    add_link(s, 14, 401)
    add_link(s, 15, 501)
    add_link(s, 16, 601)

    # add source links for slices
    add_link(s, 2, 103)
    add_link(s, 3, 203)
    add_link(s, 4, 303)
    add_link(s, 5, 403)
    add_link(s, 6, 503)
    add_link(s, 7, 603)

    # add sink links
    add_link(s, 102, 105)
    add_link(s, 202, 205)
    add_link(s, 302, 305)
    add_link(s, 402, 405)
    add_link(s, 502, 505)
    add_link(s, 602, 605)
    
    # add links between slices
    add_link(s, 104, 201)
    add_link(s, 104, 301)
    add_link(s, 104, 401)
    add_link(s, 104, 501)
    add_link(s, 104, 601)
    add_link(s, 204, 101)
    add_link(s, 204, 501)
    add_link(s, 204, 601)
    add_link(s, 304, 101)
    add_link(s, 304, 501)
    add_link(s, 304, 601)
    add_link(s, 404, 101)
    add_link(s, 404, 501)
    add_link(s, 404, 601)
    add_link(s, 504, 101)
    add_link(s, 504, 201)
    add_link(s, 504, 301)
    add_link(s, 504, 401)
    add_link(s, 504, 601)
    add_link(s, 604, 101)
    add_link(s, 604, 201)
    add_link(s, 604, 301)
    add_link(s, 604, 401)
    add_link(s, 604, 501)
    # not allowed
    add_link(s, 404, 201)
    
    # add rules
    add_rule(s, 7, 1, [1], [11], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 2, [1], [12], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 3, [1], [13], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 4, [1], [14], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 5, [1], [15], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 7, 6, [1], [16], '101xxxxx', 'xxxxxxxx', None)

    # add dummy in rules in slice tables
    add_rule(s, 1, 1, [101], [102], '000xxxxx', 'xxxxxxxx', None)
    add_rule(s, 2, 1, [201], [202], '001xxxxx', 'xxxxxxxx', None)
    add_rule(s, 3, 1, [301], [302], '010xxxxx', 'xxxxxxxx', None)
    add_rule(s, 4, 1, [401], [402], '011xxxxx', 'xxxxxxxx', None)
    add_rule(s, 5, 1, [501], [502], '100xxxxx', 'xxxxxxxx', None)
    add_rule(s, 6, 1, [601], [602], '101xxxxx', 'xxxxxxxx', None)

    # add outgoing rules from slices to other slices
    add_rule(s, 1, 2, [103], [104], '000xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 2, 2, [203], [204], '001xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 3, 2, [303], [304], '010xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 4, 2, [403], [404], '011xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 5, 2, [503], [504], '100xxxxx', '000xxxxx', 'xxxxxxxx')
    add_rule(s, 6, 2, [603], [604], '101xxxxx', '000xxxxx', 'xxxxxxxx')    

    # add universal source and source probe
    add_source(s, ['xxxxxxxx'], None, [0])
    add_source(s, ['xxxxxxxx'], None, [2])
    add_source(s, ['xxxxxxxx'], None, [3])
    add_source(s, ['xxxxxxxx'], None, [4])
    add_source(s, ['xxxxxxxx'], None, [5])
    add_source(s, ['xxxxxxxx'], None, [6])
    add_source(s, ['xxxxxxxx'], None, [7])
    
    # add probes
    add_source_probe(s, [105], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [205], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [305], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [405], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [505], 'existential', {'type':'false'}, {'type':'true'})
    add_source_probe(s, [605], 'existential', {'type':'false'}, {'type':'true'})

def simpleslice(s):
    reset_plumbing_network(s)

    add_table(s, 1, (1,2,3,4))

    add_link(s, 0, 1)
    add_link(s, 0, 2)
    add_link(s, 3, 5)
    add_link(s, 4, 5)

    add_rule(s, 1, 1, [1], [3], '10xxxxxx', 'xxxxxxxx', None)
    add_rule(s, 1, 2, [2], [4], '11xxxxxx', 'xxxxxxxx', None)

    add_source(s, ['xxxxxxxx'], None, [0])
    add_source_probe(s, [5], 'existential', {'type':'false'}, {'type':'true'})

    add_slice(s, 1, ['10xxxxxx'], None)
    add_slice(s, 2, ['11xxxxxx'], None)

    print_plumbing_network(s)

def dump(s):
    dump_plumbing_network(s, '.')
    dump_flows(s, '.')
    dump_pipes(s, '.')
    dump_slices(s, '.')
    dump_slices_pipes(s, '.')
