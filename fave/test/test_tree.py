#!/usr/bin/env python2

""" This modules provides tests for ip6np AST trees.
"""

import unittest

from ip6np.tree import Tree

class TestTree(unittest.TestCase):
    """ This class provides tests for ip6np AST trees.
    """

    def setUp(self):
        """ Sets up a clean test environment.
        """
        self.tree = Tree()


    def tearDown(self):
        """ Destroys test environment.
        """
        del self.tree


    def test_has_children(self):
        """ Tests whether a tree node has children.
        """
        self.assertFalse(self.tree.has_children())

        self.tree.add_child("foo")
        self.assertTrue(self.tree.has_children())


    def test_equals(self):
        """ Tests whether two simple trees are equal.
        """

        self.tree.value = "foo"
        self.assertEqual(self.tree, Tree("foo"))


    def test_add_child(self):
        """ Tests the adding of child nodes.
        """
        self.assertEqual(self.tree.add_child("foo"), Tree(value="foo"))


    def test_get_child(self):
        """ Tests the retrieval of child nodes.
        """

        self.tree.add_child("foo")
        self.tree.add_child("bar")

        self.assertIsNotNone(self.tree.get_child("foo"))
        self.assertIsNotNone(self.tree.get_child("bar"))
        self.assertIsNone(self.tree.get_child("baz"))


    def test_set_negated(self):
        """ Tests negating a child node.
        """

        self.assertEqual(self.tree.is_negated(), False)
        self.tree.set_negated(True)
        self.assertEqual(self.tree.is_negated(), True)
        self.tree.set_negated(False)
        self.assertEqual(self.tree.is_negated(), False)


    def test_is_negated(self):
        """ Tests whether a child node is negated
        """

        self.tree.value = "foo"
        self.tree.set_negated(True)
        other = Tree(value="foo")
        other.set_negated()

        self.assertEqual(self.tree, Tree(value="foo").set_negated(True), other)


    def test_get_first(self):
        """ Tests fetching the first child node.
        """

        self.assertIsNone(self.tree.get_first())

        self.tree.add_child("foo")
        self.tree.add_child("bar")
        self.tree.add_child("baz")

        self.assertEqual(self.tree.get_first(), Tree("foo"))


    def test_get_last(self):
        """ Tests fetching the last child node.
        """

        self.assertIsNone(self.tree.get_last())

        self.tree.add_child("foo")
        self.tree.add_child("bar")
        self.tree.add_child("baz")

        self.assertEqual(self.tree.get_last(), Tree("baz"))


if __name__ == '__main__':
    unittest.main()
