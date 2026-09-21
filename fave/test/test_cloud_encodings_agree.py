#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" The cloud dataset ships its network TWICE, and the two agree (TODO item 16).

`network.tf` is a Hassel transfer function; the six `.smt2` instances carry a
Z3-Datalog encoding of the same network. Nothing says they are equivalent, and
at the internet gateway they are not equal as written: **the `.tf` has 14
destination-NAT rules and the Datalog has 11.**

The three extra are for services 1, 11 and 23 -- the only public services whose
address prefixes span TWO datacenters. Each gets one `.tf` rule per datacenter,
with a BYTE-IDENTICAL match (`dst=121.140.254.<i>/32, proto=6, dport=331+i`) and
a different rewrite and out-port.

Hassel resolves that by priority, and the resolution is not a convention this
repository chose -- it is in the vendored implementation. `tf.py`
`_find_influences` records every EARLIER rule whose match intersects as
`affected_by`, and `apply_rewrite_rule` subtracts each applied one's header
space ("subtract off all the higher priority rule's match patterns"). For an
identical match the subtraction is total, the later rule yields nothing, and it
is inert.

**Apply that and the two encodings become the same 11 rules, exactly.** That is
what this file asserts, and why the three unreachable endpoints it implies are a
property of the DATASET rather than a disagreement between engines -- which is
what they were first written up as, wrongly.

The consequence, worth stating because the policy phase reports it as three
violations: for services 1, 11 and 23 the gateway publishes ONE of the two
declared prefixes, so the other datacenter's half of each is not reachable from
the Internet in EITHER encoding, although the README's matrix authorises the
Internet to reach the service.
"""

import os
import re
import unittest

from bench.wl_cloud.cloud_readme import INTERNET_INDEX, read_readme
from bench.wl_cloud.cloud_tf import classify_nodes, parse_tf, read_match_field


_PREFIX = 'bench/wl_cloud'
_RAW = os.path.join(_PREFIX, 'cloud-tf')
_README = os.path.join(_RAW, 'README.txt')
_TF = os.path.join(_RAW, 'network.tf')

_GATEWAY = 1500000

#: The Datalog encodes one relation per node and states the gateway's rules as
#: implications out of `R_1500000`. The variable names are the instance's own
#: (`cloud_oracle.py` reads the argument order rather than assuming it); here
#: only the gateway body shape is needed, and it is identical in all six files.
_BODY = '(R_1500000 N M L K J I H)'
_DPORT = re.compile(r'\(= K (#x[0-9a-f]+)\)')
_HEAD = re.compile(r'\(R_(\d+) G F E D C B A\)')


def _smt2_gateway(path, port_base):
    """ (service index, target core) for every gateway DNAT rule in `path`. """
    with open(path, 'r') as raw:
        text = raw.read()

    rules = []
    for block in re.split(r'\n(?=\(rule )', text):
        if _BODY not in block:
            continue
        dport, head = _DPORT.search(block), _HEAD.search(block)
        if not (dport and head):
            continue
        rules.append((int(dport.group(1)[2:], 16) - port_base, int(head.group(1))))

    return sorted(rules)


def _tf_gateway(model, port_base):
    """ (service index, target core) per gateway DNAT rule, IN FILE ORDER.

    File order is priority order: `tf.py` `_find_influences` makes a rule
    `affected_by` every earlier one it intersects.
    """
    rules = []
    for rule in model.rules_at(_GATEWAY):
        if rule.action != 'rw':
            continue
        dport = read_match_field(rule.match, 'packet.upper.dport')
        rules.append((dport - port_base, rule.out_ports[0]))
    return rules


def _shadowed(rules):
    """ Hassel's resolution: the first rule for a match wins, later ones are
    inert. Returns (surviving, shadowed). """
    seen, surviving, shadowed = set(), [], []
    for service, core in rules:
        if service in seen:
            shadowed.append((service, core))
        else:
            seen.add(service)
            surviving.append((service, core))
    return surviving, shadowed


@unittest.skipUnless(os.path.isfile(_README), "wl_cloud raw scenario not present")
class TestTheTwoEncodingsAgree(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.readme = read_readme(_README)
        with open(_TF, 'r') as raw:
            cls.model = classify_nodes(parse_tf(raw))
        cls.base = cls.readme.service_port_base
        cls.tf = _tf_gateway(cls.model, cls.base)
        cls.instances = sorted(
            os.path.join(_RAW, name) for name in os.listdir(_RAW)
            if name.endswith('.smt2'))

    def test_all_six_instances_encode_the_same_gateway(self):
        """ Otherwise the comparison below would depend on which one was read. """
        self.assertEqual(len(self.instances), 6)
        first = _smt2_gateway(self.instances[0], self.base)
        for path in self.instances[1:]:
            self.assertEqual(_smt2_gateway(path, self.base), first, path)
        self.assertEqual(len(first), 11)

    def test_the_tf_carries_three_rules_the_datalog_does_not(self):
        """ The disagreement as written -- 14 against 11. """
        self.assertEqual(len(self.tf), 14)
        self.assertEqual(len(_smt2_gateway(self.instances[0], self.base)), 11)

    def test_the_extra_rules_are_exactly_the_split_public_services(self):
        """ And they are shadowed, not chosen: an identical match, later. """
        _surviving, shadowed = _shadowed(self.tf)
        self.assertEqual(sorted(s for s, _c in shadowed), [1, 11, 23])

        for service, _core in shadowed:
            self.assertTrue(
                self.readme.permits(INTERNET_INDEX, service),
                "service %d is shadowed but not public" % service)
            self.assertEqual(
                len(self.readme.services[service]), 2,
                "service %d is shadowed but does not span two prefixes" % service)

        # a shadowed rule's match is IDENTICAL to the winner's, which is what
        # makes it inert rather than merely lower-priority
        matches = {}
        for rule in self.model.rules_at(_GATEWAY):
            if rule.action != 'rw':
                continue
            key = tuple(
                read_match_field(rule.match, f) for f in (
                    'packet.ipv4.destination', 'packet.ipv6.proto',
                    'packet.upper.dport'))
            matches.setdefault(key, []).append(rule)

        duplicated = [v for v in matches.values() if len(v) > 1]
        self.assertEqual(len(duplicated), 3)
        for pair in duplicated:
            self.assertEqual(pair[0].match, pair[1].match)
            self.assertNotEqual(pair[0].out_ports, pair[1].out_ports)

    def test_under_hassel_shadowing_the_two_encodings_ARE_the_same(self):
        """ THE POINT OF THIS FILE. 14 reduces to 11, and to the same 11. """
        surviving, _shadow = _shadowed(self.tf)
        self.assertEqual(
            sorted(surviving), _smt2_gateway(self.instances[0], self.base),
            "network.tf and the Datalog disagree about the gateway after "
            "Hassel's own priority resolution -- which would make the three "
            "unreachable endpoints an ENGINE difference after all")

    def test_only_one_prefix_of_each_split_service_is_published(self):
        """ The consequence the policy phase reports as three violations.

        The surviving rule rewrites the destination into ONE of the service's
        two declared prefixes, so the other datacenter's half is unreachable
        from the Internet -- in both encodings, and although matrix row 25
        authorises the Internet to reach the service.
        """
        _surviving, shadowed = _shadowed(self.tf)
        split = sorted(s for s, _c in shadowed)

        published = {}
        for rule in self.model.rules_at(_GATEWAY):
            if rule.action != 'rw':
                continue
            service = read_match_field(
                rule.match, 'packet.upper.dport') - self.base
            if service in published:
                continue                      # shadowed
            published[service] = read_match_field(
                rule.rewrite, 'packet.ipv4.destination')

        for service in split:
            declared = self.readme.services[service]
            self.assertIn(published[service], declared)
            self.assertEqual(
                len([p for p in declared if p != published[service]]), 1,
                "service %d should have exactly one unpublished prefix" % service)


if __name__ == '__main__':
    unittest.main()
