#!/usr/bin/env python2

import unittest

from netplumber.mapping import *
from netplumber.vector import *
from netplumber.model import *

class TestMapping(unittest.TestCase):

    def setUp(self):
        self.mapping = Mapping()

    def tearDown(self):
        del self.mapping

    def test_cmp(self):
        self.assertEqual(self.mapping,Mapping())

    def test_extend(self):
        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(self.mapping.length,128)
        self.assertEqual(self.mapping.keys(), ['packet.ipv6.source'])
        self.assertEqual(self.mapping.values(), [0])

    def test_expand(self):
        self.mapping.extend('packet.ipv6.source')
        other = Mapping(
            length=128, mapping={ 'packet.ipv6.destination' : 0 }
        )
        self.mapping.expand(other)
        self.assertEqual(
            self.mapping,
            Mapping(
                length=256,
                mapping={'packet.ipv6.source':0,'packet.ipv6.destination':128}
            )
        )

    def test_add(self):
        self.mapping.extend('packet.ipv6.source')
        other = Mapping(
            length=128,mapping={'packet.ipv6.destination':0}
        )
        self.assertEqual(
            self.mapping + other,
            Mapping(
                length=256,
                mapping={'packet.ipv6.source':0,'packet.ipv6.destination':128}
            )
        )

    def test_to_json(self):
        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(
            self.mapping.to_json(),{ 'length' : 128, 'packet.ipv6.source' : 0 }
        )

    def test_from_json(self):
        self.mapping.extend('packet.ipv6.source')
        self.assertEqual(
            Mapping.from_json({ 'length' : 128, 'packet.ipv6.source' : 0 }),
            self.mapping
        )


class TestVector(unittest.TestCase):

    def setUp(self):
        self.vector = Vector()

    def tearDown(self):
        del self.vector

    def test_enlarge(self):
        self.vector.enlarge(128)
        self.assertEqual(self.vector.length,128)
        self.assertEqual(self.vector.vector,'x'*128)

    def test_setitem(self):
        self.vector.enlarge(128)
        self.vector[0:32] = '%s%s' % ('1'*16,'0'*16)
        self.assertEqual(self.vector.length,128)
        self.assertEqual(len(self.vector.vector),128)
        self.assertEqual(self.vector.vector,'%s%s%s' % ('1'*16,'0'*16,'x'*96))

    def test_getitem(self):
        self.vector.enlarge(128)
        self.vector[0:32] = '%s%s' % ('1'*16,'0'*16)
        self.assertEqual(self.vector[8:24],'%s%s' % ('1'*8,'0'*8))
        self.assertEqual(self.vector[120:128],'x'*8)

    def get_field_from_vector(self):
        mapping = Mapping()
        mapping.extend('packet.ipv6.source')
        mapping.extend('packet.ipv6.destination')

        self.vector.enlarge(mapping.length)

        set_field_in_vector(
            mapping,
            self.vector,
            'packet.ipv6.source','%s%s%s' % ('1'*16,'0'*16,'x'*96)
        )
        self.assertEqual(self.vector.length,256)
        self.assertEqual(len(self.vector.vector),mapping.length)
        self.assertEqual(self.vector.length,mapping.length)
        self.assertEqual(self.vector.vector,'%s%s%s' % ('1'*16,'0'*16,'x'*224))


    def set_field_in_vector(self):
        mapping = Mapping()
        mapping.extend('packet.ipv6.source')
        mapping.extend('packet.ipv6.destination')
        self.vector.enlarge(mapping.length)
        set_field_in_vector(
            mapping,
            self.vector,
            'packet.ipv6.source','%s%s%s' % ('1'*16,'0'*16,'x'*96)
        )

        self.assertEqual(
            get_field_from_vector(
                mapping,
                vector,
                'packet.ipv6.source'
            ),
            '%s%s%s' % ('1'*16,'0'*16,'x'*96)
        )
        self.assertEqual(
            get_field_from_vector(
                mapping,
                vector,
                'packet.ipv6.destination'
            ), 'x'*128)

    def test_copy_field_between_vectors(self):
        map1 = Mapping()
        map1.extend('packet.ipv6.source')
        map1.extend('packet.ipv6.destination')

        map2 = Mapping()
        map2.extend('packet.ipv6.destination')
        map2.extend('packet.ipv6.source')

        self.vector.enlarge(map1.length)

        other = Vector()
        other.enlarge(map2.length)

        set_field_in_vector(
            map1,
            self.vector,
            'packet.ipv6.source','%s%s%s' % ('1'*16,'0'*16,'x'*96)
        )

        copy_field_between_vectors(
            map1,map2,self.vector,other,'packet.ipv6.source'
        )

        self.assertEqual(
            get_field_from_vector(map1,self.vector,'packet.ipv6.source'),
            get_field_from_vector(map2,other,'packet.ipv6.source')
        )

class TestHeaderSpace(unittest.TestCase):

    def setUp(self):
        vector = Vector(128)
        vector[0:128] = '%s%s%s' % ('1'*16,'0'*16,'x'*96)
        self.header = HeaderSpace(vector.length,[vector])

    def tearDown(self):
        del self.header

    def test_enlarge(self):
        self.header.enlarge(128)

        self.assertEqual(self.header.length,256)
        self.assertTrue(all([v.length == 256 for v in self.header.hs_list]))
        self.assertTrue(all([v.length == 256 for v in self.header.hs_diff]))

    def test_to_json(self):
        self.assertEqual(
            self.header.to_json(),
            {
                'length':128,
                'hs_list':['%s%s%s' % ('1'*16,'0'*16,'x'*96)],
                'hs_diff':[]
            }
        )

    def test_from_json(self):
        self.assertEqual(
            HeaderSpace.from_json({
                'length':128,
                'hs_list':['%s%s%s' % ('1'*16,'0'*16,'x'*96)],
                'hs_diff':[]
            }),
            self.header
        )

class TestModel(unittest.TestCase):

    def setUp(self):
        self.model = Model(
            'foo',
            tables={ '1' : [] },
            ports = { 'foo.1' : 1, 'foo.2' : 2 },
            mapping = Mapping()
    )

    def tearDown(self):
        del self.model

    def test_to_json(self):
        self.assertEqual(
            self.model.to_json(),
            {
                'node' : 'foo',
                'type' : 'model',
                'tables' : { '1' : [] },
                'ports' : { 'foo.1' : 1, 'foo.2' : 2 },
                'wiring' : [],
                'mapping' : { 'length' : 0 }
            }
        )

    def test_to_json_str(self):
        self.assertEqual(
            self.model.to_json_str(),
'{\
"node": "foo", \
"tables": {"1": []}, \
"wiring": [], \
"mapping": {"length": 0}, \
"type": "model", \
"ports": {"foo.2": 2, "foo.1": 1}\
}'
        )

    def test_from_json(self):
        self.assertEqual(
            Model.from_json({
                'node' : 'foo',
                'type' : 'model',
                'tables' : { '1' : [] },
                'ports' : { 'foo.1' : 1, 'foo.2' : 2 },
                'wiring' : [],
                'mapping' : { 'length' : 0 }
            }),
            self.model
        )

    def test_from_json(self):
        self.assertEqual(
            Model.from_string(
'{\
"node":"foo",\
"type":"model",\
"tables":{"1":[]},\
"ports":{"foo.1":1,"foo.2":2},\
"wiring":[],\
"mapping":{"length":0}\
}'	
            ),
            self.model
        )

    def test_sub(self):
        other = Model(
            'foo',
            tables={ '1' : [] },
            ports = { 'foo.1' : 1 },
            mapping = Mapping()
        )
        other.mapping.extend('packet.ipv6.source')

        result = Model(
                'foo',
                tables={},
                ports = { 'foo.2' : 2 },
                mapping = Mapping()
        )
        result.mapping.extend('packet.ipv6.source')

        self.assertEqual(self.model - other, result)

if __name__ == '__main__':
    unittest.main()
