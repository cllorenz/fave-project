import unittest

from test.suiterunner import RunSuites

from test.satsuite import SATSuite
from test.solversuite import SolverSuite
from test.xmlsuite import XMLSuite
from test.kripkesuite import KripkeSuite
from test.instantiatorsuite import InstantiatorSuite
from test.initconstraintssuite import InitConstraintsSuite
from test.integrationsuite import IntegrationSuite
from test.systemsuite import SystemSuite
from test.differentialsuite import DifferentialSuite


# Every suite class test/test.py drives. Kept here rather than imported from
# test.py because that list lives inside its `if __name__ == "__main__"` block;
# a suite added there and not here simply is not covered by testSuiteRunReturns
# TheirResult below.
_SUITES = [
    SATSuite, SolverSuite, XMLSuite, KripkeSuite, InstantiatorSuite,
    InitConstraintsSuite, IntegrationSuite, SystemSuite, DifferentialSuite
]


class _Result:
    """ Minimal stand-in for unittest.TestResult -- only wasSuccessful() is
    consulted by RunSuites. """

    def __init__(self, Successful):
        self._successful = Successful

    def wasSuccessful(self):
        return self._successful


class _Suite:
    """ Stand-in for one of test/*suite.py's suite classes. Records whether it
    was actually run, so a short-circuiting aggregator can be caught. """

    def __init__(self, Result):
        self._result = Result
        self.Ran = False

    def run(self):
        self.Ran = True
        return self._result


class _StubRunner:
    """ Stand-in for unittest.TextTestRunner: hands back a sentinel instead of
    executing anything, so the suites' run()-returns-its-result contract can be
    checked without running the whole ad6 tree (~40s) ten times over. """

    def __init__(self, Sentinel):
        self._sentinel = Sentinel

    def run(self, _Suite):
        return self._sentinel


class RunnerTest(unittest.TestCase):
    """ Regression test for ad6's own test entry point (ad6/FAVE_CHANGES.md
    item 24).

    `make test` used to exit 0 unconditionally. That was not a cosmetic wart:
    it is how six errored tests (`FileNotFoundError: 'minisat'`, after the
    solver binaries went missing from the environment) reported themselves as
    a successful run, and it would have hidden any real regression from a CI
    job or a `&&` chain just as effectively.

    The verdict was dropped at TWO independent layers, so both are pinned
    here:
      1. each suite's run() called TextTestRunner.run(...) -- which returns a
         TestResult -- and discarded it, returning None;
      2. test/test.py discarded whatever run() returned and never called
         sys.exit().
    Layer 2's one-line mapping lives in __main__ (not directly testable
    without running the whole tree in a subprocess); RunSuites carries the
    logic that decides it, and is tested exhaustively below. """

    def testSuitesRunReturnTheirResult(self):
        """ Layer 1: every suite must hand its runner's TestResult back to the
        caller. Pre-fix all ten returned None. """
        for suite_cls in _SUITES:
            with self.subTest(suite=suite_cls.__name__):
                suite = suite_cls()
                sentinel = _Result(True)
                # Swap the real runner out: this checks the plumbing, not the
                # suite's own tests, which the rest of `make test` already runs.
                suite._runner = _StubRunner(sentinel)
                self.assertIs(
                    suite.run(), sentinel,
                    "%s.run() must return its runner's TestResult; returning "
                    "None makes every failure in it invisible"
                    % suite_cls.__name__)

    def testAllSuitesSucceedingIsASuccess(self):
        self.assertTrue(RunSuites([_Suite(_Result(True)) for _ in range(3)]))

    def testOneFailingSuiteFailsTheWholeRun(self):
        suites = [_Suite(_Result(True)), _Suite(_Result(False)),
                  _Suite(_Result(True))]
        self.assertFalse(RunSuites(suites))

    def testEverySuiteRunsEvenAfterAnEarlierFailure(self):
        """ A short-circuiting aggregator would silently stop testing the tree
        at the first failing suite. """
        suites = [_Suite(_Result(False)), _Suite(_Result(True))]
        RunSuites(suites)
        self.assertTrue(all(s.Ran for s in suites))

    def testSuiteReturningNoResultIsAFailure(self):
        """ Fail closed: a suite that reports nothing is not a passing suite --
        that None is the original bug's own signature. """
        self.assertFalse(RunSuites([_Suite(None)]))
        self.assertFalse(RunSuites([_Suite(_Result(True)), _Suite(None)]))

    def testNoSuitesIsNotAFailure(self):
        """ Degenerate but pinned: an empty run is vacuously successful, so
        this never reports a spurious failure. """
        self.assertTrue(RunSuites([]))


if __name__ == "__main__":
    unittest.main()
