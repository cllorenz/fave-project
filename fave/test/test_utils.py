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

""" This module provides unit tests for collection, match, packet, path, and
    JSON utilities.
"""

import unittest

from util.collections_util import dict_diff, dict_isect, dict_sub, dict_union
from util.collections_util import list_diff, list_isect, list_sub, list_union

from util.match_util import OXM_FIELD_TO_MATCH_FIELD

from util.packet_util import ETHER_TYPE_IPV6, ETHER_TYPE_IPV4
from util.packet_util import IPV6_ROUTE, IPV6_HOP, IPV6_HBH, IPV6_DST
from util.packet_util import IPV6_FRAG, IPV6_AUTH, IPV6_ESP, IPV6_NONE, IPV6_PROT
from util.packet_util import IP_PROTO_ICMPV6, IP_PROTO_TCP, IP_PROTO_UDP
from util.packet_util import normalize_ipv4_address
from util.packet_util import normalize_ipv6_address, normalize_ipv6_proto
from util.packet_util import normalize_ipv6header_header, normalize_upper_port
from util.packet_util import portrange_to_prefix_list
from util.packet_util import portrange_to_prefixed_bitvectors
from util.packet_util import denormalize_ipv4_address, denormalize_ipv6_address
from util.packet_util import normalize_vlan_tag
from util.packet_util import is_ip, is_domain, is_port, is_ext_port, is_host, is_unix

from util.path_util import Path
from util.path_util import check_pathlet
from util.path_util import json_to_pathlet, pathlet_to_json
from util.path_util import pathlet_to_str, str_to_pathlet

from util.json_util import equal

from util.ip6np_util import field_value_to_bitvector, bitvector_to_field_value
from util.ip6np_util import FieldNotImplementedError, VectorConstructionError
from util.ip6np_util import _normalize_states, _normalize_icmpv6_type
from rule.rule_model import RuleField

class TestCollectionsUtilDict(unittest.TestCase):
    """ This class provides unit tests for dictionary utilities.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """

        self.dct1 = {'a' : 1, 'b' : 2}
        self.dct2 = {'a' : 1, 'c' : 3}


    def test_dict_sub(self):
        """ Tests dictionary subtraction.
        """

        self.assertEqual(dict_sub(self.dct1, self.dct2), {'b' : 2})
        self.assertEqual(dict_sub(self.dct2, self.dct1), {'c' : 3})


    def test_dict_isect(self):
        """ Tests dictionary intersection.
        """

        self.assertEqual(dict_isect(self.dct1, self.dct2), {'a' : 1})
        self.assertEqual(dict_isect(self.dct2, self.dct1), {'a' : 1})
        self.assertEqual(dict_isect(self.dct1, self.dct2), dict_isect(self.dct2, self.dct1))


    def test_dict_union(self):
        """ Tests dictionary unions.
        """

        self.assertEqual(dict_union(self.dct1, self.dct2), {'a' : 1, 'b' : 2, 'c' : 3})
        self.assertEqual(dict_union(self.dct2, self.dct1), {'a' : 1, 'b' : 2, 'c' : 3})
        self.assertEqual(dict_union(self.dct1, self.dct2), dict_union(self.dct2, self.dct1))


    def test_dict_diff(self):
        """ Tests dictionary difference.
        """

        self.assertEqual(dict_diff(self.dct1, self.dct2), {'b' : 2, 'c' : 3})
        self.assertEqual(dict_diff(self.dct2, self.dct1), {'b' : 2, 'c' : 3})
        self.assertEqual(dict_diff(self.dct1, self.dct2), dict_diff(self.dct2, self.dct1))


class TestCollectionsUtilList(unittest.TestCase):
    """ This class provides unit tests for list utilities.
    """

    def setUp(self):
        """ Creates a clean test environment.
        """


        self.lst1 = ['a', 'b']
        self.lst2 = ['a', 'c']

    def test_list_sub(self):
        """ Tests list subtraction.
        """


        self.assertEqual(list_sub(self.lst1, self.lst2), ['b'])
        self.assertEqual(list_sub(self.lst2, self.lst1), ['c'])

    def test_list_isect(self):
        """ Tests list intersection.
        """

        self.assertEqual(list_isect(self.lst1, self.lst2), ['a'])
        self.assertEqual(list_isect(self.lst2, self.lst1), ['a'])
        self.assertEqual(list_isect(self.lst1, self.lst2), list_isect(self.lst2, self.lst1))


    def test_list_union(self):
        """ Tests list union.
        """

        self.assertEqual(sorted(list_union(self.lst1, self.lst2)), ['a', 'b', 'c'])
        self.assertEqual(sorted(list_union(self.lst2, self.lst1)), ['a', 'b', 'c'])
        self.assertEqual(
            sorted(list_union(self.lst1, self.lst2)),
            sorted(list_union(self.lst2, self.lst1))
        )


    def test_list_diff(self):
        """ Tests list difference.
        """

        self.assertEqual(sorted(list_diff(self.lst1, self.lst2)), ['b', 'c'])
        self.assertEqual(sorted(list_diff(self.lst2, self.lst1)), ['b', 'c'])
        self.assertEqual(
            sorted(list_diff(self.lst1, self.lst2)),
            sorted(list_diff(self.lst2, self.lst1))
        )


class TestMatchUtil(unittest.TestCase):
    """ This class provides unit tests for match utilities.
    """

    def test_oxm_conversion(self):
        """ Tests OXM field conversion.
        """

        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['eth_src'], 'packet.ether.source')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['eth_dst'], 'packet.ether.destination')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['eth_type'], 'packet.ether.type')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ipv4_src'], 'packet.ipv4.source')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ipv4_dst'], 'packet.ipv4.destination')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ipv6_src'], 'packet.ipv6.source')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ipv6_dst'], 'packet.ipv6.destination')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ip_proto'], 'packet.ipv6.proto')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['icmpv6_type'], 'packet.ipv6.icmpv6.type')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['ipv6_exthdr'], 'module.ipv6header.header')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['tcp_dst'], 'packet.upper.dport')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['tcp_src'], 'packet.upper.sport')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['udp_dst'], 'packet.upper.dport')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['upd_src'], 'packet.upper.sport')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['in_port'], 'in_port')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['out_port'], 'out_port')
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['interface'], 'interface')


class TestPacketUtil(unittest.TestCase):
    """ This class provides unit tests for packet utilities.
    """

    def test_constants(self):
        """ Tests packet constants.
        """

        self.assertEqual(ETHER_TYPE_IPV4, '00000100')
        self.assertEqual(ETHER_TYPE_IPV6, '00000110')
        self.assertEqual(IP_PROTO_ICMPV6, '00111010')
        self.assertEqual(IP_PROTO_TCP, '00000110')
        self.assertEqual(IP_PROTO_UDP, '00010001')
        self.assertEqual(IPV6_ROUTE, '00101011')
        self.assertEqual(IPV6_HOP, '00000000')
        self.assertEqual(IPV6_HBH, '00000000')
        self.assertEqual(IPV6_DST, '00111100')
        self.assertEqual(IPV6_FRAG, '00101100')
        self.assertEqual(IPV6_AUTH, '00110011')
        self.assertEqual(IPV6_ESP, '00110010')
        self.assertEqual(IPV6_NONE, '00111011')
        self.assertEqual(IPV6_PROT, '11111111')


    def test_normalize_ipv6header_hdr(self):
        """ Tests IPv6 header normalization.
        """

        self.assertEqual(normalize_ipv6header_header('ipv6-route'), IPV6_ROUTE)
        self.assertEqual(normalize_ipv6header_header('hop'), IPV6_HOP)
        self.assertEqual(normalize_ipv6header_header('hop-by-hop'), IPV6_HBH)
        self.assertEqual(normalize_ipv6header_header('dst'), IPV6_DST)
        self.assertEqual(normalize_ipv6header_header('route'), IPV6_ROUTE)
        self.assertEqual(normalize_ipv6header_header('frag'), IPV6_FRAG)
        self.assertEqual(normalize_ipv6header_header('auth'), IPV6_AUTH)
        self.assertEqual(normalize_ipv6header_header('esp'), IPV6_ESP)


    def test_normalize_ipv6_proto(self):
        """ Tests IPv6 proto normalization.
        """

        self.assertEqual(normalize_ipv6_proto('icmpv6'), IP_PROTO_ICMPV6)
        self.assertEqual(normalize_ipv6_proto('tcp'), IP_PROTO_TCP)
        self.assertEqual(normalize_ipv6_proto('udp'), IP_PROTO_UDP)


    def test_normalize_ipv4_address(self):
        """ Tests IPv4 address normalization.
        """

        self.assertEqual(
            normalize_ipv4_address('1.2.3.4'),
            "%s%s%s%s" % (
                '00000001',
                '00000010',
                '00000011',
                '00000100'
            )
        )

        self.assertEqual(
            normalize_ipv4_address('1.2.3.4/23'),
            "%s%s%s%s" % (
                '00000001',
                '00000010',
                '0000001x',
                'xxxxxxxx'
            )
        )


    def test_normalize_ipv6_address(self):
        """ Tests IPv6 address normalization.
        """

        self.assertEqual(
            normalize_ipv6_address('2001:db8::1'),
            "%s%s%s%s%s%s%s%s" % (
                '0010000000000001',
                '0000110110111000',
                '0000000000000000',
                '0000000000000000',
                '0000000000000000',
                '0000000000000000',
                '0000000000000000',
                '0000000000000001'
            )
        )
        self.assertEqual(
            normalize_ipv6_address('2001:db8::1/64'),
            "%s%s%s%s%s%s%s%s" % (
                '0010000000000001',
                '0000110110111000',
                '0000000000000000',
                '0000000000000000',
                'xxxxxxxxxxxxxxxx',
                'xxxxxxxxxxxxxxxx',
                'xxxxxxxxxxxxxxxx',
                'xxxxxxxxxxxxxxxx'
            )
        )


    def test_normalize_upper_port(self):
        """ Tests IPv6 upper port normalization.
        """

        self.assertEqual(
            normalize_upper_port(80),
            '0000000001010000'
        )

        self.assertEqual(
            normalize_upper_port(443),
            '0000000110111011'
        )

        self.assertEqual(
            normalize_upper_port(8080),
            '0001111110010000'
        )

        self.assertEqual(
            normalize_upper_port(22),
            '0000000000010110'
        )


    def test_portrange_to_prefix_list(self):
        """ Tests the conversion of port ranges to a list of prefixes.
        """

        self.assertEqual(
            portrange_to_prefix_list(1024, 2049),
            [(1024, 6), (2048, 15)]
        )

        self.assertEqual(
            portrange_to_prefix_list(1024, 2045),
            [
                (1024, 7),
                (1536, 8),
                (1792, 9),
                (1920, 10),
                (1984, 11),
                (2016, 12),
                (2032, 13),
                (2040, 14),
                (2044, 15)
            ]
        )

        self.assertEqual(
            portrange_to_prefix_list(0, 1),
            [(0, 15)]
        )

        self.assertEqual(
            portrange_to_prefix_list(0, 0),
            [(0, 16)]
        )

        self.assertEqual(
            portrange_to_prefix_list(65534, 65535),
            [(65534, 15)]
        )

        with self.assertRaises(AssertionError):
            portrange_to_prefix_list(65535, 65536)
            portrange_to_prefix_list(65536, 65536)
            portrange_to_prefix_list(65535, 65534)
            portrange_to_prefix_list(-1, 65536)
            portrange_to_prefix_list(0, -1)


    def test_portrange_to_prefixed_bitvectors(self):
        """ Tests rendering a port range as prefixed ternary bit vectors. """
        # A single port -> one fully-specified 16-bit vector.
        self.assertEqual(
            portrange_to_prefixed_bitvectors(80, 80), ['0000000001010000']
        )
        # 0..1 collapses to a single /15 prefix (low bit wildcarded).
        self.assertEqual(
            portrange_to_prefixed_bitvectors(0, 1), ['000000000000000x']
        )
        # A range that needs two prefixes yields two vectors.
        self.assertEqual(
            portrange_to_prefixed_bitvectors(1024, 2049),
            ['000001xxxxxxxxxx', '000010000000000x']
        )


    def test_denormalize_ipv4_address(self):
        """ Tests converting a ternary vector back to an IPv4 prefix. """
        # Contiguous prefix -> dotted-quad with /cidr.
        self.assertEqual(denormalize_ipv4_address('00001010' + 'x'*24), '10.0.0.0/8')
        # Fully specified -> no /cidr suffix.
        self.assertEqual(denormalize_ipv4_address('00001010'*4), '10.10.10.10')
        # All wildcard -> the any-address.
        self.assertEqual(denormalize_ipv4_address('x'*32), '0.0.0.0/0')
        # Non-contiguous mask (a set bit after the wildcard run) is not a prefix:
        # the raw vector is returned unchanged.
        non_contiguous = '00001010' + 'x' + '0'*23
        self.assertEqual(denormalize_ipv4_address(non_contiguous), non_contiguous)
        # Wrong length is a contract violation.
        with self.assertRaises(AssertionError):
            denormalize_ipv4_address('0'*31)


    def test_denormalize_ipv6_address(self):
        """ Tests converting a ternary vector back to an IPv6 prefix. """
        self.assertEqual(
            denormalize_ipv6_address('0000000000001010' + 'x'*112),
            'a:0:0:0:0:0:0:0/16'
        )
        with self.assertRaises(AssertionError):
            denormalize_ipv6_address('0'*127)


    def test_denormalize_is_inverse_of_normalize(self):
        """ Round-trip property: denormalize(normalize(addr)) == addr. """
        for addr in ['10.0.0.0/8', '192.168.1.0/24', '10.10.10.10']:
            self.assertEqual(
                denormalize_ipv4_address(normalize_ipv4_address(addr)), addr
            )


    def test_normalize_vlan_tag(self):
        """ Tests vlan-tag normalization, incl. the zero special case. """
        # vlan 0 is treated as "any" -> all wildcard.
        self.assertEqual(normalize_vlan_tag('0'), 'x'*16)
        self.assertEqual(normalize_vlan_tag('1'), '0000000000000001')
        self.assertEqual(normalize_vlan_tag('4095'), '0000111111111111')
        # Out-of-range tags violate the contract.
        with self.assertRaises(AssertionError):
            normalize_vlan_tag('4096')


    def test_address_and_port_predicates(self):
        """ Tests the is_* validators for addresses, ports, and hosts. """
        # is_ip accepts dotted-quad with optional valid CIDR.
        self.assertTrue(is_ip('10.0.0.0/8'))
        self.assertTrue(is_ip('192.168.1.1'))
        self.assertFalse(is_ip('256.0.0.0'))    # octet out of range
        self.assertFalse(is_ip('10.0.0'))       # too few octets
        self.assertFalse(is_ip('10.0.0.0/33'))  # cidr out of range

        # is_port / is_ext_port accept 0..65535.
        self.assertTrue(is_port('80'))
        self.assertTrue(is_port('0'))
        self.assertTrue(is_port('65535'))
        self.assertFalse(is_port('70000'))
        self.assertFalse(is_port('http'))
        self.assertTrue(is_ext_port('22'))

        # is_domain validates RFC1035-style labels.
        self.assertTrue(is_domain('example.com'))
        self.assertFalse(is_domain('-bad'))

        # is_host requires <ip|domain>:<port>.
        self.assertTrue(is_host('10.0.0.1:80'))
        self.assertTrue(is_host('example.com:443'))
        self.assertFalse(is_host('10.0.0.1'))    # no port
        self.assertFalse(is_host('10.0.0.1:99999'))

        # is_unix rejects embedded NULs.
        self.assertTrue(is_unix('/tmp/sock'))
        self.assertFalse(is_unix('/tmp/so\0ck'))


class TestIp6npUtil(unittest.TestCase):
    """ Tests the field-value <-> bit-vector encoding (ip6np_util).

    This is the central per-field encoding layer feeding rule/header-space
    construction; a wrong encoding silently mis-models a rule.
    """

    def test_field_to_bitvector_state_names(self):
        """ Connection-tracking state names map to the state bitmap. """
        self.assertEqual(
            field_value_to_bitvector(RuleField('module.state', 'NEW')).vector,
            '00000001'
        )
        # Comma-separated states are OR-ed together (RELATED=2 | ESTABLISHED=4).
        self.assertEqual(
            field_value_to_bitvector(
                RuleField('module.state', 'RELATED,ESTABLISHED')
            ).vector,
            '00000110'
        )

    def test_field_to_bitvector_proto_name_and_int_agree(self):
        """ A protocol by name and by number encode identically. """
        by_name = field_value_to_bitvector(RuleField('packet.ipv6.proto', 'tcp')).vector
        by_int = field_value_to_bitvector(RuleField('packet.ipv6.proto', '6')).vector
        self.assertEqual(by_name, by_int)
        self.assertEqual(by_name, '00000110')

    def test_field_to_bitvector_accepts_vector_string(self):
        """ A value that is already a valid field-width vector passes through. """
        self.assertEqual(
            field_value_to_bitvector(RuleField('related', '00000001')).vector,
            '00000001'
        )

    def test_field_to_bitvector_unknown_field_raises(self):
        """ A field with no normalizer (and a non-vector value) is unimplemented. """
        with self.assertRaises(FieldNotImplementedError):
            field_value_to_bitvector(RuleField('packet.ether.source', 'notavec'))

    def test_field_to_bitvector_unparsable_value_raises(self):
        """ A normalizer ValueError on a non-vector value is a construction error. """
        with self.assertRaises(VectorConstructionError):
            field_value_to_bitvector(RuleField('module.limit', 'abc/sec'))

    def test_bitvector_to_field_value(self):
        """ A fully specified vector decodes to its decimal field value. """
        self.assertEqual(bitvector_to_field_value('00000110', 'related'), '6')

    def test_bitvector_to_field_value_empty_and_ignore(self):
        """ None (empty intersection) and all-wildcard both decode to None. """
        self.assertIsNone(bitvector_to_field_value(None, 'related'))
        self.assertIsNone(bitvector_to_field_value('x'*8, 'related'))

    def test_normalize_states_multiflag(self):
        """ _normalize_states OR-combines multiple flags (NEW=1 | ESTABLISHED=4). """
        self.assertEqual(_normalize_states('NEW,ESTABLISHED'), '00000101')

    def test_normalize_icmpv6_type(self):
        """ ICMPv6 type names map to their type/code vector. """
        self.assertEqual(
            _normalize_icmpv6_type('echo-request'), '10000000xxxxxxxx'
        )


class TestPathUtil(unittest.TestCase):
    """ This class provides unit tests for path utilities.
    """

    def test_check_pathlet(self):
        """ Tests pathlet checking.
        """

        self.assertTrue(check_pathlet('start'))
        self.assertTrue(check_pathlet('end'))
        self.assertTrue(check_pathlet('skip'))
        self.assertTrue(check_pathlet('.*(port=foo.1)'))
        self.assertTrue(check_pathlet('(port in (foo.1,foo.2,bar.3,bar.4))'))
        self.assertTrue(check_pathlet('.*(port in (foo.1,foo.2,bar.3,bar.4))$'))
        self.assertTrue(check_pathlet('.*(table=foo)'))
        self.assertTrue(check_pathlet('(table in (foo,bar))'))
        self.assertTrue(check_pathlet('.*(table in (foo,bar))$'))


    def test_pathlet_to_str(self):
        """ Tests pathlet to string conversion.
        """

        self.assertEqual(pathlet_to_str('start'), '^')
        self.assertEqual(pathlet_to_str('end'), '$')
        self.assertEqual(pathlet_to_str('skip'), '.')
        self.assertEqual(pathlet_to_str('.*(port=foo.1)'), '.*(p=foo.1)')
        self.assertEqual(
            pathlet_to_str('(port in (foo.1,foo.2,bar.3,bar.4))'),
            '(p in (foo.1,foo.2,bar.3,bar.4))'
        )
        self.assertEqual(
            pathlet_to_str('.*(port in (foo.1,foo.2,bar.3,bar.4))$'),
            '.*(p in (foo.1,foo.2,bar.3,bar.4))$'
        )
        self.assertEqual(pathlet_to_str('.*(table=foo)'), '.*(t=foo)')
        self.assertEqual(
            pathlet_to_str('(table in (foo,bar))'), '(t in (foo,bar))'
        )
        self.assertEqual(
            pathlet_to_str('.*(table in (foo,bar))$'), '.*(t in (foo,bar))$'
        )


    def test_str_to_pathlet(self):
        """ Tests string to pathlet conversion.
        """

        self.assertEqual(str_to_pathlet('^'), ('start', 1))
        self.assertEqual(str_to_pathlet('$'), ('end', 1))
        self.assertEqual(str_to_pathlet('.'), ('skip', 1))
        self.assertEqual(str_to_pathlet('.*(p=foo.1)'), ('.*(port=foo.1)', 11))
        self.assertEqual(
            str_to_pathlet('(p in (foo.1,foo.2,bar.3,bar.4))'),
            ('(port in (foo.1,foo.2,bar.3,bar.4))', 32)
        )
        self.assertEqual(
            str_to_pathlet('.*(p in (foo.1,foo.2,bar.3,bar.4))$'),
            ('.*(port in (foo.1,foo.2,bar.3,bar.4))$', 35)
        )
        self.assertEqual(str_to_pathlet('.*(t=foo)'), ('.*(table=foo)', 9))
        self.assertEqual(
            str_to_pathlet('(t in (foo,bar))'), ('(table in (foo,bar))', 16)
        )
        self.assertEqual(
            str_to_pathlet('.*(t in (foo,bar))$'), ('.*(table in (foo,bar))$', 19)
        )


    def test_pathlet_to_json(self):
        """ Tests pathlet to JSON conversion.
        """

        self.assertEqual(pathlet_to_json('start'), {'type':'start'})
        self.assertEqual(pathlet_to_json('end'), {'type':'end'})
        self.assertEqual(pathlet_to_json('skip'), {'type':'skip'})
        self.assertEqual(
            pathlet_to_json('.*(port=foo.1)'), {'type':'port', 'port':'foo.1'}
        )
        self.assertEqual(
            pathlet_to_json('(port in (foo.1,foo.2,bar.3,bar.4))'),
            {'type':'next_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
        )
        self.assertEqual(
            pathlet_to_json('.*(port in (foo.1,foo.2,bar.3,bar.4))$'),
            {'type':'last_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
        )
        self.assertEqual(
            pathlet_to_json('.*(table=foo)'), {'type':'table', 'table':'foo'}
        )
        self.assertEqual(
            pathlet_to_json('(table in (foo,bar))'),
            {'type':'next_tables', 'tables':['foo', 'bar']}
        )
        self.assertEqual(
            pathlet_to_json('.*(table in (foo,bar))$'),
            {'type':'last_tables', 'tables':['foo', 'bar']}
        )


    def test_json_to_pathlet(self):
        """ Tests JSON to pathlet conversion.
        """

        self.assertEqual(json_to_pathlet({'type':'start'}), 'start')
        self.assertEqual(json_to_pathlet({'type':'end'}), 'end')
        self.assertEqual(json_to_pathlet({'type':'skip'}), 'skip')
        self.assertEqual(
            json_to_pathlet({'type':'port', 'port':'foo.1'}), '.*(port=foo.1)'
        )
        self.assertEqual(
            json_to_pathlet(
                {'type':'next_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
            ),
            '(port in (foo.1,foo.2,bar.3,bar.4))'
        )
        self.assertEqual(
            json_to_pathlet(
                {'type':'last_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
            ),
            '.*(port in (foo.1,foo.2,bar.3,bar.4))$'
        )
        self.assertEqual(
            json_to_pathlet({'type':'table', 'table':'foo'}), '.*(table=foo)'
        )
        self.assertEqual(
            json_to_pathlet({'type':'next_tables', 'tables':['foo', 'bar']}),
            '(table in (foo,bar))'
        )
        self.assertEqual(
            json_to_pathlet({'type':'last_tables', 'tables':['foo', 'bar']}),
            '.*(table in (foo,bar))$'
        )


    def test_path_to_json(self):
        """ Tests path to JSON conversion.
        """

        path = Path(['start', '.*(port in (foo.1,foo.2,bar.3,bar.4))$'])

        self.assertEqual(
            path.to_json(),
            {
                'pathlets':[
                    {'type':'start'},
                    {'type':'last_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
                ]
            }
        )

        self.assertEqual(
            str(path),
            '^.*(p in (foo.1,foo.2,bar.3,bar.4))$'
        )

        self.assertTrue(
            Path(['start', '.*(port in (foo.1,foo.2,bar.3,bar.4))$']) == path
        )

        self.assertEqual(
            Path.from_json({
                'pathlets':[
                    {'type':'start'},
                    {'type':'last_ports', 'ports':['foo.1', 'foo.2', 'bar.3', 'bar.4']}
                ]
            }),
            path
        )

        self.assertEqual(
            Path.from_string('^.*(p in (foo.1,foo.2,bar.3,bar.4))$'), path
        )


class TestJsonUtil(unittest.TestCase):
    """ This class provides unit tests for JSON utilities.
    """

    def test_basic_equal(self):
        """ Tests basic JSON object equality.
        """

        first_one = 1
        second_one = 1
        third_two = 2
        self.assertTrue(equal(first_one, second_one))
        self.assertFalse(equal(first_one, third_two))

        first_a = "a"
        second_a = "a"
        third_c = "c"
        self.assertTrue(equal(first_a, second_a))
        self.assertFalse(equal(first_a, third_c))

        first_true = True
        second_true = True
        third_false = False
        self.assertTrue(equal(first_true, second_true))
        self.assertFalse(equal(first_true, third_false))

        first_none = None
        second_none = None
        third_one = 1
        self.assertTrue(equal(first_none, second_none))
        self.assertFalse(equal(first_none, third_one))


    def test_complex_equal(self):
        """ Tests complex JSON object equality.
        """

        first_a = {"a" : 1, "b" : 2}
        second_a = {"b" : 2, "a" : 1}
        third_c = {"c" : 3, "a" : 1}
        self.assertTrue(equal(first_a, second_a))
        self.assertFalse(equal(first_a, third_c))

        first_d = [1, 2, 3, {"d" : "e"}]
        second_d = [1, 2, 3, {"d" : "e"}]
        third_f = [1, 2, {"d" : "e"}, 3]
        self.assertTrue(equal(first_d, second_d))
        self.assertFalse(equal(first_d, third_f))

        first_g = {"a" : 1, "b" : [1, 2, 3, {"d" : "e"}]}
        second_g = {"b" : [1, 2, 3, {"d" : "e"}], "a" : 1}
        third_i = {"c" : [1, 2, {"d" : "e"}, 3], "a" : 1}
        self.assertTrue(equal(first_g, second_g))
        self.assertFalse(equal(first_g, third_i))


if __name__ == '__main__':
    unittest.main()
