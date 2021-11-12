#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

import pyparsing as pp


class ASTParser:


    def __init__(self):

        # ruleset ::= line "\n"+
        # line ::= ipt "-A" body action  | ipt "-P" action
        # ipt ::= "ip6tables"
        # action ::= "DROP" | "ACCEPT"
        # body ::= negation argument | argument | negation argument body | argument body
        # negation ::= "!"
        # argument ::= saddr | daddr | sport | dport | proto | sinf | oinf | module
        # saddr ::= "-s" ipv6-addr | "--source" ipv6-addr
        # daddr ::= "-d" ipv6-addr | "--destination" ipv6-addr
        # proto ::= "udp" | "tcp"
        # sport ::= "--sport" portno
        # dport ::= "--dport" portno
        # portno ::= 1..65535
        # sinf ::= "-i" identifier
        # oinf ::= "-o" identifier
        # module ::= "-m" identifier | "--module" identifier

        identifier = pp.Word(pp.alphas, bodyChars=pp.alphanums + '_-')
        word = pp.Word(pp.printables)

        ipv6_seg = '[0-9a-fA-F]{1,4}'
        ipv6_addr = pp.Regex("(%s:){7}%s" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("(%s:){1,7}:" % ipv6_seg) ^ \
            pp.Regex("(%s:){1,6}:%s" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("(%s:){1,5}(:%s){1,2}" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("(%s:){1,4}(:%s){1,3}" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("(%s:){1,3}(:%s){1,4}" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("(%s:){1,2}(:%s){1,5}" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex("%s:((:%s){1,2})" % (ipv6_seg, ipv6_seg)) ^ \
            pp.Regex(":((:%s){1,7}|:)" % ipv6_seg)
#        fe80:(:IPV6SEG){0,4}%[0-9a-zA-Z]{1,}|
#        ::(ffff(:0{1,4}){0,1}:){0,1}IPV4ADDR|
#        (IPV6SEG:){1,4}:IPV4ADDR
        ipv6_cidr = ipv6_addr + pp.Optional(pp.Word('/', bodyChars=pp.nums, min=1, max=3))

        portno = pp.Word(pp.nums, min=1, max=5)

        saddr = pp.Literal('-s') + ipv6_cidr ^ \
            pp.Literal('--source') + ipv6_cidr
        daddr = pp.Literal('-d') + ipv6_cidr ^ \
            pp.Literal('--destination') + ipv6_cidr
        proto = pp.Literal('-p') + identifier ^ \
            pp.Literal('--proto') + identifier
        sport = pp.Literal('--sport') + portno
        dport = pp.Literal('--dport') + portno
        sinf = pp.Literal('-i') + word ^ \
            pp.Literal('--in-interface') + word
        oinf = pp.Literal('-o') + word ^ \
            pp.Literal('--out-interface') + word

        module_cmd = pp.Literal('-m') ^ pp.Literal('--module')
        module = module_cmd + identifier

        module_argument = pp.Literal('-') + pp.alphas + word ^ \
            pp.Literal('--') + identifier + word
        module_body = pp.OneOrMore(module_argument)

        argument = saddr ^ \
            daddr ^ \
            sport ^ \
            dport ^ \
            proto ^ \
            sinf ^ \
            oinf ^ \
            module ^ \
            module_body

        negation = pp.Literal('!')
        neg_argument = negation + argument ^ argument
        body = pp.OneOrMore(neg_argument)

        jump = pp.Literal('-j') ^ pp.Literal('--jump')
        drop = pp.CaselessLiteral('DROP')
        accept = pp.CaselessLiteral('ACCEPT')
        action = drop ^ accept


        append_cmd = pp.Literal('-A')
        policy_cmd = pp.Literal('-P')
        ipt = pp.Literal('ip6tables')

        line = pp.Group(ipt + append_cmd + identifier + body + jump + action) ^ \
            pp.Group(ipt + policy_cmd + identifier + action)

        self.ruleset = pp.OneOrMore(line + pp.OneOrMore(pp.White('\n\r')))


    def parse(self, ruleset):
        self.ruleset.parseString(ruleset)


if __name__ == '__main__':
    with open('bench/wl_up/rulesets/pgf-ruleset', 'r') as rsf:
        raw = rsf.read()
        parser = ASTParser()
        rs = parser.parse(raw)

        print rs