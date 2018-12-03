#!/usr/bin/env python2

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

from util.path_util import Path
from util.path_util import check_pathlet
from util.path_util import json_to_pathlet, pathlet_to_json
from util.path_util import pathlet_to_str, str_to_pathlet

from util.json_util import equal

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

        self.assertItemsEqual(list_union(self.lst1, self.lst2), ['a', 'b', 'c'])
        self.assertItemsEqual(list_union(self.lst2, self.lst1), ['a', 'b', 'c'])
        self.assertItemsEqual(
            list_union(self.lst1, self.lst2),
            list_union(self.lst2, self.lst1)
        )


    def test_list_diff(self):
        """ Tests list difference.
        """

        self.assertItemsEqual(list_diff(self.lst1, self.lst2), ['b', 'c'])
        self.assertItemsEqual(list_diff(self.lst2, self.lst1), ['b', 'c'])
        self.assertItemsEqual(
            list_diff(self.lst1, self.lst2),
            list_diff(self.lst2, self.lst1)
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
        self.assertEqual(OXM_FIELD_TO_MATCH_FIELD['in_port'], 'interface')


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
