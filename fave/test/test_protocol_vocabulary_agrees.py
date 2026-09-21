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

""" The two protocol vocabularies are the same one, written twice (item 21).

`Service.valid_protocols` decides which protocols an FPL service may name;
`packet_util.normalize_ipv6_proto` decides which ones FaVe can turn into a
packet field. They must agree, because `protocol` reaches the same field from
both directions -- `util/match_util.py` and `iptables/generator.py` each send it
to `packet.ipv6.proto`.

THEY CANNOT SHARE A DEFINITION: `policy_translator/` is a standalone tree with
its own `mypy.ini` and source root, and importing `fave/` from it would couple
the language to one of its consumers. So the list is duplicated, and this test
is what makes the duplication safe.

Guessing instead of checking is how the divergence arose in the first place:
`examples/fml-paper-policy.txt` declares `protocol = 'arp'` and
`protocol = 1616`, which the FPL side accepted, the matrix rendered, and FaVe
rejects -- so a policy could compile into checks the verifier could not read.

The test asserts equality in BOTH directions. A protocol FaVe gains and FPL
does not is unreachable from a policy; one FPL gains and FaVe does not brings
the original defect back.
"""

import os
import subprocess
import sys
import unittest

from util.packet_util import normalize_ipv6_proto


_FAVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PT = os.path.join(os.path.dirname(_FAVE), 'policy_translator')


def _fpl_protocols():
    """ Read via a subprocess, because `policy_translator` is a separate source
    root: importing it here would put its modules on fave's path. """
    done = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0, %r);'
         'from policy import Service;'
         'print("\\n".join(Service.valid_protocols))' % _PT],
        check=True, capture_output=True)
    return sorted(done.stdout.decode().split())


def _fave_protocols():
    """ `normalize_ipv6_proto` is a dict lookup that raises on anything else,
    so its domain is the vocabulary. Probed rather than read, so that a change
    of representation there does not quietly make this test vacuous. """
    candidates = [
        'gre', 'esp', 'icmp', 'icmpv6', 'tcp', 'udp',      # expected
        'arp', 'sctp', 'dccp', 'ah', 'igmp', 'ospf', '6',  # must NOT be known
    ]
    known = []
    for name in candidates:
        try:
            normalize_ipv6_proto(name)
        except KeyError:
            continue
        known.append(name)
    return sorted(known)


@unittest.skipUnless(os.path.isdir(_PT), "policy_translator not present")
class TestTheVocabulariesAgree(unittest.TestCase):

    def test_FPL_accepts_exactly_what_fave_can_normalise(self):
        self.assertEqual(
            _fpl_protocols(), _fave_protocols(),
            "Service.valid_protocols and packet_util.normalize_ipv6_proto have "
            "drifted apart; they are one vocabulary written in two trees")

    def test_the_probe_is_not_vacuous(self):
        """ If `_fave_protocols` silently returned everything or nothing, the
        test above would pass for the wrong reason. """
        known = _fave_protocols()

        self.assertIn('tcp', known)
        self.assertNotIn('arp', known, "arp is layer 2, not an IP protocol")
        self.assertNotIn('6', known, "the vocabulary is names, not numbers")

    def test_arp_is_rejected_on_BOTH_sides(self):
        """ The concrete divergence, named: `examples/fml-paper-policy.txt`
        wrote it, FPL took it, FaVe never could. """
        self.assertNotIn('arp', _fpl_protocols())
        with self.assertRaises(KeyError):
            normalize_ipv6_proto('arp')


if __name__ == '__main__':
    unittest.main()
