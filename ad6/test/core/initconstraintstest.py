import itertools
import unittest
from copy import deepcopy

from src.core.instantiator import Instantiator
from src.core.structure import KripkeStructure, KripkeNode
from src.sat.satutils import SATUtils
from src.solver.pycosat import PycoSATAdapter
from src.xml.xmlutils import XMLUtils


def _build_kripke(n):
    """ n independent, unconditionally-true INIT nodes, each with exactly one
    outgoing transition to its own dedicated target -- the minimal shape
    Instantiator._CreateInitConstraints actually consumes
    (Kripke.IterInits() x Kripke.IterFTransitions(init)), with no other
    Kripke machinery involved. """
    kripke = KripkeStructure({}, {}, {}, {})
    for i in range(n):
        init_key = 'init_%d' % i
        target_key = 'target_%d' % i
        init_node = KripkeNode(Props=[init_key, XMLUtils.INIT], Gamma=XMLUtils.constant())
        target_node = KripkeNode(Props=[target_key], Gamma=XMLUtils.constant())
        kripke.Put(init_key, init_node)
        kripke.Put(target_key, target_node)
        kripke.Put(init_key, (target_key, True))
        kripke.PutInit(init_key, init_node)
    return kripke


def _literal(i):
    return 'init_%d_true_target_%d' % (i, i)


class InitConstraintsTest(unittest.TestCase):
    """ Property test for Instantiator._CreateInitConstraints (AD6_PLAN.md
    §4.4 / ad6/FAVE_CHANGES.md §6,§8): for N marked-INIT nodes, each with a
    single own transition, AT MOST ONE of the N transitions may fire
    simultaneously (mutual exclusion) -- and each remains individually
    satisfiable, and "none fire" stays satisfiable (this is an at-most-one
    encoding, not exactly-one; a query supplies "at least one" itself by
    asserting a specific transition).

    The wl_ifi translator hit a real bug here that this reproduces: the
    chained-XOR construction for Length>3 nodes left almost every
    NON-ADJACENT pair of transitions completely unconstrained -- not just
    "the last few" as first suspected when only N=17 (wl_ifi's generator
    count) had been examined. For every N>=4 under the original code, only
    (T[0],T[1]) was ever correctly excluded; every other pair, including
    ones as close as (T[2],T[3]), could fire together. N=4 is the emptiest
    case (its `range(2, Length-3)` is empty, so zero constraints were
    generated at all). """

    def _encoding(self, n):
        kripke = _build_kripke(n)
        constraints = Instantiator._CreateInitConstraints(kripke)
        encoding = Instantiator._InstantiateBase(kripke)
        encoding[0].extend(constraints)
        SATUtils.ConvertToCNF(encoding)
        return encoding

    def _solvable(self, encoding, forced_true):
        instance = deepcopy(encoding)
        for i in forced_true:
            instance[0].append(XMLUtils.variable(_literal(i)))
        return bool(PycoSATAdapter().Solve(instance))

    def _assertAtMostOne(self, n):
        encoding = self._encoding(n)
        for i in range(n):
            self.assertTrue(self._solvable(encoding, [i]),
                            "init %d of %d is unsatisfiable on its own" % (i, n))
        self.assertTrue(self._solvable(encoding, []),
                        "no inits firing should stay satisfiable (at-most-one, not exactly-one)")
        for i, j in itertools.combinations(range(n), 2):
            self.assertFalse(
                self._solvable(encoding, [i, j]),
                "init %d and %d of %d fired simultaneously -- mutual exclusion broken" % (i, j, n)
            )

    def testTwo(self):
        self._assertAtMostOne(2)

    def testThree(self):
        self._assertAtMostOne(3)

    def testFour(self):
        self._assertAtMostOne(4)

    def testSix(self):
        self._assertAtMostOne(6)

    def testSeventeen(self):
        # wl_ifi's actual generator count -- the case that surfaced this bug.
        self._assertAtMostOne(17)


def main():
    unittest.main()


if __name__ == '__main__':
    main()
