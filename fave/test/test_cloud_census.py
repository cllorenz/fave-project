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

""" `WORKLOAD.md` still describes the workload (CLOUD_BENCH_PLAN.md §1.8).

A benchmark's census -- how many devices, how many ACL rules, which header
fields -- is the part of its documentation that rots silently. Nothing breaks
when it stops being true, and a stale "86 devices" reads exactly as
authoritative as a measured one. §1.8's principle is that a figure with no
derivation behind it is an `oracle.json` waiting to happen, so the document is
generated and this pins it.

Two kinds of assertion, and the second is the one that matters:

  * `test_document_is_current` compares the tracked file byte for byte with a
    fresh derivation from the vendored raw data. It catches an edit by hand and
    a reading that drifted, and it is worth exactly as much as the derivation.

  * everything else asserts the derivation against facts established some OTHER
    way -- the partition being total, the two `CLOUD_BENCH_PLAN.md` figures this
    module corrects, and the classifiers refusing what they do not recognise.
    A census that only agrees with itself is the failure mode being avoided,
    so the cross-checks do not go through `census()`.
"""

import os
import unittest

from bench.wl_cloud.cloud_census import (
    DOCUMENT,
    RAW,
    CensusError,
    build,
    census,
    device_class,
    endpoint_class,
    rule_function,
)
from bench.wl_cloud.cloud_readme import read_readme
from bench.wl_cloud.cloud_tf import classify_nodes, node_name, parse_tf


def _load():
    with open(os.path.join(RAW, 'network.tf')) as handle:
        rules = parse_tf(handle)
    return rules, classify_nodes(rules)


class TestCloudCensusDocument(unittest.TestCase):
    """ The tracked document is what the raw data says today. """

    def test_document_is_current(self):
        with open(DOCUMENT) as handle:
            tracked = handle.read()

        self.assertEqual(
            tracked, build(),
            "WORKLOAD.md no longer matches the raw data it claims to describe. "
            "It is GENERATED -- regenerate it with `python3 -m "
            "bench.wl_cloud.cloud_census` from fave/ rather than editing it, "
            "and read the diff before committing: a change here means the "
            "reading of the dataset moved.")

    def test_document_is_tracked(self):
        """ Unlike the derived JSON, this one is committed -- it is prose. """
        self.assertTrue(os.path.isfile(DOCUMENT))


class TestCloudCensusPartitions(unittest.TestCase):
    """ The taxonomies are total and disjoint, counted without `census()`. """

    @classmethod
    def setUpClass(cls):
        cls.rules, cls.model = _load()
        cls.census = census(
            cls.rules, cls.model,
            read_readme(os.path.join(RAW, 'README.txt')))

    def test_every_rule_has_exactly_one_function(self):
        functions = [rule_function(rule) for rule in self.rules]
        self.assertEqual(len(functions), len(self.rules))
        self.assertLessEqual(
            set(functions), {'deny', 'nat', 'acl-permit', 'forward'})

    def test_the_function_grid_accounts_for_every_device_rule(self):
        """ No rule is dropped or counted twice on its way into the table. """
        on_devices = sum(
            len(self.model.rules_at(node)) for node in self.model.devices)
        self.assertEqual(sum(self.census['grid'].values()), on_devices)
        self.assertEqual(self.census['device_rules'], on_devices)

    def test_devices_plus_endpoints_are_every_node(self):
        classified = (
            sum(self.census['devices'].values())
            + sum(self.census['endpoints'].values()))
        self.assertEqual(classified, self.census['nodes_total'])

    def test_device_rules_plus_source_rules_are_every_rule(self):
        self.assertEqual(
            self.census['device_rules'] + self.census['source_rules'],
            len(self.rules))

    def test_classifiers_refuse_what_they_do_not_recognise(self):
        """ A default bucket would count a misread node as though it were read. """
        for name in ('dc0_spine3', 'internet', '', 'dc0_leaf0_host0'):
            self.assertRaises(CensusError, device_class, name)
        for name in ('dc0_core', 'internet_gw', 'nonsense'):
            self.assertRaises(CensusError, endpoint_class, name)


class TestCloudCensusCorrectsThePlan(unittest.TestCase):
    """ The two CLOUD_BENCH_PLAN.md figures the document overrides.

    Both are asserted from the raw data directly, so the document's claim that
    the plan is wrong is itself checked rather than asserted.
    """

    @classmethod
    def setUpClass(cls):
        cls.rules, cls.model = _load()

    def test_the_data_plane_is_1741_rules_not_1722(self):
        """ §1.3 subtracted the gateway's rules AND counted it as a table. """
        gateway = next(
            node for node in self.model.devices
            if node_name(node) == 'internet_gw')
        gateway_rules = len(self.model.rules_at(gateway))

        on_devices = sum(
            len(self.model.rules_at(node)) for node in self.model.devices)
        injectors = sum(
            len(self.model.rules_at(node)) for node in self.model.sources)

        self.assertEqual(on_devices, 1741)
        self.assertEqual(len(self.rules) - injectors, 1741)
        # and the figure the plan used, reconstructed, is short by exactly the
        # gateway's own rules -- which is the whole of the mistake.
        self.assertEqual(len(self.rules) - injectors - gateway_rules, 1722)

    def test_85_and_86_differ_by_the_gateway_alone(self):
        """ §1.2's criterion misfiles a device whose every rule drops or NATs. """
        in_ports, out_ports = set(), set()
        for rule in self.rules:
            in_ports.update(rule.in_ports)
            out_ports.update(rule.out_ports)

        both_sides = in_ports & out_ports
        self.assertEqual(len(both_sides), 85)
        self.assertEqual(len(self.model.devices), 86)
        self.assertEqual(
            [node_name(n) for n in sorted(set(self.model.devices) - both_sides)],
            ['internet_gw'])

        gateway = next(
            node for node in self.model.devices
            if node_name(node) == 'internet_gw')
        self.assertTrue(all(
            rule.is_drop or rule.action == 'rw'
            for rule in self.model.rules_at(gateway)))


if __name__ == '__main__':
    unittest.main()
