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

""" This module provides an AST structure.
"""
from functools import reduce

class Tree(list):
    """ This class provides storing and manipulation capabilities for an AST.
    """

    def __init__(self, value=None, parent=None):
        """ Constructs an AST object.

        Keyword arguments:
        value -- the tree's value (default: None)
        parent -- the tree's parent tree (default: None)
        """

        super(Tree, self).__init__([])
        self.parent = parent
        self.value = value
        self._negated = False


    def has_child(self, value):
        """ Checks whether the tree is parent of a certain child.

        Keyword arguments:
        value -- the value to be checked
        """

        for tree in self:
            if value == tree.value:
                return True
        return False


    def has_children(self):
        """ Checks whether the tree is parent of any children.
        """
        return len(self) > 0


    def add_child(self, elem):
        """ Appends a child leaf or tree to the tree.

        Keyword arguments:
        elem -- the child to be added (may be value or tree)
        """
        if isinstance(elem, Tree):
            elem.parent = self
            self.append(elem)
            return elem

        return self.add_child(Tree(value=elem))


    def add_children(self, elems):
        """ Appends a list of children to the tree.

        Keyword arguments:
        elems -- the list of children to be added (may be values or trees)
        """
        for elem in elems:
            self.add_child(elem)


    def get_child(self, value):
        """ Fetches a child from the tree.

        Keyword arguments:
        value -- the child to be fetched
        """

        for tree in self:
            if value == tree.value:
                return tree
        return None


    def is_negated(self):
        """ Checks whether the tree is negated.
        """
        return self._negated


    def set_negated(self, neg=True):
        """ Sets the tree's negation.

        Keyword arguments:
        neg -- negation value (Default: True)
        """

        assert isinstance(neg, bool)
        self._negated = neg

        return self


    def get_first(self):
        """ Fetches the tree's first child.
        """

        try:
            return self[0]
        except IndexError:
            return None


    def get_last(self):
        """ Fetches the tree's last child.
        """
        try:
            return self[len(self)-1]
        except IndexError:
            return None


    def __eq__(self, obj):
        return all(
            [self.value == obj.value, self._negated == obj.is_negated()] +
            [a == b for a, b in zip(self, obj)]
        )


    def __str__(self):
        return str(self.value)


    def print_tree(self):
        """ Pretty prints the tree to stdout.
        """
        print((self.stringify()))


    def stringify(self, depth=0):
        """ Converts the tree to a pretty string.

        Keyword arguments:
        depth -- number of prefixed tabs (default: 0)
        """

        if len(self) == 0:
            return "\t"*depth + ("! " if self._negated else "") + str(self.value)
        else:
            return "\t"*depth + \
                ("! " if self._negated else "") + str(self.value) + \
                ":\n" + \
                reduce(
                    lambda x, y: x+"\n"+y,
                    [c.stringify(depth+1) for c in self]
                )
