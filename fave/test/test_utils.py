#!/usr/bin/env python2

import unittest

from util.collections_util import *
from util.match_util import *
from util.packet_util import *
from util.path_util import *
from util.json_util import *

class TestCollectionsUtilDict(unittest.TestCase):

    def setUp(self):
        self.d1 = { 'a' : 1, 'b' : 2 }
        self.d2 = { 'a' : 1, 'c' : 3 }

    def test_dict_sub(self):
        self.assertEqual(dict_sub(self.d1,self.d2),{ 'b' : 2 })
        self.assertEqual(dict_sub(self.d2,self.d1),{ 'c' : 3 })

    def test_dict_isect(self):
        self.assertEqual(dict_isect(self.d1,self.d2),{ 'a' : 1 })	
        self.assertEqual(dict_isect(self.d2,self.d1),{ 'a' : 1 })
        self.assertEqual(dict_isect(self.d1,self.d2),dict_isect(self.d2,self.d1))

    def test_dict_union(self):
        self.assertEqual(dict_union(self.d1,self.d2),{ 'a' : 1, 'b' : 2, 'c' : 3})
        self.assertEqual(dict_union(self.d2,self.d1),{ 'a' : 1, 'b' : 2, 'c' : 3})
        self.assertEqual(dict_union(self.d1,self.d2),dict_union(self.d2,self.d1))

    def test_dict_diff(self):
        self.assertEqual(dict_diff(self.d1,self.d2),{ 'b' : 2, 'c' : 3 })
        self.assertEqual(dict_diff(self.d2,self.d1),{ 'b' : 2, 'c' : 3 })
        self.assertEqual(dict_diff(self.d1,self.d2),dict_diff(self.d2,self.d1))

class TestCollectionsUtilList(unittest.TestCase):

    def setUp(self):
        self.l1 = [ 'a', 'b' ]
        self.l2 = [ 'a', 'c' ]

    def test_list_sub(self):
        self.assertEqual(list_sub(self.l1,self.l2),[ 'b' ])
        self.assertEqual(list_sub(self.l2,self.l1),[ 'c' ])

    def test_list_isect(self):
        self.assertEqual(list_isect(self.l1,self.l2),[ 'a' ])
        self.assertEqual(list_isect(self.l2,self.l1),[ 'a' ])
        self.assertEqual(list_isect(self.l1,self.l2),list_isect(self.l2,self.l1))

    def test_list_union(self):
        self.assertItemsEqual(list_union(self.l1,self.l2),[ 'a', 'b', 'c' ])
        self.assertItemsEqual(list_union(self.l2,self.l1),[ 'a', 'b', 'c' ])
        self.assertItemsEqual(
            list_union(self.l1,self.l2),
            list_union(self.l2,self.l1)
        )

    def test_list_diff(self):
        self.assertItemsEqual(list_diff(self.l1,self.l2),[ 'b', 'c' ])
        self.assertItemsEqual(list_diff(self.l2,self.l1),[ 'b', 'c' ])
        self.assertItemsEqual(
            list_diff(self.l1,self.l2),
            list_diff(self.l2,self.l1)
        )

class TestMatchUtil(unittest.TestCase):

    def test_oxm_conversion(self):
        self.assertEqual(oxm_field_to_match_field['eth_src'],'packet.ether.source')
        self.assertEqual(oxm_field_to_match_field['eth_dst'],'packet.ether.destination')
        self.assertEqual(oxm_field_to_match_field['eth_type'],'packet.ether.type')
        self.assertEqual(oxm_field_to_match_field['ipv4_src'],'packet.ipv4.source')
        self.assertEqual(oxm_field_to_match_field['ipv4_dst'],'packet.ipv4.destination')
        self.assertEqual(oxm_field_to_match_field['ipv6_src'],'packet.ipv6.source')
        self.assertEqual(oxm_field_to_match_field['ipv6_dst'],'packet.ipv6.destination')
        self.assertEqual(oxm_field_to_match_field['ip_proto'],'packet.ipv6.proto')
        self.assertEqual(oxm_field_to_match_field['icmpv6_type'],'packet.ipv6.icmpv6.type')
        self.assertEqual(oxm_field_to_match_field['ipv6_exthdr'],'module.ipv6header.header')
        self.assertEqual(oxm_field_to_match_field['tcp_dst'],'packet.upper.dport')
        self.assertEqual(oxm_field_to_match_field['tcp_src'],'packet.upper.sport')
        self.assertEqual(oxm_field_to_match_field['udp_dst'],'packet.upper.dport')
        self.assertEqual(oxm_field_to_match_field['upd_src'],'packet.upper.sport')
        self.assertEqual(oxm_field_to_match_field['in_port'],'interface')

class TestPacketUtil(unittest.TestCase):

    def test_constants(self):
        self.assertEqual(ETHER_TYPE_IPV6,'00000110')
        self.assertEqual(IP_PROTO_ICMPV6,'00111010')
        self.assertEqual(IP_PROTO_TCP,'00000110')
        self.assertEqual(IP_PROTO_UDP,'00010001')
        self.assertEqual(IPV6_ROUTE,'00101011')
        self.assertEqual(IPV6_HOP,'00000000')
        self.assertEqual(IPV6_HBH,'00000000')
        self.assertEqual(IPV6_DST,'00111100')
        self.assertEqual(IPV6_FRAG,'00101100')
        self.assertEqual(IPV6_AUTH,'00110011')
        self.assertEqual(IPV6_ESP,'00110010')

    def test_normalize_ipv6header_header(self):
        self.assertEqual(normalize_ipv6header_header('ipv6-route'),IPV6_ROUTE)
        self.assertEqual(normalize_ipv6header_header('hop'),IPV6_HOP)
        self.assertEqual(normalize_ipv6header_header('hop-by-hop'),IPV6_HBH)
        self.assertEqual(normalize_ipv6header_header('dst'),IPV6_DST)
        self.assertEqual(normalize_ipv6header_header('route'),IPV6_ROUTE)
        self.assertEqual(normalize_ipv6header_header('frag'),IPV6_FRAG)
        self.assertEqual(normalize_ipv6header_header('auth'),IPV6_AUTH)
        self.assertEqual(normalize_ipv6header_header('esp'),IPV6_ESP)

    def test_normalize_ipv6_proto(self):
        self.assertEqual(normalize_ipv6_proto('icmpv6'),IP_PROTO_ICMPV6)
        self.assertEqual(normalize_ipv6_proto('tcp'),IP_PROTO_TCP)
        self.assertEqual(normalize_ipv6_proto('udp'),IP_PROTO_UDP)

    def test_normalize_ipv6_address(self):
        self.assertEqual(
            normalize_ipv6_address('2001:db8::1'),
'\
0010000000000001\
0000110110111000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000000\
0000000000000001\
'
        )
        self.assertEqual(
            normalize_ipv6_address('2001:db8::1/64'),
'\
0010000000000001\
0000110110111000\
0000000000000000\
0000000000000000\
xxxxxxxxxxxxxxxx\
xxxxxxxxxxxxxxxx\
xxxxxxxxxxxxxxxx\
xxxxxxxxxxxxxxxx\
'
        )
	
    def test_normalize_upper_port(self):
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

    def test_check_pathlet(self):
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
        self.assertEqual(pathlet_to_str('start'),'^')
        self.assertEqual(pathlet_to_str('end'),'$')
        self.assertEqual(pathlet_to_str('skip'),'.')
        self.assertEqual(pathlet_to_str('.*(port=foo.1)'),'.*(p=foo.1)')
        self.assertEqual(
            pathlet_to_str('(port in (foo.1,foo.2,bar.3,bar.4))'),
            '(p in (foo.1,foo.2,bar.3,bar.4))'
        )
        self.assertEqual(
            pathlet_to_str('.*(port in (foo.1,foo.2,bar.3,bar.4))$'),
            '.*(p in (foo.1,foo.2,bar.3,bar.4))$'
        )
        self.assertEqual(pathlet_to_str('.*(table=foo)'),'.*(t=foo)')
        self.assertEqual(
            pathlet_to_str('(table in (foo,bar))'),'(t in (foo,bar))'
        )
        self.assertEqual(
            pathlet_to_str('.*(table in (foo,bar))$'),'.*(t in (foo,bar))$'
        )

    def test_str_to_pathlet(self):
        self.assertEqual(str_to_pathlet('^'),('start',1))
        self.assertEqual(str_to_pathlet('$'),('end',1))
        self.assertEqual(str_to_pathlet('.'),('skip',1))
        self.assertEqual(str_to_pathlet('.*(p=foo.1)'),('.*(port=foo.1)',11))
        self.assertEqual(
            str_to_pathlet('(p in (foo.1,foo.2,bar.3,bar.4))'),
            ('(port in (foo.1,foo.2,bar.3,bar.4))',32)
        )
        self.assertEqual(
            str_to_pathlet('.*(p in (foo.1,foo.2,bar.3,bar.4))$'),
            ('.*(port in (foo.1,foo.2,bar.3,bar.4))$',35)
        )
        self.assertEqual(str_to_pathlet('.*(t=foo)'),('.*(table=foo)',9))
        self.assertEqual(
            str_to_pathlet('(t in (foo,bar))'),('(table in (foo,bar))',16)
        )
        self.assertEqual(
            str_to_pathlet('.*(t in (foo,bar))$'),('.*(table in (foo,bar))$',19)
        )

    def test_pathlet_to_json(self):
        self.assertEqual(pathlet_to_json('start'),{'type':'start'})
        self.assertEqual(pathlet_to_json('end'),{'type':'end'})
        self.assertEqual(pathlet_to_json('skip'),{'type':'skip'})
        self.assertEqual(
            pathlet_to_json('.*(port=foo.1)'),{'type':'port','port':'foo.1'}
        )
        self.assertEqual(
            pathlet_to_json('(port in (foo.1,foo.2,bar.3,bar.4))'),
            {'type':'next_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
        )
        self.assertEqual(
            pathlet_to_json('.*(port in (foo.1,foo.2,bar.3,bar.4))$'),
            {'type':'last_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
        )
        self.assertEqual(
            pathlet_to_json('.*(table=foo)'),{'type':'table','table':'foo'}
        )
        self.assertEqual(
            pathlet_to_json('(table in (foo,bar))'),
            {'type':'next_tables','tables':['foo','bar']}
        )
        self.assertEqual(
            pathlet_to_json('.*(table in (foo,bar))$'),
            {'type':'last_tables','tables':['foo','bar']}
        )

    def test_json_to_pathlet(self):
        self.assertEqual(json_to_pathlet({'type':'start'}),'start')
        self.assertEqual(json_to_pathlet({'type':'end'}),'end')
        self.assertEqual(json_to_pathlet({'type':'skip'}),'skip')
        self.assertEqual(
            json_to_pathlet({'type':'port','port':'foo.1'}),'.*(port=foo.1)'
        )
        self.assertEqual(
            json_to_pathlet(
                {'type':'next_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
                ),
                '(port in (foo.1,foo.2,bar.3,bar.4))'
        )
        self.assertEqual(
            json_to_pathlet(
                {'type':'last_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
            ),
            '.*(port in (foo.1,foo.2,bar.3,bar.4))$'
        )
        self.assertEqual(
            json_to_pathlet({'type':'table','table':'foo'}),'.*(table=foo)'
        )
        self.assertEqual(
            json_to_pathlet({'type':'next_tables','tables':['foo','bar']}),
            '(table in (foo,bar))'
        )
        self.assertEqual(
            json_to_pathlet({'type':'last_tables','tables':['foo','bar']}),
            '.*(table in (foo,bar))$'
        )

    def test_path_to_json(self):
        p = Path(['start','.*(port in (foo.1,foo.2,bar.3,bar.4))$'])

        self.assertEqual(
            p.to_json(),
            {
                'pathlets':[
                    {'type':'start'},
                    {'type':'last_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
                ]
            }
        )

        self.assertEqual(
            p.to_string(),
            '^.*(p in (foo.1,foo.2,bar.3,bar.4))$'
        )

        self.assertTrue(
            Path(['start','.*(port in (foo.1,foo.2,bar.3,bar.4))$']) == p
        )

        self.assertEqual(Path.from_json(
            {	
                'pathlets':[
                    {'type':'start'},
                    {'type':'last_ports','ports':['foo.1','foo.2','bar.3','bar.4']}
                ]
            }),p
        )

        self.assertEqual(
            Path.from_string('^.*(p in (foo.1,foo.2,bar.3,bar.4))$'),p
        )

class TestJsonUtil(unittest.TestCase):

    def test_basic_equal(self):
        a = 1
        b = 1
        c = 2
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

        a = "a"
        b = "a"
        c = "c"
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

        a = True
        b = True
        c = False
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

        a = None
        b = None
        c = 1
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

    def test_complex_equal(self):
        a = { "a" : 1, "b" : 2 }
        b = { "b" : 2, "a" : 1 }
        c = { "c" : 3, "a" : 1 }
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

        a = [ 1, 2, 3, { "d" : "e" } ]
        b = [ 1, 2, 3, { "d" : "e" } ]
        c = [ 1, 2, { "d" : "e" }, 3 ]
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))

        a = { "a" : 1, "b" : [ 1, 2, 3, { "d" : "e" } ] }
        b = { "b" : [ 1, 2, 3, { "d" : "e" } ], "a" : 1 }
        c = { "c" : [ 1, 2, { "d" : "e" }, 3 ], "a" : 1 }
        self.assertTrue(equal(a,b))
        self.assertFalse(equal(a,c))


if __name__ == '__main__':
    unittest.main()
