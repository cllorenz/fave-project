""" This module provides an AST structure.
"""

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
        """ Appends a child leaf or tree to the tree

        Keyword arguments:
        elem -- the child to be added (may be value or tree)
        """
        if isinstance(elem, Tree):
            elem.parent = self
            self.append(elem)
            return elem
        else:
            return self.add_child(Tree(value=elem))


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

        if len(self) > 0:
            return self[0]
        return None


    def get_last(self):
        """ Fetches the tree's last child.
        """
        if len(self) > 0:
            return self[len(self)-1]
        return None


    def __eq__(self, obj):
        if not self.value == obj.value:
            print "value:", self.value, obj.value
        if not self._negated == obj._negated:
            print self.value,
            print "_negated", self._negated, obj._negated

        return all(
            [self.value == obj.value, self._negated == obj._negated] +
            [a == b for a, b in zip(self, obj)]
        )


    def __str__(self):
        return str(self.value)


    def print_tree(self):
        """ Pretty prints the tree to stdout.
        """
        print self.stringify()


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
