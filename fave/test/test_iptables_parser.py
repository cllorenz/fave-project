#!/usr/bin/env python3

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

""" This module provides tests for the links as well as the topology command models.
"""

import unittest
import os

from iptables.parser_singleton import PARSER
from util.tree_util import Tree


class TestParser(unittest.TestCase):
    """ This class provides tests for the AST parser.
    """


    def setUp(self):
        self.parser = PARSER


    def tearDown(self):
        del self.parser


    @staticmethod
    def _build_tree_from_tuples(tpls):
        if not isinstance(tpls, tuple):
            val = tpls
            neg = val.startswith("! ")
            if neg:
                val = val[2:]
            leaf = Tree(val)
            if neg:
                leaf.set_negated()
            return leaf

        else:
            tree = TestParser._build_tree_from_tuples(tpls[0])
            for tpl in tpls[1:]:
                tree.add_child(TestParser._build_tree_from_tuples(tpl))
            return tree

    @staticmethod
    def _build_match_from_tuples(tpls, cmd):
        for tpl in tpls:
            item = cmd
            for val in tpl:
                neg = val.startswith("! ")
                if neg:
                    val = val[2:]
                item = item.add_child(val)
                if neg:
                    item.set_negated()


    def test_minimal_ruleset(self):
        """ Tests a minimal rule set consisting of only one policy rule.
        """

        ruleset = "ip6tables -P FORWARD ACCEPT"

        name = "/tmp/ruleset-minimal"
        try:
            with open(name, 'w') as rfile:
                rfile.write(ruleset + '\n')

        finally:
            res = self.parser.parse(name)
            os.remove(name)

        exp = TestParser._build_tree_from_tuples((
            "root", (
                ruleset, (
                    "-P", (
                        "FORWARD", ("ACCEPT",)
                    ),
                    "-t", ("filter",)
                )
            )
        ))

        self.assertEqual(res, exp)


    def test_small_ruleset(self):
        """ Tests a small rule set consisting of one policy and two regular rules.
        """

        ruleset = """\
ip6tables -P FORWARD DROP
ip6tables -t filter -A FORWARD -d 2001:db8::1 -j ACCEPT
ip6tables -A FORWARD -d 2001:db8::2 -m tcp --dport 80 -j ACCEPT
"""

        name = "/tmp/ruleset-small"
        try:
            with open(name, 'w') as rfile:
                rfile.write(ruleset)

        finally:
            res = self.parser.parse(name)
            os.remove(name)

        exp = Tree("root")
        command = TestParser._build_tree_from_tuples((
            "ip6tables -P FORWARD DROP", (
                "-P", (
                    "FORWARD", ("DROP",)
                )
            ), (
                "-t", ("filter",)
            )
        ))
        exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -t filter -A FORWARD -d 2001:db8::1 -j ACCEPT", (
                (
                    "-A",
                    ("FORWARD",),
                    ("-d", ("2001:db8::1",)),
                    ("-j", ("ACCEPT",))
                ), (
                    "-t", ("filter",)
                )
            )
        ))
        exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -A FORWARD -d 2001:db8::2 -m tcp --dport 80 -j ACCEPT", (
                (
                    "-A",
                    ("FORWARD",),
                    ("-d", ("2001:db8::2",)),
                    ("-m", ("tcp",)),
                    ("--dport", ("80",)),
                    ("-j", ("ACCEPT",))
                ), (
                    "-t", ("filter",)
                )
            )
        ))
        exp.add_child(command)

        self.assertEqual(res, exp)


    @staticmethod
    def _build_policies(exp):
        command = TestParser._build_tree_from_tuples((
            "ip6tables -P INPUT DROP", (
                ("-P", ("INPUT", ("DROP",))),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -P FORWARD DROP", (
                ("-P", ("FORWARD", ("DROP",))),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -P OUTPUT DROP", (
                ("-P", ("OUTPUT", ("DROP",))),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)


    @staticmethod
    def _build_input(exp):

        command = TestParser._build_tree_from_tuples((
            "ip6tables -A INPUT -i lo -j ACCEPT", (
                (
                    "-A",
                    ("INPUT",),
                    ("-i", "lo"),
                    ("-j", ("ACCEPT",))
                ),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)

        for icmpv6_type in [
                "destination-unreachable",
                "packet-too-big",
                "time-exceeded",
                "parameter-problem"
        ]:
            command = TestParser._build_tree_from_tuples((
                "ip6tables -A INPUT -p icmpv6 --icmpv6-type %s -j ACCEPT" % icmpv6_type, (
                    (
                        "-A",
                        ("INPUT",),
                        ("-p", "icmpv6"),
                        ("--icmpv6-type", icmpv6_type),
                        ("-j", ("ACCEPT",))
                    ),
                    ("-t", ("filter",))
                )
            ))
            exp.add_child(command)


        for icmpv6_type in ["echo-request", "echo-reply"]:
            command = TestParser._build_tree_from_tuples(
                (
                    "ip6tables -A INPUT -p icmpv6 --icmpv6-type %s -m limit \
--limit 900/min -j ACCEPT" % icmpv6_type,
                    (
                        (
                            "-A",
                            ("INPUT",),
                            ("-p", "icmpv6"),
                            ("--icmpv6-type", icmpv6_type),
                            ("-m", ("limit",)),
                            ("--limit", ("900/min",)),
                            ("-j", ("ACCEPT",))
                        ), (
                            "-t", ("filter",)
                        )
                    )
                )
            )
            exp.add_child(command)

        for icmpv6_type in ["neighbour-solicitation", "neighbour-advertisement"]:
            command = TestParser._build_tree_from_tuples((
                "ip6tables -A INPUT -p icmpv6 --icmpv6-type %s -j ACCEPT" % icmpv6_type, (
                    (
                        "-A",
                        ("INPUT",),
                        ("-p", "icmpv6"),
                        ("--icmpv6-type", icmpv6_type),
                        ("-j", ("ACCEPT",))
                    ),
                    ("-t", ("filter",))
                )
            ))
            exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -A INPUT -d 2001:db8::1 -p tcp --dport 22 -j ACCEPT", (
                (
                    "-A",
                    ("INPUT",),
                    ("-d", ("2001:db8::1",)),
                    ("-p", "tcp"),
                    ("--dport", ("22",)),
                    ("-j", ("ACCEPT",))
                ),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)

        command = TestParser._build_tree_from_tuples((
            "ip6tables -A INPUT -p tcp --dport 80 -j ACCEPT", (
                (
                    "-A",
                    ("INPUT",),
                    ("-p", "tcp"),
                    ("--dport", ("80",)),
                    ("-j", ("ACCEPT",))
                ),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)


    @staticmethod
    def _build_output(exp):
        command = TestParser._build_tree_from_tuples((
            "ip6tables -A OUTPUT -o lo -j ACCEPT", (
                (
                    "-A",
                    ("OUTPUT",),
                    ("-o", ("lo",)),
                    ("-j", ("ACCEPT",))
                ),
                ("-t", ("filter",))
            )
        ))
        exp.add_child(command)


    @staticmethod
    def _build_forward(exp):
        for icmpv6_type in ["destination-unreachable", "packet-too-big"]:
            command = TestParser._build_tree_from_tuples((
                "ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -j ACCEPT" % icmpv6_type, (
                    (
                        "-A",
                        ("FORWARD",),
                        ("-p", ("icmpv6",)),
                        ("--icmpv6-type", (icmpv6_type,)),
                        ("-j", ("ACCEPT",))
                    ),
                    ("-t", ("filter",))
                )
            ))
            exp.add_child(command)

        for icmpv6_type in ["echo-request", "echo-reply"]:
            command = TestParser._build_tree_from_tuples(
                (
                    "ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -m limit \
--limit 900/min -j ACCEPT" % icmpv6_type,
                    (
                        (
                            "-A",
                            ("FORWARD",),
                            ("-p", ("icmpv6",)),
                            ("--icmpv6-type", (icmpv6_type,)),
                            ("-m", ("limit",)),
                            ("--limit", ("900/min",)),
                            ("-j", ("ACCEPT",))
                        ), (
                            "-t", ("filter",)
                        )
                    )
                )
            )
            exp.add_child(command)


        for icmpv6_type in [
                "ttl-zero-during-transit",
                "unknown-header-type",
                "unknown-option"
        ]:
            command = TestParser._build_tree_from_tuples((
                "ip6tables -A FORWARD -p icmpv6 --icmpv6-type %s -j ACCEPT" % icmpv6_type, (
                    (
                        "-A",
                        ("FORWARD",),
                        ("-p", ("icmpv6",)),
                        ("--icmpv6-type", (icmpv6_type,)),
                        ("-j", ("ACCEPT",))
                    ),
                    ("-t", ("filter",))
                )
            ))
            exp.add_child(command)

        negation = lambda x: "! " if x.startswith("! ") else ""
        segs = lambda x: x.lstrip("! ") if x.startswith("! ") else x
        for rt_type, segs_left in [
                ("0", "! 0"),
                ("2", "! 1"),
                ("0", "0"),
                ("2", "1")
        ]:
            command = TestParser._build_tree_from_tuples(
                (
                    "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt \
--rt-type %s %s--rt-segsleft %s -j DROP" % (rt_type, negation(segs_left), segs(segs_left)),
                    (
                        (
                            "-A",
                            ("FORWARD",),
                            ("-m", ("ipv6header",)),
                            ("--header", ("ipv6-route",)),
                            ("-m", ("rt",)),
                            ("--rt-type", (rt_type,)),
                            ("--rt-segsleft", (segs_left,)),
                            ("-j", ("DROP",))
                        ), (
                            "-t", ("filter",)
                        )
                    )
                )
            )
            exp.add_child(command)

        command = TestParser._build_tree_from_tuples(
            (
                "ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt \
! --rt-segsleft 0 -j DROP",
                (
                    (
                        "-A",
                        ("FORWARD",),
                        ("-m", ("ipv6header",)),
                        ("--header", ("ipv6-route",)),
                        ("-m", ("rt",)),
                        ("--rt-segsleft", ("! 0",)),
                        ("-j", ("DROP",))
                    ), (
                        "-t", ("filter",)
                    )
                )
            )
        )
        exp.add_child(command)

        for proto in ["tcp", "udp"]:
            command = TestParser._build_tree_from_tuples((
                "ip6tables -A FORWARD -p %s --dport 80 -j ACCEPT" % proto, (
                    (
                        "-A",
                        ("FORWARD",),
                        ("-p", (proto,)),
                        ("--dport", ("80",)),
                        ("-j", ("ACCEPT",))
                    ),
                    ("-t", ("filter",))
                )
            ))
            exp.add_child(command)


    def test_complex_ruleset(self):
        """ Tests a complex rule set consisting of several policy as well as complex rules.
        """
        ruleset = """\
ip6tables -P INPUT DROP
ip6tables -P FORWARD DROP
ip6tables -P OUTPUT DROP

ip6tables -A INPUT -i lo -j ACCEPT

ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT

ip6tables -A INPUT -d 2001:db8::1 -p tcp --dport 22 -j ACCEPT
ip6tables -A INPUT -p tcp --dport 80 -j ACCEPT

ip6tables -A OUTPUT -o lo -j ACCEPT

ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT

ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 --rt-segsleft 0 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 --rt-segsleft 1 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt ! --rt-segsleft 0 -j DROP

ip6tables -A FORWARD -p tcp --dport 80 -j ACCEPT
ip6tables -A FORWARD -p udp --dport 80 -j ACCEPT
"""

        name = "/tmp/ruleset-complex"
        try:
            with open(name, 'w') as rfile:
                rfile.write(ruleset)

        finally:
            res = self.parser.parse(name)
            os.remove(name)

        exp = Tree("root")
        TestParser._build_policies(exp)
        TestParser._build_input(exp)
        TestParser._build_output(exp)
        TestParser._build_forward(exp)

        self.assertEqual(res, exp)


if __name__ == '__main__':
    unittest.main()
