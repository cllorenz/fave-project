#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" Equivalence test: libnetplumber (in-process) vs net_plumber over JSON-RPC.

Drives an identical model through BOTH backends -- the jsonrpc module against a
live net_plumber, and LibTransport over an in-process LibNetPlumber (the same
jsonrpc-compatible interface, so one build sequence feeds both) -- and asserts:
 1. identical node ids,
 2. byte-identical engine-state dumps (dump_plumbing_network + dump_flows),
 3. identical compliance verdicts (RPC parsed from the log; lib read in-process).

Needs a live backend -> e2e tier. See APKEEP_BACKEND.md (P1).
"""

import unittest

import os
import json
import time
import tempfile

import netplumber.jsonrpc as jsonrpc
from netplumber.jsonrpc import connect_to_netplumber, NET_PLUMBER_DEFAULT_PORT
from netplumber.jsonrpc import init, destroy, reset_plumbing_network, stop
from netplumber.lib_transport import LibTransport
from netplumber.lib_adapter import libnetplumber
from reporting.reporter import _parse_log_line, Log

LEN = 1  # header length in bytes (8 bits); matches the 8-bit vectors below

NP_LOG = '/dev/shm/np/stdout.log'


def build(T, socks):
    """ Build one model through a jsonrpc-compatible transport T (the jsonrpc
    module, or a LibTransport). Exercises tables, rules with match/mask/rewrite,
    wiring, a source with a {list,diff} header space, and a probe. Returns the
    (source, probe) node ids. """
    T.add_table(socks, 1, [1, 2])
    T.add_table(socks, 2, [3, 4])
    # rule with mask + rewrite (high nibble rewritten); match-all so the source
    # reaches the probe (giving a non-trivial compliance verdict to compare).
    T.add_rule(socks, 1, 0, [1], [2], "xxxxxxxx", "11110000", "1010xxxx")
    T.add_rule(socks, 2, 0, [3], [4], "xxxxxxxx", "", "")
    T.add_link(socks, 2, 3)
    src = T.add_source(socks, 1000, ["11xxxxxx"], ["11110000"], [100])
    T.add_link(socks, 100, 1)
    prb = T.add_source_probe(socks, [300], "existential", "", None, {"type": "true"}, 2000)
    T.add_link(socks, 4, 300)
    return src, prb


def _canon(obj):
    """ Order-independent canonical form: sort dict keys and lists recursively. """
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return sorted((_canon(x) for x in obj),
                      key=lambda v: json.dumps(v, sort_keys=True))
    return obj


def _load_dump(directory):
    out = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            with open(os.path.join(directory, name)) as handle:
                out[name] = _canon(json.load(handle))
    return out


@unittest.skipIf(libnetplumber is None, "libnetplumber not built")
class TestLibNetPlumberEquivalence(unittest.TestCase):
    """ libnetplumber must behave identically to net_plumber over JSON-RPC. """

    def setUp(self):
        os.system('mkdir -p /dev/shm/np')
        os.system('rm -f %s' % NP_LOG)
        os.system('scripts/start_np.sh')
        self.socks = [connect_to_netplumber('localhost', NET_PLUMBER_DEFAULT_PORT)]
        destroy(self.socks)  # start_np leaves it initialized; reset to clean

    def tearDown(self):
        try:
            reset_plumbing_network(self.socks)
        except Exception:
            pass
        stop(self.socks)

    def test_state_and_compliance_equivalence(self):
        # --- RPC backend: live net_plumber ---
        init(self.socks, LEN)
        rpc_src, rpc_prb = build(jsonrpc, self.socks)
        rpc_dir = tempfile.mkdtemp()
        jsonrpc.dump_plumbing_network(self.socks, rpc_dir)
        jsonrpc.dump_flows(self.socks, rpc_dir)

        # --- lib backend: in-process LibNetPlumber ---
        lib = libnetplumber.LibNetPlumber(LEN)
        lib_t = LibTransport(lib)
        lib_src, lib_prb = build(lib_t, None)
        lib_dir = tempfile.mkdtemp()
        lib_t.dump_plumbing_network(None, lib_dir)
        lib_t.dump_flows(None, lib_dir)

        # 1. identical node ids (both use the passed ids)
        self.assertEqual((rpc_src, rpc_prb), (lib_src, lib_prb))

        # 2. identical engine-state dumps
        rpc_dump = _load_dump(rpc_dir)
        lib_dump = _load_dump(lib_dir)
        self.assertEqual(sorted(rpc_dump), sorted(lib_dump), "dump file sets differ")
        for name in rpc_dump:
            self.assertEqual(rpc_dump[name], lib_dump[name],
                             "engine-state dump differs in %s" % name)

        # 3. identical compliance verdicts: a "must not reach" rule the source
        #    violates (it does reach). RPC -> log; lib -> in-process.
        rule = {rpc_prb: [(rpc_src, False, None)]}
        jsonrpc.check_compliance(self.socks, rule)
        time.sleep(0.2)  # let log4cxx flush
        rpc_viol = set()
        with open(NP_LOG) as handle:
            for raw in handle:
                event = _parse_log_line(raw.rstrip().split())
                if event and event[0] == Log.Compliance:
                    _, negated, frm, to_, _cond = event
                    rpc_viol.add((int(frm), int(to_), negated))

        lib_t.check_compliance(None, rule)
        lib_viol = set((s, d, v) for (s, d, v, _c) in lib.get_compliance_results())

        self.assertTrue(lib_viol, "expected a compliance violation")
        # RPC's `negated` flag == the rule's `valid` (the logger prints '!' iff
        # valid), so the tuples are directly comparable.
        self.assertEqual(rpc_viol, lib_viol, "compliance verdicts differ")


if __name__ == '__main__':
    unittest.main()
