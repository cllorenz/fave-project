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

    from test import *
    from test.satsuite import SATSuite
    from test.solversuite import SolverSuite
    from test.xmlsuite import XMLSuite
    from test.kripkesuite import KripkeSuite
    from test.instantiatorsuite import InstantiatorSuite
    from test.integrationsuite import IntegrationSuite
    from test.systemsuite import SystemSuite

    suites = [
        SATSuite(),
        SolverSuite(),
        XMLSuite(),
        KripkeSuite(),
        InstantiatorSuite(),
        IntegrationSuite(),
        SystemSuite()
    ]
    for suite in suites:
            suite.run()
