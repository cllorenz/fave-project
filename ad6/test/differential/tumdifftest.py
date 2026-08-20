import sys
import time
import unittest

import lxml.etree as et

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator
from src.solver.pycosat import PycoSATAdapter


class TumDifferentialTest(unittest.TestCase):
    """ ad6 vs NetPlumber on wl_tum (AD6_PLAN.md §4.3).

    wl_tum's ruleset (bench/tum/tum-ruleset, 3794 real-world -A FORWARD rules
    from the TUM firewall) is byte-identical to FaVe's own default (ipv4)
    wl_tum benchmark input (fave/bench/wl_tum/rulesets/tum-ruleset) -- no
    translation needed, confirmed by direct diff, not assumption.

    FaVe/NetPlumber's oracle question for wl_tum is a single pair:
    source.tum -> probe.tum, wired in FaVe's own model as
    source.tum -> fw.tum.forward_filter_in (raw injection into the FORWARD
    chain, bypassing any interface/admission notion) and
    fw.tum.forward_filter_accept -> probe.tum (the FORWARD chain's ACCEPT
    exit). The ad6-native equivalent is: is the firewall's synthesized
    `tum_fw_accept_r0` node reachable from an init at `tum_fw_forward_r0`
    (the ruleset's first FORWARD rule -- IP6TablesParser always keys chain
    entry rules `r0`)? No network topology/interface admission is involved
    on either side, so ad6's bundled bench/tum/tum.xml (a 2-interface stub
    ad6 never actually wires into this query) is not exercised and does not
    need to model the ruleset's many VLAN sub-interfaces.

    EXPECTED value (True, i.e. reachable) was obtained from the reference
    oracle by running, from the fave/ directory with PYTHONPATH=. and
    libnetplumber built (net_plumber/python/build_libnetplumber.sh):

        python3 bench/apkeep_tum_diff.py --emit netplumber --out /tmp/np_tum.json

    which printed {"probe.tum": ["source.tum"]} -- NetPlumber says the pair
    IS reachable. Re-derive and update this constant if tum-ruleset changes.
    """

    EXPECTED_REACHABLE = True

    @classmethod
    def setUpClass(cls):
        sys.setrecursionlimit(10**6)

        fw = IP6TablesParser.parse(
            open('bench/tum/tum-ruleset').read(), 'tum_fw', dump_mappings=False
        )
        network = et.parse('bench/tum/tum.xml')

        config = GenUtils.config()
        firewalls = GenUtils.firewalls()
        firewalls.append(fw)
        config.append(firewalls)
        config.extend(network.getroot().getchildren())

        cls.kripke, cls.encoding = Instantiator.InstantiateBase(
            config, Inits=['tum_fw_forward_r0'], default_inits=False
        )
        cls.solver = PycoSATAdapter()

    def testForwardAcceptReachability(self):
        self.assertIn('tum_fw_accept_r0', list(self.kripke.IterNodes()))

        instance = Instantiator.InstantiateReach(
            self.kripke, self.encoding, 'tum_fw_accept_r0'
        )
        result = bool(self.solver.Solve(instance))

        self.assertEqual(
            result, self.EXPECTED_REACHABLE,
            "ad6 disagrees with the NetPlumber oracle on wl_tum "
            "(source.tum -> probe.tum): ad6=%s NetPlumber=%s" % (
                result, self.EXPECTED_REACHABLE
            )
        )


def main():
    unittest.main()


if __name__ == '__main__':
    main()
