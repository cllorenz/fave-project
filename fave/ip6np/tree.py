from functools import reduce

class Tree(list):
    def __init__(self,value=None,parent=None):
        self.parent = parent
        self.value = value
        self._negated = False

    def has_child(self,value):
        for tree in self:
            if value == str(tree):
                return True
        return False

    def has_children(self):
        return len(self) > 0

    def add_child(self,elem):
        if type(elem) is Tree:
            elem.parent = self
            self.append(elem)
            return elem
        else:
            return self.add_child(Tree(value=elem))

    def get_child(self,value):
        for tree in self:
            if value == str(tree):
                return tree
        return None

    def is_negated(self):
        return self._negated

    def set_negated(self,neg):
        assert(type(neg) == bool)
        self._negated = neg

    def get_first(self):
        if len(self) > 0:
            return self[0]
        return None

    def get_last(self):
        if len(self) > 0:
            return self[len(self)-1]
        return None

    def __equals__(self,obj):
        return self.value == str(obj)

    def __str__(self):
        return str(self.value)

    def print_tree(self):
        print self.stringify()

    def stringify(self,depth=0):
        if len(self) == 0:
            return "\t"*depth + str(self.value)
        else:
            return "\t"*depth + \
                str(self.value) + \
                ":\n" + \
                reduce(
                    lambda x,y: x+"\n"+y,
                    [c.stringify(depth+1) for c in self]
                )

