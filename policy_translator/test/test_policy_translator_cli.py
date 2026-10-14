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

""" `policy_translator.py`, the command line every workload generator and demo
script calls (`fave/test/gen_wl_*_inputs.sh`), run in-process.

Driven through `runpy.run_path(..., run_name='__main__')` with a patched
`sys.argv`, so the `__main__` guard is exercised the way a shell runs it and
coverage sees the module. Inputs are COMMITTED policies only
(`examples/ifi-policy.txt`, `wl_shadow`'s and `wl_generic_fw`'s inventory and
policy pairs); every output goes to a temporary directory.

Pinned, per output flag:

  * `-c` writes `Policy.roles_to_csv`, for one combined file and for an
    inventory + policy pair (the two-file form the generators use);
  * `-i` the inventory mapping, `--roles` the roles JSON, `-p` the prosa,
    `-fw` the iptables script, `-w` the HTML table;
  * `--strict --no-internet -r CSV` replaces the policy by a report CSV
    (`PolicyBuilder.replace_policy_with_csv`): `X` allows, `_` ignores;
  * `-d` / `-t` raise the log level;
  * an unreadable input and a `PolicyException` both EXIT 1 (TODO item 15:
    every caller checks the exit status through `os.system`).
"""

import contextlib
import io
import json
import logging
import os
import runpy
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy_logger import PT_LOGGER


_PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_PT)
_SCRIPT = os.path.join(_PT, 'policy_translator.py')

_IFI = [os.path.join(_PT, 'examples', 'ifi-policy.txt')]
_SHADOW = [
    os.path.join(_REPO, 'fave', 'bench', 'wl_shadow', 'inventory.txt'),
    os.path.join(_REPO, 'fave', 'bench', 'wl_shadow', 'policy.txt'),
]
_GENERIC_FW = [
    os.path.join(_REPO, 'fave', 'bench', 'wl_generic_fw', 'default',
                 'inventory.txt'),
    os.path.join(_REPO, 'fave', 'bench', 'wl_generic_fw', 'default',
                 'policy.txt'),
]
_FML = [os.path.join(_PT, 'examples', 'fml-paper-policy.txt')]


class TestPolicyTranslatorCli(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self._level = PT_LOGGER.level

    def tearDown(self):
        PT_LOGGER.setLevel(self._level)
        self._tmp.cleanup()

    def _path(self, name):
        return os.path.join(self.tmp, name)

    def _run(self, argv):
        """ Runs the script as `__main__`; returns (stdout, exit code). """
        out = io.StringIO()
        saved = sys.argv
        sys.argv = ['policy_translator.py'] + argv
        code = 0
        try:
            with contextlib.redirect_stdout(out):
                runpy.run_path(_SCRIPT, run_name='__main__')
        except SystemExit as exc:
            code = exc.code
        finally:
            sys.argv = saved
        return out.getvalue(), code

    def _read(self, name):
        with open(self._path(name), 'r') as f:
            return f.read()

    def test_csv_of_a_combined_file(self):
        _out, code = self._run(['-c', '-o', self._path('r.csv')] + _IFI)
        self.assertEqual(code, 0)
        lines = self._read('r.csv').splitlines()
        self.assertEqual(lines[0], ",AdminNetz,Intern,Internet,Sekretariate,"
                         "TrustedClients,UntrustedClients,Webserver")
        self.assertEqual(lines[1], "AdminNetz,X,X,X,X,X,X,X")
        self.assertEqual(lines[4], "Sekretariate,(X),X,X,X,,,"
                         "(protocol:tcp;port:80|protocol:tcp;port:443)")
        self.assertEqual(len(lines), 8)

    def test_csv_of_an_inventory_and_policy_pair(self):
        _out, code = self._run(['-c', '-o', self._path('g.csv')] + _GENERIC_FW)
        self.assertEqual(code, 0)
        self.assertEqual(self._read('g.csv'), (
            ",Internet,Office,WebServer\n"
            "Internet,X,(X),(protocol:tcp;port:80)\n"
            "Office,X,X,(protocol:tcp;port:80|protocol:tcp;port:22)\n"
            "WebServer,(X),(X),X\n"))

    def test_inventory_mapping(self):
        _out, code = self._run(['-i', '-o', self._path('m.json')] + _IFI)
        self.assertEqual(code, 0)
        mapping = json.loads(self._read('m.json'))
        self.assertEqual(mapping['AdminNetz'],
                         {'hosts': ['admin.cs.uni-potsdam.de'], 'vlan': 1})
        # Server's `vlan = 5` is pushed down onto its member Webserver.
        self.assertEqual(mapping['Webserver']['vlan'], 5)
        self.assertIn('Internet', mapping)
        self.assertNotIn('All', mapping)

    def test_roles_json(self):
        _out, code = self._run(['--roles', self._path('roles.json')] + _IFI)
        self.assertEqual(code, 0)
        roles = json.loads(self._read('roles.json'))
        self.assertEqual([r['name'] for r in roles], [
            'AdminNetz', 'Intern', 'Internet', 'Sekretariate',
            'TrustedClients', 'UntrustedClients', 'Webserver'])
        self.assertEqual(roles[0]['attributes']['vlan'], 1)

    def test_prosa(self):
        _out, code = self._run(['-p', '-o', self._path('p.txt')] + _SHADOW)
        self.assertEqual(code, 0)
        self.assertEqual(self._read('p.txt'), (
            "# Policy Translator -- prose output\n"
            "#\n"
            "# Ground rule: everything is forbidden that is not allowed here "
            "(default: deny).\n"
            "# 1 rule.\n"
            "\n"
            "A <--> B\n"
            "\tA and B may reach each other.\n"))

    def test_iptables(self):
        _out, code = self._run(['-fw', '-o', self._path('f.sh')] + _SHADOW)
        self.assertEqual(code, 0)
        lines = self._read('f.sh').splitlines()
        self.assertIn("iptables -P FORWARD DROP", lines)
        self.assertEqual(lines[-4:], [
            'ip6tables -A FORWARD -s 0::0/0 -d 0::0/0 -m conntrack --ctstate '
            'NEW,NOTRACK -m comment --comment "A to B" -j ACCEPT',
            'ip6tables -A FORWARD -s 0::0/0 -d 0::0/0 -m conntrack --ctstate '
            'NEW,NOTRACK -m comment --comment "B to A" -j ACCEPT',
            'ip6tables -A FORWARD -s 0::0/0 -d 0::0/0 -m conntrack --ctstate '
            'NEW -m comment --comment "A to A" -j ACCEPT',
            'ip6tables -A FORWARD -s 0::0/0 -d 0::0/0 -m conntrack --ctstate '
            'NEW -m comment --comment "B to B" -j ACCEPT',
        ])

    def test_html(self):
        _out, code = self._run(['-w', '-o', self._path('r.html')] + _IFI)
        self.assertEqual(code, 0)
        html = self._read('r.html')
        self.assertTrue(html.startswith("<!DOCTYPE html>\n"))
        self.assertIn("<title>Policy Translator -- HTML output</title>", html)
        self.assertIn("<td class='label' colspan='7'>TARGET</td>", html)
        # Role attributes in the header tooltips.
        self.assertIn("hosts = ['admin.cs.uni-potsdam.de']<br/>vlan = 1<br/>",
                      html)
        # `<->>` leaves a conditional way back; its condition is in the tip.
        self.assertIn("state = RELATED,ESTABLISHED<br/>", html)
        self.assertIn("ODER<br/>", html)
        self.assertIn("provider = Webserver<br/>", html)
        self.assertNotIn("NICHT", html)  # only under `default: allow`
        self.assertTrue(html.endswith("</html>"))

    def test_strict_no_internet_with_report_csv(self):
        report = self._path('report.csv')
        with open(report, 'w') as f:
            f.write(",A,B\nA,X,_\nB,_,X\n")
        _out, code = self._run([
            '--strict', '--no-internet', '-r', report,
            '-w', '-o', self._path('s.html')] + _SHADOW)
        self.assertEqual(code, 0)
        html = self._read('s.html')
        self.assertNotIn('Internet', html)
        rows = [
            line.strip() for line in html.split("<h3>")[0].splitlines()
            if line.strip().startswith("<td class='role'>")
            or line.strip() in ("<td class='allowed'>&#x2705;</td>",
                                "<td>&nbsp;</td>",
                                "<td class='disallowed'>&#x274c;</td>")
        ]
        # The report replaced `A <--> B`: diagonal allowed, the rest ignored.
        self.assertEqual(rows, [
            "<td class='role'>A</td>",
            "<td class='allowed'>&#x2705;</td>",
            "<td>&nbsp;</td>",
            "<td class='role'>B</td>",
            "<td>&nbsp;</td>",
            "<td class='allowed'>&#x2705;</td>",
        ])

    def test_debug_and_trace_raise_the_log_level(self):
        null = logging.NullHandler()
        saved = PT_LOGGER.handlers[:]
        PT_LOGGER.handlers = [null]
        try:
            _out, code = self._run(['-d', '--roles', self._path('d.json')]
                                   + _SHADOW)
            self.assertEqual((code, PT_LOGGER.level), (0, logging.DEBUG))
            _out, code = self._run(['-t', '--roles', self._path('t.json')]
                                   + _SHADOW)
            self.assertEqual((code, PT_LOGGER.level), (0, logging.TRACE))
        finally:
            PT_LOGGER.handlers = saved

    def test_unreadable_input_exits_1(self):
        out, code = self._run(['-c', '-o', self._path('x.csv'),
                               self._path('missing.txt')])
        self.assertEqual(code, 1)
        self.assertEqual(out, "Error: could not read the input file(s).\n")
        self.assertFalse(os.path.exists(self._path('x.csv')))

    def test_policy_exception_exits_1(self):
        out, code = self._run(['-c', '-o', self._path('x.csv')] + _FML)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith(
            "Error: Service ARP: 'arp' is not an IP protocol."), out)
        self.assertFalse(os.path.exists(self._path('x.csv')))

    def test_no_internet_with_a_policy_naming_internet_exits_1(self):
        out, code = self._run(['--no-internet', '-c', '-o',
                               self._path('x.csv')] + _IFI)
        self.assertEqual(code, 1)
        self.assertEqual(out, "Error: Role Internet is unknown.\n")


if __name__ == '__main__':
    unittest.main()
