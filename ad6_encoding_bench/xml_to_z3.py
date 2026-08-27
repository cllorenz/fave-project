"""Converts ad6's XML formula representation directly into a Z3 BoolRef,
preserving arbitrary Boolean structure (no CNF/Tseitin needed -- Z3 takes
arbitrary formulas natively). Used by axis4_incremental.py to build one
persistent Z3 Solver representing ad6's shared base model, so many queries
can be checked via incremental assumptions instead of one-shot solves.
"""
from src.xml.xmlutils import XMLUtils
import z3


def to_z3(node):
    tag = node.tag

    if tag == XMLUtils.VARIABLE:
        name = node.attrib[XMLUtils.ATTRNAME]
        negated = node.attrib.get(XMLUtils.ATTRNEGATED) == 'true'
        b = z3.Bool(name)
        return z3.Not(b) if negated else b

    if tag == XMLUtils.CONSTANT:
        return z3.BoolVal(node.attrib.get(XMLUtils.ATTRVALUE) == 'true')

    children = [to_z3(child) for child in node]

    if tag == XMLUtils.CONJUNCTION:
        return z3.And(*children) if children else z3.BoolVal(True)
    if tag == XMLUtils.DISJUNCTION:
        return z3.Or(*children) if children else z3.BoolVal(False)
    if tag == XMLUtils.IMPLICATION:
        a, b = children
        return z3.Implies(a, b)
    if tag == XMLUtils.EQUALITY:
        a, b = children
        return a == b

    raise ValueError("unhandled tag: %s" % tag)


def formula_to_z3(formula_element):
    """`formula_element` is ad6's <formula><conjunction>...</conjunction></formula>.
    Returns a single Z3 BoolRef asserting the whole thing."""
    if formula_element.tag == XMLUtils.FORMULA:
        formula_element = formula_element[0]
    return z3.And(*[to_z3(child) for child in formula_element])
