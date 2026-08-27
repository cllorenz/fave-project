"""A small, standalone Tseitin CNF converter for ad6's XML formula
representation (see AD6_ENCODING_PLAN.md §2.2/§3, Axis 1). Independent of
ad6/src/sat/satutils.py -- not a replacement, a comparison baseline.

Standard Tseitin transformation: one fresh auxiliary variable per internal
(non-leaf) node, with gate-defining clauses relating it to its children's
literals, instead of ad6's own naive De-Morgan-and-distribute approach
(SATUtils.ConvertToCNF / _ConvertDNCToCNFRecurse) which distributes
directly and can blow up in formula alternation depth. No sub-formula
sharing/CSE -- this is the textbook version, the fair baseline for "what
does the well-understood standard fix look like."

Handles exactly the node shapes ad6's own formulas use: VARIABLE (leaf,
signed by its own `negated` attribute), CONSTANT (true/false), CONJUNCTION/
DISJUNCTION (n-ary AND/OR), IMPLICATION and EQUALITY (2-ary, as ad6 always
builds them: Implicant->Conclusio, and (variable-or-formula)<->conjunction).
"""
from src.xml.xmlutils import XMLUtils


class TseitinConverter:
    def __init__(self):
        self.var_index = {}       # leaf variable name -> int
        self.next_index = 1
        self.clauses = []
        self.true_lit = None      # lazily allocated fixed-true variable

    def _fresh(self):
        idx = self.next_index
        self.next_index += 1
        return idx

    def _leaf_lit(self, name):
        if name not in self.var_index:
            self.var_index[name] = self._fresh()
        return self.var_index[name]

    def _true_literal(self):
        if self.true_lit is None:
            self.true_lit = self._fresh()
            self.clauses.append([self.true_lit])
        return self.true_lit

    def convert(self, node):
        """Returns a signed literal (int) representing `node`'s truth
        value, appending gate-defining clauses to self.clauses as needed."""
        tag = node.tag

        if tag == XMLUtils.VARIABLE:
            name = node.attrib[XMLUtils.ATTRNAME]
            negated = node.attrib.get(XMLUtils.ATTRNEGATED) == 'true'
            lit = self._leaf_lit(name)
            return -lit if negated else lit

        if tag == XMLUtils.CONSTANT:
            value = node.attrib.get(XMLUtils.ATTRVALUE) == 'true'
            t = self._true_literal()
            return t if value else -t

        children = [self.convert(child) for child in node]

        if tag == XMLUtils.CONJUNCTION:
            if not children:
                return self._true_literal()
            g = self._fresh()
            for c in children:
                self.clauses.append([-g, c])
            self.clauses.append([g] + [-c for c in children])
            return g

        if tag == XMLUtils.DISJUNCTION:
            if not children:
                return -self._true_literal()
            g = self._fresh()
            for c in children:
                self.clauses.append([-c, g])
            self.clauses.append([-g] + list(children))
            return g

        if tag == XMLUtils.IMPLICATION:
            a, b = children
            # g <-> (a -> b) == g <-> (-a OR b)
            g = self._fresh()
            self.clauses.append([a, g])
            self.clauses.append([-b, g])
            self.clauses.append([-g, -a, b])
            return g

        if tag == XMLUtils.EQUALITY:
            a, b = children
            g = self._fresh()
            self.clauses.append([g, a, b])
            self.clauses.append([g, -a, -b])
            self.clauses.append([-g, -a, b])
            self.clauses.append([-g, a, -b])
            return g

        raise ValueError("unhandled tag: %s" % tag)

    def convert_top(self, formula_element):
        """`formula_element` is ad6's <formula><conjunction>...</conjunction></formula>
        (or a bare <conjunction>). Returns (n_vars, clauses) with the whole
        thing asserted true (a unit clause per top-level conjunct's
        literal), mirroring what ad6's own ConvertToCNF ultimately encodes."""
        if formula_element.tag == XMLUtils.FORMULA:
            formula_element = formula_element[0]

        for child in formula_element:
            lit = self.convert(child)
            self.clauses.append([lit])

        return self.next_index - 1, self.clauses

    def to_dimacs(self):
        n_vars = self.next_index - 1
        lines = ["p cnf %d %d" % (n_vars, len(self.clauses))]
        for clause in self.clauses:
            lines.append(' '.join(str(l) for l in clause) + ' 0')
        return '\n'.join(lines) + '\n'
