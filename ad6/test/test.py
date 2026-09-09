import sys
import os


if __name__ == "__main__":
    os.environ['PROJ_ROOT'] = os.getcwd()
    os.environ['PROJ_SRC'] = os.environ['PROJ_ROOT']+'/src'
    os.environ['PROJ_TEST'] = os.environ['PROJ_ROOT']+'/test'
    os.environ['PROJ_CONF'] = os.environ['PROJ_ROOT']+'/conf'

    sys.path.insert(0,os.environ['PROJ_ROOT'])
    sys.path.insert(1,os.environ['PROJ_SRC'])
    sys.path.insert(2,os.environ['PROJ_TEST'])
    sys.path.insert(3,os.environ['PROJ_CONF'])

    from test.satsuite import SATSuite
    from test.solversuite import SolverSuite
    from test.xmlsuite import XMLSuite
    from test.kripkesuite import KripkeSuite
    from test.instantiatorsuite import InstantiatorSuite
    from test.initconstraintssuite import InitConstraintsSuite
    from test.integrationsuite import IntegrationSuite
    from test.systemsuite import SystemSuite
    from test.differentialsuite import DifferentialSuite
    from test.parsersuite import ParserSuite
    from test.runnersuite import RunnerSuite
    from test.suiterunner import RunSuites

    suites = [
        SATSuite(),
        SolverSuite(),
        XMLSuite(),
        KripkeSuite(),
        InstantiatorSuite(),
        InitConstraintsSuite(),
        IntegrationSuite(),
        SystemSuite(),
        DifferentialSuite(),
        ParserSuite(),
        RunnerSuite()
    ]
    # Exit non-zero if ANY suite failed, so `make test` (and anything chaining
    # off it) can actually tell a green run from a red one -- this used to fall
    # off the end of __main__ and exit 0 unconditionally. See
    # test/suiterunner.py and ad6/FAVE_CHANGES.md item 24.
    sys.exit(0 if RunSuites(suites) else 1)
