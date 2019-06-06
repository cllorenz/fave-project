#!/usr/bin/env python2

import json

trees = json.load(open("np_dump/flow_trees.json", "r"))["flows"]

def tree_depth(tree):
  if "children" not in tree or not tree["children"]:
    return 1
  else:
    return max(map(tree_depth, tree["children"])) + 1

print max(map(tree_depth, trees))
