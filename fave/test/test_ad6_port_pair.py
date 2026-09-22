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

""" A rule matching BOTH transport ports means AND, not OR.

THE DEFECT, fixed 2026-09-22. `KripkeUtils.ConvertToKripke` collected every
`<port>` element of a rule into one list, regardless of direction, and combined
them with a DISJUNCTION whenever there was more than one. That is right for
several ports in the same direction -- `--dports 80,443` is an alternation --
and wrong for a source port beside a destination port, which is a conjunction.
So `sport=342 AND dport=346` was encoded as `sport=342 OR dport=346`:

    <disjunction>
      <variable name="src_port_342"/>
      <variable name="dst_port_346"/>
    </disjunction>

An over-approximation on ANY rule carrying both ports. The neighbouring
interface and VLAN readers split their elements by direction; the port reader
did not, and nothing compared its answers with another engine on a model where
it mattered.

WHERE IT COST SOMETHING. wl_cloud's leaf ACLs match both ports on every rule,
and its matrix phase pins each endpoint's source port at the generator, so ad6
reported 1,778 violations against NetPlumber's 1,315 -- 463 pairs reachable
that nobody authorised, none missed (CLOUD_BENCH_PLAN.md §1.7.4). The ORACLE
phase agreed 6/6 with both other engines throughout, because its generators
inject no source port: the port is free there, a permitted value always exists,
and every engine says the same. A defect can sit in a shared reader for as long
as no workload states the thing it drops.

The first suspect was `Instantiator._ShortenPrefixes`, which really is handed
port keys it reads as dotted-quad addresses. Instrumenting it showed it mutates
nothing here, so that is a separate latent oddity and not this.

WHAT EACH TEST HOLDS. The first four drive two switches in series through the
adapter: no packet carries two source ports, so a probe behind hops permitting
different ones is unreachable, with or without a destination port beside them.
The last two inspect the rule condition ad6 builds from its own XML, because
FaVe's translator emits one port per field and the same-direction alternation --
the case the OR was written for, and which must keep working -- has no shape on
the FaVe side.
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


#: One ad6 rule carrying whatever port elements a test wants to inspect. Used
#: for the shapes FaVe's own translator cannot emit (it writes one port per
#: field), which is where the same-direction alternation lives.
_ONE_RULE = """<config><firewalls><firewall name="fw" key="fw_x">
<table name="t"><rule name="r0" key="fw_x_t_r0">
  <proto>tcp</proto>
  %s
  <action type="jump" target="net_x_1_out"/>
</rule></table></firewall></firewalls>
<networks><network name="net"><node name="x">
<interface name="1" key="net_x_1"/><firewall keyref="fw_x"/>
</node></network></networks></config>"""


def _port_condition(ports):
    """ The rule condition ad6 builds for one rule carrying `ports`.

    Imports ad6's reader through `Ad6Adapter.AD6_ROOT` rather than relying on
    `sys.path`: the adapter puts ad6 there when it translates, so a bare
    `from src.core.kripke import ...` works only once some other test in this
    file has run -- which made these two pass together and fail alone.
    """
    import sys

    import lxml.etree as et

    from ad6.adapter import AD6_ROOT
    if AD6_ROOT not in sys.path:
        sys.path.insert(0, AD6_ROOT)
    from src.core.kripke import KripkeUtils

    kripke = KripkeUtils.ConvertToKripke(
        et.fromstring((_ONE_RULE % ports).encode()), default_inits=False)
    for key in sorted(kripke._Nodes):
        xml = et.tostring(kripke._Nodes[key].Gamma).decode()
        if 'port' in xml:
            return xml
    raise AssertionError("no rule condition mentions a port")


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

    def test_a_source_port_binds_when_a_destination_port_is_beside_it(self):
        """ What the defect was. A destination port beside the source port --
        the SAME one at both hops, so it discriminates nothing -- used to make
        the conflicting source ports stop conflicting, because every `<port>` of
        a rule went into one list and the list was OR-ed. """
        self.assertFalse(_reaches(_ad6(), [(342, 346), (999, 346)]))

    def test_a_destination_port_binds_when_a_source_port_is_beside_it(self):
        """ The mirror image, which failed the same way. """
        self.assertFalse(_reaches(_ad6(), [(342, 346), (342, 347)]))

    def test_both_ports_conflicting_is_still_unreachable(self):
        self.assertFalse(_reaches(_ad6(), [(342, 346), (999, 347)]))

    def test_ports_in_ONE_direction_still_alternate(self):
        """ The case the OR was written for, kept: several ports in the same
        direction are alternatives (`--dports 80,443`), so a hop permitting
        either must pass traffic the other hop permits. FaVe's translator emits
        one port per field, so this is asserted where the shape exists -- on the
        rule condition ad6 builds from its own XML. """
        gamma = _port_condition(
            '<port direction="dst">80</port><port direction="dst">443</port>')
        self.assertIn('disjunction', gamma)
        self.assertIn('dst_port_80', gamma)
        self.assertIn('dst_port_443', gamma)

    def test_the_two_directions_CONJOIN(self):
        """ And the defect itself, at the same level: one port per direction is
        an AND, and used to be emitted as an OR. """
        gamma = _port_condition(
            '<port direction="src">342</port><port direction="dst">346</port>')
        self.assertNotIn('disjunction', gamma)
        self.assertIn('src_port_342', gamma)
        self.assertIn('dst_port_346', gamma)

    def test_another_engine_gets_both_right(self):
        """ So the model is not the ambiguous thing. """
        self.assertFalse(_reaches(_apkeep(), [(342, None), (999, None)]))
        self.assertFalse(_reaches(_apkeep(), [(342, 346), (999, 346)]))


if __name__ == '__main__':
    unittest.main()
