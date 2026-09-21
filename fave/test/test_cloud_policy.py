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

""" wl_cloud's generated FPL, end to end (C7, CLOUD_BENCH_PLAN.md §1.9.6).

The sibling of `test_wl_{up,ifi,example}_policy_artifacts.py`, and it pins the
same invariant: what the workload verifies is what its sources produce. wl_cloud
differs in where those sources come from -- they are GENERATED from
`cloud-tf/README.txt` rather than written -- so the chain has one more link and
every link is checked:

    README.txt --(cloud_readme)--> matrix
               --(cloud_policy)--> FPL inventory + policy
               --(PolicyTranslator)--> reachability.csv
               --(reach_csv_to_checks)--> checks.json

**The link that needed a test most** is the third. A role whose FPL block fails
to parse is not rejected -- it is SILENTLY SKIPPED, and the translator exits 0
with a smaller inventory and a policy that compiles against what is left. Eight
of these 25 roles vanished that way the first time this ran, because their
description contained a `+` and FPL's `value_text` does not admit one. The
check set was 40% smaller and nothing said so. See TODO item 15;
`test_a_plus_in_a_description_silently_loses_the_role` pins the defect itself so
that fixing the grammar turns this file red and points at the item.

**Two roles can name the same machines.** Services 2 and 3 are both
10.0.17.0/25. That is the reason for the generator's source-port constraint and
for `reach_csv_to_checks --deny-per-service`, and both are asserted here.
"""

import csv
import ipaddress
import re
import json
import os
import subprocess
import sys
import tempfile
import unittest

from bench.wl_cloud.cloud_policy import (
    INTERNET_ENDPOINT,
    INTERNET_ROLE,
    cloud_inventory,
    emit_inventory,
    emit_policy,
    endpoint_name,
    expected_violations,
    public_services,
    published_prefix,
    role_endpoints,
    role_name,
    service_name,
    unpublished_endpoints,
)
from bench.wl_cloud.cloud_endpoints import derive_endpoints
from bench.wl_cloud.cloud_preparation import (
    build_model,
    leaf_blocks,
    role_endpoints as model_endpoints,
)
from bench.wl_cloud.cloud_readme import INTERNET_INDEX, read_readme
from bench.wl_cloud.cloud_tf import classify_nodes, parse_tf


_FAVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREFIX = os.path.join(_FAVE, 'bench', 'wl_cloud')
_README = os.path.join(_PREFIX, 'cloud-tf', 'README.txt')
_TF = os.path.join(_PREFIX, 'cloud-tf', 'network.tf')

#: FPL's `value_text`, verbatim from `policy_translator/fpl_grammar.py`. A
#: quoted attribute value may contain only these.
_VALUE_TEXT = set(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:/-_ ,')


def _translate(inventory_text, policy_text, tmp, strict=True):
    """ Run PolicyTranslator over generated sources; return (csv rows, roles). """
    inventory = os.path.join(tmp, 'roles_and_services.txt')
    policy = os.path.join(tmp, 'reach.txt')
    matrix = os.path.join(tmp, 'reachability.csv')
    roles = os.path.join(tmp, 'roles.json')

    with open(inventory, 'w') as out:
        out.write(inventory_text)
    with open(policy, 'w') as out:
        out.write(policy_text)

    subprocess.run(
        [sys.executable, '../policy_translator/policy_translator.py']
        + (['--strict'] if strict else [])
        + ['--csv', '--out', matrix, '--roles', roles, inventory, policy],
        cwd=_FAVE, check=True, capture_output=True,
        env=dict(os.environ, PYTHONPATH=_FAVE))

    with open(matrix) as raw:
        rows = list(csv.reader(raw))
    with open(roles) as raw:
        return rows, json.load(raw)


@unittest.skipUnless(os.path.isfile(_README), "wl_cloud raw scenario not present")
class TestCloudPolicy(unittest.TestCase):
    """ The generated FPL, and what the translator makes of it. """

    @classmethod
    def setUpClass(cls):
        cls.readme = read_readme(_README)
        cls.inventory_text = emit_inventory(cls.readme)
        cls.policy_text = emit_policy(cls.readme)
        cls.public_text = emit_policy(cls.readme, public=True)

        cls._tmp = tempfile.TemporaryDirectory(prefix='wl_cloud_policy_')
        cls.rows, cls.roles = _translate(
            cls.inventory_text, cls.policy_text, cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _cells(self, rows):
        header = rows[0][1:]
        return {
            (row[0], header[i]): cell
            for row in rows[1:] for i, cell in enumerate(row[1:])
        }

    # -- the inventory survives the translator -------------------------------

    def test_every_generated_role_reaches_the_translator(self):
        """ THE GUARD. A role whose block fails to parse is dropped in silence,
        so the count is asserted rather than trusted (TODO item 15). """
        self.assertEqual(len(self.roles), 26)
        self.assertEqual(
            sorted(role['name'] for role in self.roles),
            sorted([INTERNET_ROLE]
                   + [role_name(i) for i in self.readme.services]))

    def test_every_generated_role_offers_exactly_its_own_service(self):
        offered = {
            role['name']: [s['name'] for s in role.get('services', [])]
            for role in self.roles
        }
        self.assertEqual(offered[INTERNET_ROLE], [])
        for index in self.readme.services:
            self.assertEqual(
                offered[role_name(index)], [service_name(self.readme, index)])

    def test_every_emitted_attribute_value_is_expressible_in_fpl(self):
        """ Forward-looking half of the `+` defect: no generated value may use
        a character FPL's `value_text` does not admit. Catches the next such
        character before it silently deletes a role. """
        for line in self.inventory_text.splitlines():
            for value in re.findall(r"'([^']*)'", line):
                bad = sorted(set(value) - _VALUE_TEXT)
                self.assertEqual(
                    bad, [],
                    "%r in %r is outside FPL's value_text" % (bad, line))

    def test_a_plus_in_a_description_silently_loses_the_role(self):
        """ PINS THE DEFECT, not the desired behaviour (TODO item 15).

        FPL's `value_text` admits no `+`, and the parser neither raises nor
        warns: the role simply is not there afterwards. When the grammar is
        fixed, or the drop made loud, this test goes red -- which is the point.
        """
        source = (
            "def service S331\n    protocol = 'tcp'\n    port     = 331\nend\n"
            "\n"
            "def role keeps\n    description = 'a, b'\n"
            "    hosts       = ['h1']\n    offers S331\nend\n"
            "\n"
            "def role loses\n    description = 'a + b'\n"
            "    hosts       = ['h2']\n    offers S331\nend\n"
        )
        policy = "def policies (default: deny)\n    keeps ---> keeps.S331\nend\n"

        with tempfile.TemporaryDirectory(prefix='fpl_plus_') as tmp:
            _rows, roles = _translate(source, policy, tmp)

        names = [role['name'] for role in roles]
        self.assertIn('keeps', names)
        self.assertNotIn(
            'loses', names,
            "a `+` in a description no longer loses the role -- TODO item 15 "
            "may be fixed; invert this test and drop the workaround in "
            "cloud_policy._role_block")

    # -- the matrix survives the translator ----------------------------------

    def test_the_matrix_compiles_cell_for_cell(self):
        """ All 676 cells: permitted exactly where the README permits, and each
        condition naming the PROVIDER's port in the right direction.

        Destination port towards the provider, source port away from it -- so
        the Internet column carries `sport` and every service column carries
        `port`. That asymmetry is the data plane's (inbound DNAT vs outbound
        SNAT), and it is what `<-->` resolves.
        """
        cells = self._cells(self.rows)
        self.assertEqual(len(cells), 26 * 26)

        for i in self.readme.roles:
            for j in self.readme.roles:
                cell = cells[(role_name(i), role_name(j))]

                if not self.readme.permits(i, j):
                    self.assertEqual(
                        cell, '', "(%d, %d) is denied but compiled to %r"
                        % (i, j, cell))
                    continue

                expected = '(protocol:tcp;sport:%d)' % self.readme.service_port(i) \
                    if j == INTERNET_INDEX \
                    else '(protocol:tcp;port:%d)' % self.readme.service_port(j)
                self.assertEqual(
                    cell, expected,
                    "(%d, %d) compiled to %r" % (i, j, cell))

    def test_no_condition_leaks_the_provider_marker(self):
        """ F1's regression (§1.9.1): `provider` is a qualifier, not an OR
        operand, and must never appear in the CSV. """
        for cell in self._cells(self.rows).values():
            self.assertNotIn('provider', cell)

    # -- role -> model endpoints ---------------------------------------------

    def test_the_readme_and_the_transfer_function_agree_on_every_endpoint(self):
        """ TWO derivations of the same 64 (service, leaf) pairs.

        One reads the README's `Services of router <id>` census; the other
        contains each leaf's /25 -- taken from its datacenter core's routing
        table -- in a declared service prefix. They agree on all 40 leaves,
        which is what makes the endpoint mapping a measurement rather than a
        transcription.
        """
        with open(_TF, 'r') as raw:
            model = classify_nodes(parse_tf(raw))

        blocks = leaf_blocks(model)
        self.assertEqual(len(blocks), 40)

        derived = {}
        for leaf, block in blocks.items():
            derived[leaf] = sorted(
                index for index, prefixes in self.readme.services.items()
                if any(
                    ipaddress.ip_network(block).subnet_of(
                        ipaddress.ip_network(prefix))
                    for prefix in prefixes))

        stated = {
            leaf: sorted(services)
            for leaf, services in self.readme.router_services.items()
        }
        self.assertEqual(stated, derived)
        self.assertEqual(sum(len(v) for v in stated.values()), 64)

    def test_the_inventory_round_trips_through_the_emitted_fpl(self):
        """ `inventory.json` is read back OUT of the file the translator read,
        so the two cannot drift -- TODO item 14's defect. """
        self.assertEqual(
            cloud_inventory(self.inventory_text), role_endpoints(self.readme))

    def test_the_fpl_names_exactly_the_endpoints_the_model_builds(self):
        """ The check set addresses `source.<name>`/`probe.<name>`, so a name
        the FPL invents and the model does not build is a check against
        nothing -- which passes. """
        with open(_TF, 'r') as raw:
            rules = parse_tf(raw)
        model = classify_nodes(rules)

        endpoints = model_endpoints(
            model, self.readme.router_services, self.readme.service_port,
            endpoint_name, INTERNET_ENDPOINT)

        self.assertEqual(
            sorted(e.name for e in endpoints),
            sorted(n for names in role_endpoints(self.readme).values()
                   for n in names))
        self.assertEqual(len(endpoints), 65)

    def test_every_service_endpoint_generator_pins_its_source_port(self):
        """ Without it, a leaf's two co-located services are indistinguishable
        at the ACL and each inherits the other's permissions. """
        with open(_TF, 'r') as raw:
            model = classify_nodes(parse_tf(raw))

        endpoints = model_endpoints(
            model, self.readme.router_services, self.readme.service_port,
            endpoint_name, INTERNET_ENDPOINT)

        shared = [
            leaf for leaf, services in self.readme.router_services.items()
            if len(services) > 1
        ]
        self.assertTrue(shared, "no leaf hosts two services; the constraint "
                                "this test exists for is not exercised")

        for endpoint in endpoints:
            if endpoint.name == INTERNET_ENDPOINT:
                self.assertEqual(endpoint.fields, [])
                continue
            index = int(endpoint.name.rsplit('_svc', 1)[1])
            self.assertIn(
                'tcp_src=%d' % self.readme.service_port(index), endpoint.fields)
            self.assertEqual(len(endpoint.fields), 2)

    def test_co_located_services_share_a_block_and_differ_in_port(self):
        """ The property the whole disambiguation rests on, stated once. """
        for leaf, services in self.readme.router_services.items():
            if len(services) < 2:
                continue
            ports = {self.readme.service_port(s) for s in services}
            self.assertEqual(
                len(ports), len(services),
                "leaf %s hosts %s without distinct ports" % (leaf, services))

    def test_the_model_builds_one_probe_per_role_endpoint(self):
        with open(_TF, 'r') as raw:
            rules = parse_tf(raw)
        model = classify_nodes(rules)
        endpoints = model_endpoints(
            model, self.readme.router_services, self.readme.service_port,
            endpoint_name, INTERNET_ENDPOINT)

        built = build_model(rules, model, role_members=endpoints)
        self.assertEqual(len(built['sources']['devices']), 65)
        self.assertEqual(len(built['probes']['devices']), 65)
        self.assertEqual(
            sorted(name for name, _t, _f in built['sources']['devices']),
            sorted(e.source_device for e in endpoints))
        self.assertEqual(
            sorted(dev[0] for dev in built['probes']['devices']),
            sorted(e.probe_device for e in endpoints))

    def test_a_plain_endpoint_is_a_role_member_too(self):
        """ `build_model` has ONE role-member path, and both kinds travel it.

        `cloud_endpoints.Endpoint` (the §1.9 phase) and `RoleEndpoint` (this
        one) are read only through `inject`, `fields` and `observe`, so an
        Endpoint is the special case: one sink, no header constraint. Pinned
        here because the two were separate code paths before the branches met,
        and a second path is how the two phases drift apart.
        """
        with open(_TF, 'r') as raw:
            rules = parse_tf(raw)
        model = classify_nodes(rules)
        endpoints = derive_endpoints(model)

        one = endpoints['internet']
        self.assertEqual((one.inject, one.observe, one.fields),
                         (one.tx, [one.rx], []))

        built = build_model(rules, model, role_members=[one])
        self.assertEqual(
            [dev[0] for dev in built['sources']['devices']],
            [one.source_device])
        self.assertEqual(
            [dev[0] for dev in built['probes']['devices']], [one.probe_device])

    # -- the derived expectation ---------------------------------------------

    def test_the_gateway_publishes_one_prefix_of_each_split_service(self):
        """ Hassel's shadowing, read as "what the Internet can actually reach".

        The identical-match second rule is inert, so a service spanning two
        datacenters is published from exactly one. See TODO item 16 and
        `test_cloud_encodings_agree.py`, which checks the reduction against the
        dataset's own Datalog encoding.
        """
        with open(_TF, 'r') as raw:
            model = classify_nodes(parse_tf(raw))

        published = published_prefix(model, self.readme)
        self.assertEqual(sorted(published), public_services(self.readme))

        for service, prefix in published.items():
            self.assertIn(prefix, self.readme.services[service])

    def test_the_unpublished_endpoints_are_the_three_split_services(self):
        with open(_TF, 'r') as raw:
            model = classify_nodes(parse_tf(raw))

        unpublished = unpublished_endpoints(
            self.readme, model, leaf_blocks(model))

        self.assertEqual(
            sorted(unpublished),
            ['dc4_leaf0_svc11', 'dc4_leaf4_svc01', 'dc4_leaf6_svc23'])

        # each names a service that IS public and DOES span two prefixes --
        # otherwise the derivation would be finding something else
        for name in unpublished:
            service = int(name.rsplit('_svc', 1)[1])
            self.assertTrue(self.readme.permits(INTERNET_INDEX, service))
            self.assertEqual(len(self.readme.services[service]), 2)

    def test_the_expected_violation_sets_are_what_the_runs_report(self):
        """ The numbers §1.9.6 quotes, derived rather than counted off a run.

        `public` expects only the three must-reach failures of item 16;
        `matrix` expects those plus every denied cell into a public service,
        which is the half `reach_public.txt` states away.
        """
        with open(_TF, 'r') as raw:
            model = classify_nodes(parse_tf(raw))
        blocks = leaf_blocks(model)

        public = expected_violations(self.readme, model, blocks, 'public')
        matrix = expected_violations(self.readme, model, blocks, 'matrix')

        self.assertEqual(len(public), 3)
        self.assertEqual(len(matrix), 1315)
        self.assertTrue(public < matrix)
        self.assertEqual(len(matrix - public), 1312)

        # every `public` expectation is the Internet against an endpoint
        self.assertEqual({src for src, _dst in public}, {INTERNET_ENDPOINT})

        # and every EXTRA `matrix` expectation targets a public service, which
        # is the property that makes the 1,312 a statement about the generator
        # rather than a number
        endpoint_service = {
            name: index
            for index in self.readme.services
            for name in role_endpoints(self.readme)[role_name(index)]
        }
        for _src, dst in matrix - public:
            self.assertIn(endpoint_service[dst], public_services(self.readme))

    # -- the two policies ----------------------------------------------------

    def test_the_matrix_policy_states_every_authorised_pair_once(self):
        """ 226 ordered 1-cells as 204 `--->` rules and 11 `<-->` rules. """
        rules = [
            line.strip() for line in self.policy_text.splitlines()
            if '--->' in line or '<-->' in line
        ]
        forward = [r for r in rules if '--->' in r]
        both = [r for r in rules if '<-->' in r]

        self.assertEqual(len(forward), 204)
        self.assertEqual(len(both), 11)
        self.assertEqual(
            len(forward) + 2 * len(both), len(self.readme.authorised_pairs()))
        self.assertEqual(len(rules), len(set(rules)), "a rule is stated twice")

        for rule in both:
            self.assertTrue(rule.startswith('%s <-->' % INTERNET_ROLE))

    def test_the_public_policy_adds_exactly_the_unauthorised_public_cells(self):
        """ The delta between the two policies IS the finding: the generator's
        source-less ACL rule admits every role, not only the Internet. """
        def _rules(text):
            return {
                line.strip() for line in text.splitlines()
                if '--->' in line or '<-->' in line
            }

        added = _rules(self.public_text) - _rules(self.policy_text)
        self.assertEqual(_rules(self.policy_text) - _rules(self.public_text), set())

        expected = {
            '%s ---> %s.%s' % (
                role_name(i), role_name(j), service_name(self.readme, j))
            for j in public_services(self.readme)
            for i in self.readme.services
            if not self.readme.permits(i, j)
        }
        self.assertEqual(added, expected)
        # 184, not 173: the DIAGONAL is included. A source-less ACL rule admits
        # service j's own hosts too, and the matrix denies that cell like any
        # other -- 11 public services, so 173 cross-role cells plus 11 self
        # cells. The matrix run reports exactly these 184 role pairs.
        self.assertEqual(len(added), 184)

    def test_the_public_policy_compiles_to_a_superset_of_the_matrix(self):
        with tempfile.TemporaryDirectory(prefix='wl_cloud_public_') as tmp:
            rows, roles = _translate(self.inventory_text, self.public_text, tmp)

        self.assertEqual(len(roles), 26)
        strict_cells = self._cells(self.rows)
        public_cells = self._cells(rows)

        for key, cell in strict_cells.items():
            if cell:
                self.assertEqual(public_cells[key], cell, "cell %s changed" % (key,))

        filled = sum(1 for c in public_cells.values() if c)
        self.assertEqual(filled, 226 + 184)


if __name__ == '__main__':
    unittest.main()
