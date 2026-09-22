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

""" ad6 loses a port match when the same rule matches BOTH transport ports.

THE FINDING, and it is not fixed. Two switches in series, each permitting a
different SOURCE port. No packet carries two source ports, so the probe is
unreachable -- and ad6 says so, until each rule ALSO matches a destination port,
at which point it reports the probe reachable. The same happens with the roles
swapped: conflicting destination ports bind until a source port is added beside
them. Either port alone is honoured; the two together are both lost.

WHERE IT COSTS SOMETHING. wl_cloud's leaf ACLs match both ports on every rule,
and its matrix phase pins each endpoint's source port at the generator, so ad6
reports 1,778 violations against NetPlumber's 1,315 -- 463 pairs reachable that
nobody authorised, and no pair missed (CLOUD_BENCH_PLAN.md §1.7.4). The ORACLE
phase agrees 6/6 with both other engines, because its generators inject no
source port: the port is free there, a permitted value always exists, and every
engine says the same.

NOT a generator-seeding gap -- `translate.generator_device` carries the whole
injected header, an immutable field as a match and a mutable one as a rewrite on
the injection edge. This is about matches composing along a path.

STRONGLY SUSPECTED, NOT PROVEN: `Instantiator._ShortenPrefixes` is the IP-prefix
shortening optimisation, and it is handed every key beginning `src_`/`dst_` --
which includes `src_port_342`. It then reads `342` as a dotted-quad address with
an implicit /32, canonises it to a nine-bit string, and may splice or truncate
the equality that binds the port, `Conjunction[:lastCIDR]` with `lastCIDR = 32`
over a sixteen-variable conjunction. That it receives port keys and mangles
their canonical form is demonstrable; that this is what fires here is not yet
shown, and the trigger's exact shape is what a fix has to start from.

MARKED `expectedFailure` rather than skipped, so it runs, and so that FIXING it
reports an unexpected success instead of passing silently.
"""

import logging
import unittest

from types import SimpleNamespace

from rule.rule_model import Rule, Match, RuleField, Forward

_DST = 'packet.ipv4.destination'
_PROTO = 'packet.ipv6.proto'
_SPORT = 'packet.upper.sport'
_DPORT = 'packet.upper.dport'


def _logger(name):
    log = logging.getLogger(name)
    log.setLevel(logging.ERROR)
    return log


def _switch(name, sport, dport):
    match = [RuleField(_DST, '10.0.3.0/25'), RuleField(_PROTO, 6)]
    if sport is not None:
        match.append(RuleField(_SPORT, sport))
    if dport is not None:
        match.append(RuleField(_DPORT, dport))
    return SimpleNamespace(node=name, type='switch', tables={name + '.1': [
        Rule(name, name + '.1', 1, [name + '.1'], Match(match),
             [Forward([name + '.2'])])]})


def _reaches(engine, hops):
    """ source -> sw1 -> sw2 -> probe, each switch permitting one (sport, dport)
    pair. True iff the probe is reachable. """
    for index, (sport, dport) in enumerate(hops, start=1):
        model = _switch('sw%d' % index, sport, dport)
        engine.add_tables(model)
        engine.add_rules(model)
    engine.add_link('source.A.1', 'sw1.1')
    for index in range(1, len(hops)):
        engine.add_link('sw%d.2' % index, 'sw%d.1' % (index + 1))
    engine.add_link('sw%d.2' % len(hops), 'probe.B.1')
    engine.add_generator(
        SimpleNamespace(node='source.A', type='generator', fields={}))
    engine.add_probe(SimpleNamespace(node='probe.B', type='probe'))
    engine.check_compliance({'probe.B': [('source.A', False, [])]})
    return not engine.get_compliance_results()


def _ad6():
    from ad6.adapter import Ad6Adapter
    return Ad6Adapter(_logger('ad6_port_pair'))


def _apkeep():
    from apkeep.adapter import APKeepAdapter
    return APKeepAdapter(_logger('ak_port_pair'), faithful_vlan=False,
                         engine='ndd')


class TestConflictingPortsOnAPath(unittest.TestCase):
    """ One hop permits source port 342, the next permits 999. """

    def test_one_port_alone_binds(self):
        """ The control. With no destination port in either rule, ad6 gets it
        right -- which is what makes the pair the thing that breaks it. """
        self.assertFalse(_reaches(_ad6(), [(342, None), (999, None)]))

    @unittest.expectedFailure
    def test_a_source_port_binds_when_a_destination_port_is_beside_it(self):
        """ The defect. Adding a destination port -- the SAME one at both hops,
        so it discriminates nothing -- makes the conflicting source ports stop
        conflicting. """
        self.assertFalse(_reaches(_ad6(), [(342, 346), (999, 346)]))

    def test_another_engine_gets_both_right(self):
        """ So the model is not the ambiguous thing. """
        self.assertFalse(_reaches(_apkeep(), [(342, None), (999, None)]))
        self.assertFalse(_reaches(_apkeep(), [(342, 346), (999, 346)]))


if __name__ == '__main__':
    unittest.main()
