""" Aggregate the ad6 suites' results into one pass/fail verdict.

Extracted from test/test.py so the verdict logic can be regression-tested
directly (ad6/FAVE_CHANGES.md item 24). Before this existed, test/test.py ran
every suite and then simply fell off the end of __main__, so `make test`
exited 0 no matter what the suites reported -- a failing ad6 suite looked
exactly like a passing one to any caller (a person skimming the tail, a CI
job, a `&&` chain). That is the same "a skip/failure is NOT a pass" hazard
fave/test/backend_gate.py guards on the FaVe side, on ad6's side of the fence.
"""


def RunSuites(Suites):
    """ Run every suite in order and return True iff all of them succeeded.

    Every suite is run even after an earlier one fails -- the point of this
    entry point is a complete picture of the tree, so a short-circuit (e.g.
    `all(S.run().wasSuccessful() for S in Suites)`) would be wrong here.

    A suite whose run() hands back no TestResult at all counts as a FAILURE,
    not a pass: that silent None is precisely what used to make failures
    invisible, so this fails closed rather than trusting the suite. """
    Verdicts = []
    for Suite in Suites:
        Result = Suite.run()
        Verdicts.append(Result is not None and Result.wasSuccessful())
    return all(Verdicts)
