#!/usr/bin/env python2

""" Provides tests for RPC calls with a NetPlumber backend.
"""

import unittest

import os
import re
import random

from netplumber.jsonrpc import connect_to_netplumber
from netplumber.jsonrpc import init, destroy, reset_plumbing_network, expand
from netplumber.jsonrpc import print_plumbing_network
from netplumber.jsonrpc import add_table, add_link
from netplumber.jsonrpc import add_rule, remove_rule
from netplumber.jsonrpc import add_source, add_source_probe
from netplumber.jsonrpc import add_slice, remove_slice


def generate_random_rule(idx, in_ports, out_ports, length):
    """ Generates a random rule of a specified length with given ingress and egress ports.
    """

    gen_wc = lambda x: "".join(["01x"[random.randint(0, 2)] for _i in range(x)])
    gen_01 = lambda x: "".join(["01"[random.randint(0, 1)] for _i in range(x)])
    gen_ports = lambda ports: [p for p in ports if random.randint(0, 1) == 1]

    iports = []
    # potential infinite loop...
    # though,  it would be strange randomness if this happened
    while iports == []:
        iports = gen_ports(in_ports)

    oports = gen_ports(out_ports)

    match = gen_wc(length)
    mask = gen_01(length)
    rewrite = gen_wc(length)

    return (idx, iports, oports, match, mask, rewrite)


def _check_probe_log_line(line, probe_id, state):
    p1 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Started in True State" % probe_id
    p2 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Met Probe Condition" % probe_id
    p3 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*More Flows Met Probe Condition" % probe_id
    p4 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Fewer Flows Met Probe Condition" % probe_id

    n1 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Started in False State" % probe_id
    n2 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Failed Probe Condition" % probe_id
    n3 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*More Flows Failed Probe Condition" % probe_id
    n4 = r".*DefaultProbeLogger.* - (Universal|Existential) Probe %s.*Fewer Flows Failed Probe Condition" % probe_id

    # probe match and positive state
    positives = [
        re.match(p1, line) is not None,
        re.match(p2, line) is not None,
        re.match(p3, line) is not None,
        re.match(p4, line) is not None
    ]
    negatives = [
        re.match(n1, line) is not None,
        re.match(n2, line) is not None,
        re.match(n3, line) is not None,
        re.match(n4, line) is not None,
    ]

    if (state and any(positives)) or (not state and any(negatives)):
        return "match"
    elif (not state and any(positives)) or (state and any(negatives)):
        return "mismatch"
    elif re.match(r".*DefaultProbeLogger", line) is not None:
        return "wrong_probe"
    else:
        return "skip"


def check_probe_log(sequence, logfile="/tmp/np/stdout.log"):
    """ Checks probe output in log file.

    Keyword parameters:
    sequence - a list of tuples (probe id, state)
    logfile - path to a net_plumber log file
    """

    with open(logfile, 'r') as lf:
        log = iter(lf.read().split('\n'))
        line = log.next()

        for probe_id, state in sequence:
            while True:
                result = _check_probe_log_line(line, probe_id, state)

                if result == "match":
                    line = log.next()
                    break
                elif result == "mismatch":
                    return False
                elif result == "wrong_probe":
                    pass
                elif result == "skip_line":
                    pass

                try:
                    line = log.next()
                except StopIteration:
                    return False

    return True


def _check_generic_log(logger, logfile="/tmp/np/stdout.log"):
    with open(logfile, 'r') as lf:
        log = lf.read().split("\n")
        for line in log:
            if re.match(r".*%s" % logger, line) is not None:
                return True

        return False


def check_cycle_log(logfile="/tmp/np/stdout.log"):
    """ Check log output for loop.
    """
    return _check_generic_log("DefaultLoopDetectionLogger", logfile=logfile)


def check_unreach_log(logfile="/tmp/np/stdout.log"):
    """ Check log output for unreachable rule.
    """
    return _check_generic_log("DefaultUnreachDetectionLogger", logfile=logfile)


def check_shadow_log(logfile="/tmp/np/stdout.log"):
    """ Check log output for shadowed rule.
    """
    return _check_generic_log("DefaultShadowDetectionLogger", logfile=logfile)


def check_blackhole_log(logfile="/tmp/np/stdout.log"):
    """ Check log output for black hole.
    """
    return _check_generic_log("DefaultBlackholeDetectionLogger", logfile=logfile)


class TestRPC(unittest.TestCase):
    """ Test class for RPC tests.
    """

    def setUp(self):
        """ Fixture to prepare clean test environment.
        """

        os.system('scripts/start_np.sh')
        server = ('localhost', 1234)
        self.sock = connect_to_netplumber(*server)
        init(self.sock, 1)


    def tearDown(self):
        """ Fixture to destroy test environment.
        """

        reset_plumbing_network(self.sock)
        self.sock.close()
        os.system('scripts/stop_np.sh')


    def prepare_network(self, tables, links, sources, probes):
        """ Preparation function to set up a topology consisting of tables,
            links, sources, and probes.
        """

        nodes = {
            'tables' : [],
            'sources' : [],
            'probes' : []
        }

        for t_idx, t_ports, table in tables:
            nodes['tables'].append([])
            add_table(self.sock, t_idx, t_ports)

            for rule in table:
                result = add_rule(self.sock, t_idx, *rule)
                nodes['tables'][t_idx-1].append(result)

        for link in links:
            add_link(self.sock, *link)

        for source in sources:
            result = add_source(self.sock, *source)
            nodes['sources'].append(result)

        for probe in probes:
            result = add_source_probe(self.sock, *probe)
            nodes['probes'].append(result)

        return nodes


    def test_basic(self):
        """ Tests basic network with four tables, few rules, one source, and one
            probe.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2, 3], [
                (1, [1], [2], "xxxxxxx0", None, None),
                (2, [1], [3], "xxxxxxx1", None, None)
            ]),
            (2, [4, 5], [(1, [4], [5], "x"*8, None, None)]),
            (3, [6, 7], [(1, [6], [7], "x"*8, None, None)]),
            (4, [8, 9, 10], [(1, [8, 9], [10], "x"*8, None, None)])
        ]

        # (from_port, to_port)
        links = [(0, 1), (2, 4), (3, 6), (5, 8), (7, 9), (10, 11)]

        source = (["x"*8], None, [0])

        # ([ports], {universal, existential}, filter, test)
        probe = (
            [11],
            "universal",
            {
                "type":"header",
                "header":{
                    "list":["x"*8],
                    "diff":None
                }
            }, {
                "type":"path",
                "pathlets":[
                    {"type":"table", "table":2},
                    {"type":"port", "port":1},
                    {"type":"end"}
                ]
            }
        )

        init(self.sock, 1)

        nodes = self.prepare_network(tables, links, [source], [probe])

        # initial false probe condition
        probe_id = nodes["probes"][0]
        plogs = [(probe_id, False)]
        self.assertTrue(check_probe_log(plogs))

        # results in true probe condition
        remove_rule(self.sock, nodes['tables'][0][1])

        plogs.append((probe_id, True))
        self.assertTrue(check_probe_log(plogs))

        # results in false probe condition
        add_rule(self.sock, 1, 2, [1], [3], "xxxxxxx1", None, None)

        plogs.append((probe_id, False))
        self.assertTrue(check_probe_log(plogs))


    def test_advanced(self):
        """ Tests an advanced network with eight tables, several rules, a
            multitude of sources, and a complex probe.
        """

        tables = [
            (1, [11, 12, 13, 14, 19], [
                (1, [12, 13, 19], [11], "xxxx0110xxxxxx11", None, None),
                (2, [14], [12], "xxxx1001xxxxxxxx", None, None),
                (3, [14], [13], "xxxx1010xxxxxxxx", None, None)
            ]),
            (2, [21, 22, 23, 24, 29], [
                (1, [21, 23, 24, 29], [22], "xxxx0110xxxxxx11", None, None),
                (2, [21], [24], "xxxx1010xxxxxxxx", None, None)
            ]),
            (3, [31, 32, 33, 34, 35, 36, 39], [
                (1, [32, 34], [33], "xxxx1000xxxxxx11", None, None),
                (2, [31, 33, 34, 35, 36, 39], [32], "xxxx0110xxxxxx11", None, None),
                #(3, [31], [33], "xxxx1001xxxxxx11", "1"*16, "xxxx1000xxxxxx11"),
                (4, [31], [34], "xxxx1001xxxxxxxx", None, None)
            ]),
            (4, [41, 42, 43, 44, 45, 49], [
                (1, [41, 42, 44, 49], [43], "xxxx0111xxxxxx11", None, None),
                (2, [41], [45], "xxxx1010xxxxxxxx", None, None)
            ]),
            (5, [51, 52, 54, 53, 59], [
                (1, [52], [51], "xxxx1000xxxxxx11", None, None),
                (2, [51, 53, 59], [52], "xxxx0111xxxxxx11", None, None),
                (3, [51], [54], "xxxx1001xxxxxxxx", None, None)
            ]),
            (6, [61, 62, 63], [
                (1, [61, 62, 63], [63], "xxxx0110xxxxxx11", "1"*16, "01101000xxxxxx11"),
                (2, [61, 62, 63], [], "x"*16, None, None)
            ]),
            (7, [71, 72], [
                (1, [71, 72], [72], "xxxx0111xxxxxx11", "1"*16, "01111000xxxxxx11"),
                (2, [71, 72], [], "x"*16, None, None)
            ]),
            (8, [81, 89], [
                (1, [81], [89], "xxxx1000xxxxxx11", None, None),
                (2, [89], [81], "1000xxxxxxxxxxxx", None, None)
            ]),
        ]

        links = [
            (91, 19), (92, 29), (93, 39), (94, 49), (95, 59), (96, 14),
            (89, 99),
            (11, 61), (22, 62), (32, 63), (43, 71), (52, 72),
            (61, 11), (62, 22), (63, 32), (71, 43), (72, 52),
            (33, 81), (81, 33),
            (12, 31), (13, 21), (31, 12), (21, 13),
            (23, 36), (24, 41), (36, 23), (41, 24),
            (34, 51), (35, 42), (51, 34), (42, 35),
            (44, 53), (53, 44)
        ]

        sources = [
            (["00010110xxxxxx11"], None, [91]),
            (["00100110xxxxxx11"], None, [92]),
            (["00110110xxxxxx11"], None, [93]),
            (["01000111xxxxxx11"], None, [94]),
            (["01010111xxxxxx11"], None, [95]),
            (["x"*16], [
                "00010110xxxxxx11",
                "00100110xxxxxx11",
                "00110110xxxxxx11",
                "01000111xxxxxx11",
                "01010111xxxxxx11"
            ], [96])
        ]

        probe = (
            [99],
            "universal",
            {
                "type":"header",
                "header":{
                    "list":["xxxx1000xxxxxx11"],
                    "diff":None
                }
            }, {
                "type":"or",
                "arg1":{
                    "type":"path",
                    "pathlets":[
                        {"type":"table", "table":6},
                        {"type":"last_ports", "ports":[19, 29, 39, 49, 59]},
                    ]
                },
                "arg2":{
                    "type":"path",
                    "pathlets":[
                        {"type":"table", "table":7},
                        {"type":"last_ports", "ports":[19, 29, 39, 49, 59]},
                    ]
                }
            }
        )

        destroy(self.sock)
        init(self.sock, 2)

        nodes = self.prepare_network(tables, links, sources, [probe])

        # initial true probe condition
        probe_id = nodes["probes"][0]
        plogs = [(probe_id, True)]
        check_probe_log(plogs)

        # results in false probe condition
        remove_rule(self.sock, nodes['tables'][2][2])
        result = add_rule(
            self.sock, 3, 3, [31], [33], "xxxx1001xxxxxx11", "1"*16, "xxxx1000xxxxxx11"
        )

        plogs.append((probe_id, False))
        check_probe_log(plogs)

        # results in true probe condition
        remove_rule(self.sock, result)
        add_rule(self.sock, 3, 4, [31], [34], "xxxx1001xxxxxxxx", "1"*16, None)

        plogs.append((probe_id, True))
        check_probe_log(plogs)


    def test_cycle(self):
        """ Tests a simple network including a loop.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [(1, [1], [2], "x"*8, None, None)]),
            (2, [3, 4], []),
        ]

        links = [(2, 3), (4, 1), (99, 1)]

        sources = [(["x"*8], None, [99])]
        probes = []

        init(self.sock, 1)

        self.prepare_network(tables, links, sources, probes)

        self.assertFalse(check_cycle_log())

        # add new rule to close the cycle
        add_rule(self.sock, *(2, 1, [3], [4], "x"*8, None, None))

        self.assertTrue(check_cycle_log())


    def _test_slicing(self):
        """ Tests slicing in a simple network.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [(1, [1], [2], "xxxxx110", None, None)]),
            (2, [3, 4], [(1, [3], [4], "xxxxxx10", None, None)]),
            (3, [5, 6], [(1, [5], [6], "xxxxxxx0", None, None)])
        ]

        # (from_port, to_port)
        links = [(2, 3), (4, 5)]

        sources = []
        probes = []

        init(self.sock, 1)

        self.prepare_network(tables, links, sources, probes)

        # add new rule which will be put in new slice
        add_rule(self.sock, *(1, 2, [1], [2], "xxxxx111", None, None))

        # setup slice
        add_slice(self.sock, 1, *(["xxxxx1x1"], None))

        # add slice to introduce overlap
        add_slice(self.sock, 2, *(["xxxxx111"], None))
        remove_slice(self.sock, 2)

        result = add_rule(self.sock, *(1, 3, [1], [2], "xxxxxx1x", None, None))
        remove_rule(self.sock, result)

        # add rule to introduce leakage
        result = add_rule(self.sock, *(2, 2, [3], [4], "xxxxx111", "1"*8, "xxxxx110"))
        remove_rule(self.sock, result)

        # remove slice
        remove_slice(self.sock, 1)


    def _test_fw(self):
        """ Tests special firewall tables in a simple network.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [(1, [1], [2], "x"*8, None, None)]),
            (2, [3, 4], []),
            (3, [5, 6], [(1, [5], [6], "x"*8, None, None)])
        ]

        # (from_port, to_port)
        links = [(2, 3), (4, 5)]

        sources = [(["x"*8], None, [1])]
        probes = []

        init(self.sock, 1)

        nodes = self.prepare_network(tables, links, sources, probes)

        # add new rule which drops some traffic
        rule2 = add_fw_rule(self.sock, *(2, 2, [3], [], {"list":["x"*8], "diff":None}))
        self.assertTrue(rule2 != 0)

        # add new rule which allows some traffic
        rule1 = add_fw_rule(self.sock, *(2, 1, [3], [4], {"list":["xxxxxx11"], "diff":None}))
        self.assertTrue(rule1 != 0)

        # try to add normal rule to firewall,  should fail
        rule3 = add_rule(self.sock, *(2, 3, [3], [4], "x"*8, None, None))
        self.assertEqual(rule3, 0)

        # try to add firewall rule to normal table,  should fail
        rule4 = add_fw_rule(self.sock, *(1, 2, [1], [2], {"list":["x"*8], "diff":None}))
        self.assertEqual(rule4, 0)

        remove_fw_rule(self.sock, rule1)

        # try to add firewall rule to former normal table,  should succeed
        remove_rule(self.sock, nodes[0][0])
        rule5 = add_fw_rule(self.sock, 1, 1, [1], [2], {"list":["x"*8], "diff":None})
        self.assertTrue(rule5 != 0)

        remove_fw_rule(self.sock, rule2)

        # try to add normal rule to former firewall table,  should succeed
        rule6 = add_rule(self.sock, 2, 1, [3], [4], "x"*8, None, None)
        self.assertTrue(rule6 != 0)


    def _test_policy(self):
        """ Tests policy sources and probes in a simple network.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [(1, [1], [2], "x"*8, None, None)]),
            (2, [3, 4], []),
            (3, [5, 6], [(1, [5], [6], "x"*8, None, None)])
        ]

        # (from_port, to_port)
        links = [(2, 3), (4, 5)]

        sources = [(["x"*8], None, [99])]
        probes = []

        init(self.sock, 1)

        self.prepare_network(tables, links, sources, probes)

        # add policy probe node
        add_policy_probe(self.sock, [7])
        add_link(self.sock, 6, 7)
        add_link(self.sock, 99, 1)

        # add policy rules
        add_policy_rule(self.sock, 2, {"list":["xxxxxx11"], "diff":None}, "allow")
        add_policy_rule(self.sock, 2, {"list":["x"*8], "diff":None}, "deny")

        # add uncritical rule
        add_rule(self.sock, *(2, 1, [3], [4], "xxxxx111", None, None))

        # add critical rule
        add_rule(self.sock, *(2, 2, [3], [4], "xxxxxx11", "1"*8, "xxxxxx10"))

        print_plumbing_network(self.sock)


    def test_rule_unreachability(self):
        """ Tests rule reachability in a table.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [
                (1, [], [2], "10xxxxxx", None, None),
                (2, [], [2], "01xxxxxx", None, None),
                (3, [], [2], "00xxxxxx", None, None)
            ])
        ]

        init(self.sock, 1)
        self.prepare_network(tables, [], [], [])

        # add rule that completes the matching
        add_rule(self.sock, *(1, 4, [], [2], "11xxxxxx", None, None))

        self.assertFalse(check_unreach_log())

        # add unreachable rule
        add_rule(self.sock, *(1, 5, [], [2], "xx1xxxxx", None, None))

        self.assertTrue(check_unreach_log())


    def test_rule_shadowing(self):
        """ Tests rule shadowing in a table.
        """

        tables = [
            # (t_idx, t_ports, [(r_idx, [in_ports], [out_ports], match, mask, rw)])
            (1, [1, 2], [
                (1, [], [2], "10xxxxxx", None, None),
                (2, [], [2], "01xxxxxx", None, None),
                (3, [], [2], "00xxxxxx", None, None)
            ])
        ]

        init(self.sock, 1)
        self.prepare_network(tables, [], [], [])

        self.assertFalse(check_shadow_log())

        # add shadowed rule
        add_rule(self.sock, *(1, 4, [], [2], "011xxxxx", None, None))

        self.assertTrue(check_shadow_log())

        # add unshadowed rule
        add_rule(self.sock, *(1, 5, [], [2], "11xxxxxx", None, None))

        self.assertTrue(check_shadow_log())


    def test_expand(self):
        """ Tests rule expansion with a simple network.
        """

        rules = [generate_random_rule(i, [1, 2], [1, 2], 160) for i in range(0, 50)]

        tables = [
            (1, [1, 2], rules)
        ]

        links = [(99, 1)]
        sources = [(["x"*160], None, [99])]
        probes = []

        init(self.sock, 1)
        # initially expand wildcard vector size
        expand(self.sock, 160)

        self.prepare_network(tables, links, sources, probes)

        # double wildcard size
        expand(self.sock, 320)

        # add rule with new size
        rule = generate_random_rule(100, [1, 2], [1, 2], 320)
        add_rule(self.sock, 1, *rule)


if __name__ == '__main__':
    random.seed(0)
    unittest.main()
