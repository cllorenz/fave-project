#!/usr/bin/env python2

import unittest

from ip6np.tree import Tree

class TestTree(unittest.TestCase):

    def setUp(self):
        self.tree = Tree()

    def tearDown(self):
        del self.tree

    def test_has_children(self):
        self.assertFalse(self.tree.has_children())

        self.tree.add_child("foo")
        self.assertTrue(self.tree.has_children())

    def test_equals(self):
        self.tree.value = "foo"
        self.assertEqual(self.tree,Tree("foo"))

    def test_add_child(self):
        self.assertEqual(self.tree.add_child("foo"),Tree(value="foo"))

    def test_get_child(self):
        self.tree.add_child("foo")
        self.tree.add_child("bar")

        self.assertIsNotNone(self.tree.get_child("foo"))
        self.assertIsNotNone(self.tree.get_child("bar"))
        self.assertIsNone(self.tree.get_child("baz"))

    def test_set_negated(self):
        self.assertEqual(self.tree._negated,False)
        self.tree.set_negated(True)
        self.assertEqual(self.tree._negated,True)
        self.tree.set_negated(False)
        self.assertEqual(self.tree._negated,False)

    def test_is_negated(self):
        self.tree.value = "foo"
        self.tree.set_negated(True)
        other = Tree(value="foo")
        other._negated = True

        self.assertEqual(self.tree,Tree(value="foo"),other)

    def test_get_first(self):
        self.assertIsNone(self.tree.get_first())

        self.tree.add_child("foo")
        self.tree.add_child("bar")
        self.tree.add_child("baz")

        self.assertEqual(self.tree.get_first(),Tree("foo"))

    def test_get_last(self):
        self.assertIsNone(self.tree.get_last())

        self.tree.add_child("foo")
        self.tree.add_child("bar")
        self.tree.add_child("baz")

        self.assertEqual(self.tree.get_last(),Tree("bar"))

if __name__ == '__main__':
    unittest.main()
