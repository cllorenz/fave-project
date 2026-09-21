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

""" wl_cloud's FPL inventory and policy, derived from the dataset (C7, §1.9).

Every other workload in the suite states its policy as FPL and lets
PolicyTranslator produce the reachability matrix. wl_cloud did not: its checks
were built by hand from the six oracle queries, so the workload exercised FaVe's
ENGINE and skipped its POLICY layer entirely, and produced none of the
`reachable.json`/`cchecks.json` that `bench/apkeep_convergence.py` and
`bench/i2_structural_oracle.py` consume.

**What changed the shape of C7.** §1.9.4 assumed the inventory would have to be
FABRICATED -- a role per endpoint host, a service per port -- and measured the
cost: five policy rules became 60 checks of which six came from the oracle, so
~54 of 60 expectations would have been self-derived. That is no longer
necessary. `cloud-tf/README.txt` declares 25 services with their prefixes and a
26x26 authorisation matrix over them; `cloud_readme.py` parses it. The roles,
the services and the policy are all the dataset's, so the provenance runs the
other way: what is fabricated here is the *endpoint naming*, nothing else.

**Two policies, because the matrix and the data plane disagree** (owner
decision). `matrix/reach.txt` states the matrix as written and
`matrix/reach_public.txt` states it plus what the generator ACTUALLY
implemented. The delta between the two runs is the measurement:

  * A service in matrix row 25 is one the Internet may reach. The generator
    implements that as an ACL rule with NO SOURCE CONSTRAINT (43 of them) --
    which admits every source, not only the Internet. All 11 such services are
    therefore reachable from all 26 roles, while the matrix authorises 102 of
    those 275 cells.
  * So `matrix/reach.txt` is expected to REPORT VIOLATIONS, concentrated
    entirely on the 11 public services, and `matrix/reach_public.txt` is
    expected to be clean. A violation anywhere else, or a clean
    `matrix/reach.txt`, is a finding.

Under `matrix/` because they are GENERATED. The two files of the same name one
level up are the ORACLE phase's, hand-written and tracked -- a policy is an
intent and cannot be derived. Same names, opposite provenance, so they do not
share a directory.

This is the wl_ifi precedent (27 violations under `<->>`, none under `<-->` on
the same data plane): a policy is an INTENT, so the expected verdict is part of
the policy, not a property of the network.

**Operators, and why each is the one the data plane has.**

  * A service pair {i, j} is realised as TWO independent ACL rules, one per
    direction, each pinning its own destination port -- `dst in svc_j,
    dport = 331+j` and `dst in svc_i, dport = 331+i`. Two `--->` rules say
    exactly that. `<-->` would additionally OR in `sport` operands on both
    cells, which is a weaker claim than the data plane makes.
  * The Internet pairs are different, and `<-->` IS their shape. Inbound is the
    gateway's 19 destination-NAT rules plus the source-less ACL (`dport=331+i`);
    outbound is 14 source-NAT rules at the datacenter cores, matched on
    `sport = 331+i`. Destination port towards the provider, source port away
    from it -- which is precisely the direction resolution F2 added
    (§1.9.2). The services carrying egress NAT are exactly matrix row 25, a
    fourth independent confirmation that index 25 is the Internet.

`--->` with a service needs F1 (§1.9.1); `<-->` with a service needs F2. Before
those two fixes neither rule in this file would have compiled, which is why C7
sat behind them.
"""

from __future__ import annotations

import ast
import ipaddress

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from bench.wl_cloud.cloud_readme import CloudReadme, INTERNET_INDEX
from bench.wl_cloud.cloud_tf import node_name, read_match_field


#: FPL's own name for the external role. `bench/reach_csv_to_checks.py`
#: special-cases it by this spelling, so it is not ours to choose.
INTERNET_ROLE = 'Internet'

#: The model node the Internet role stands for -- the gateway for traffic in,
#: the egress sink for traffic out. One name, because a role maps to endpoint
#: NAMES and `cloud_preparation` attaches the generator and the probe of one
#: endpoint to the two different nodes.
INTERNET_ENDPOINT = 'internet'


def role_name(index: int) -> str:
    """ Matrix index -> FPL role name. """
    return INTERNET_ROLE if index == INTERNET_INDEX else 'svc%02d' % index


def _check_scenario(readme: CloudReadme) -> None:
    """ This module's one dataset-specific assumption, stated once.

    `role_name` reads `INTERNET_INDEX` off the module rather than off the
    README, which is right for `cloud/base` and wrong for any scenario with a
    different service count -- the other seven in the archive are a ready-made
    scaling axis (§1). The READER stays general (`CloudReadme.internet_index`
    is derived); the EMITTER says so out loud instead of silently naming a
    service role `Internet`.
    """
    if readme.internet_index != INTERNET_INDEX:
        raise ValueError(
            "this README declares %d services, so its Internet index is %d, "
            "not the %d `role_name` assumes. Emitting FPL for it would name "
            "service %d 'Internet' and lose the real external role."
            % (len(readme.services), readme.internet_index,
               INTERNET_INDEX, INTERNET_INDEX))


def service_name(readme: CloudReadme, index: int) -> str:
    """ Matrix index -> FPL service name, named by the port it IS.

    The port is the service's identity in both the data plane and the oracle
    (`03.sat.smt2` constrains `#x014C`), so naming the service anything else
    would put a translation step between the two.
    """
    return 'S%d' % readme.service_port(index)


def endpoint_name(index: int, leaf: int) -> str:
    """ The model endpoint for service `index` behind leaf ingress node `leaf`.

    A service spans one to nine leaf routers, and a leaf's /25 may belong to TWO
    services (README: `Services of router 1400125: set([2, 3])`), so neither
    half alone names an endpoint.
    """
    return '%s_svc%02d' % (node_name(leaf).rsplit('_', 1)[0], index)


def role_endpoints(readme: CloudReadme) -> Dict[str, List[str]]:
    """ {role name: [endpoint name, ...]} -- the `--inventory-mapping` a check
    set is expanded over.

    Derived from the README's `Services of router <id>` census, which
    `test_cloud_policy.py` asserts is identical to the mapping obtained
    independently by containing each leaf's /25 in a service prefix read off
    `network.tf`. Two derivations from two halves of the dataset agreeing on all
    64 pairs is what makes this a measurement rather than a transcription.
    """
    endpoints: Dict[str, List[str]] = {INTERNET_ROLE: [INTERNET_ENDPOINT]}

    for leaf in sorted(readme.router_services):
        for index in sorted(readme.router_services[leaf]):
            endpoints.setdefault(role_name(index), []).append(
                endpoint_name(index, leaf))

    return endpoints


def _role_block(readme: CloudReadme, index: int, hosts: Sequence[str]) -> str:
    prefixes = readme.services[index]

    # `ipv4` carries ONE prefix, and nine of the 25 services have two. Rather
    # than pick one and read as though that were the whole service, the
    # attribute is emitted only when it is the whole truth; the description
    # always lists every prefix. Nothing downstream consumes `ipv4` here (the
    # endpoint mapping does the address work), so this costs nothing but says
    # so out loud.
    # The prefixes are joined with SPACES. FPL's `value_text` is
    # `Word(alphanums + ".:/-_ ,")` (`fpl_grammar.py`), so a quoted value may
    # not contain a `+` -- and a role whose description does is not rejected,
    # it is SILENTLY SKIPPED, leaving a smaller inventory and a policy that
    # compiles. Eight of these 25 roles vanished that way on the first run.
    # See TODO item 15.
    lines = [
        'def role %s' % role_name(index),
        "    description = 'Cloud service %d on tcp/%d, public %s, prefixes %s'" % (
            index, readme.service_port(index), readme.service_address(index),
            ' '.join(prefixes)),
        '    hosts       = [%s]' % ', '.join("'%s'" % h for h in hosts),
    ]
    if len(prefixes) == 1:
        lines.append("    ipv4        = '%s'" % prefixes[0])
    lines.append('    offers %s' % service_name(readme, index))
    lines.append('end')

    return '\n'.join(lines)


def emit_inventory(readme: CloudReadme) -> str:
    """ `roles_and_services.txt`: 25 services and 25 service roles.

    `Internet` is NOT declared: FPL carries it as a built-in role, and
    redeclaring it would shadow the one `reach_csv_to_checks` recognises.

    The `def` keyword is deliberate. FPL accepts `define`, `def`, `describe` and
    `desc` interchangeably (`fpl_grammar.py`), but `inventorygen.py` matches
    only `def` when it extends a role with its `hosts` -- a coincidence that
    silently took wl_example from 10 checks to 32 when its source was
    normalised. Here the inventory and its reader are generated together, so the
    coincidence is removed rather than relied on: `cloud_inventory()` accepts
    every spelling.
    """
    _check_scenario(readme)
    endpoints = role_endpoints(readme)

    blocks = [
        '\n'.join([
            'def service %s' % service_name(readme, index),
            "    protocol = 'tcp'",
            '    port     = %d' % readme.service_port(index),
            'end',
        ]) for index in sorted(readme.services)
    ]

    blocks.extend(
        _role_block(readme, index, endpoints[role_name(index)])
        for index in sorted(readme.services)
    )

    return '\n\n'.join(blocks) + '\n'


def public_services(readme: CloudReadme) -> List[int]:
    """ The services matrix row 25 says the Internet may reach.

    Read off the README, not off `network.tf`, so this module needs only the
    one input -- but the two agree exactly, and `test_cloud_policy.py` pins
    that against the 43 source-less ACL rules and the 19 gateway NAT rules.
    """
    return [
        index for index in sorted(readme.services)
        if readme.permits(INTERNET_INDEX, index)
    ]


def published_prefix(model: Any, readme: CloudReadme) -> Dict[int, str]:
    """ {service: the prefix the gateway ACTUALLY publishes to the Internet}.

    `network.tf` carries one destination-NAT rule per (service, datacenter), so
    a service whose prefixes span two datacenters gets two -- with a
    byte-identical match. Hassel resolves that by priority and the LATER rule is
    inert (`tf.py` `_find_influences` + the `affected_by` subtraction in
    `apply_rewrite_rule`), which is why only the first is read here. Reducing
    the file that way yields exactly the 11 rules the dataset's Datalog
    encoding carries; `test_cloud_encodings_agree.py` pins it.
    """
    published: Dict[int, str] = {}

    for rule in model.rules_at(readme.internet_port):
        if rule.action != 'rw':
            continue
        service = read_match_field(
            rule.match, 'packet.upper.dport') - readme.service_port_base
        if service in published:
            continue                          # shadowed by the earlier rule
        published[service] = read_match_field(
            rule.rewrite, 'packet.ipv4.destination')

    return published


def unpublished_endpoints(
        readme: CloudReadme, model: Any, blocks: Dict[int, str]
) -> List[str]:
    """ Endpoints of a PUBLIC service that the gateway does not publish.

    A public service spanning two datacenters is published from one of them
    (see `published_prefix`), so the other datacenter's hosts are unreachable
    from the Internet although matrix row 25 authorises the service. `blocks`
    maps a leaf ingress node to the /25 it owns.
    """
    published = published_prefix(model, readme)
    out = []

    for leaf in sorted(readme.router_services):
        for service in sorted(readme.router_services[leaf]):
            if service not in published:
                continue                      # private: no gateway rule at all
            if _within(blocks[leaf], published[service]):
                continue
            out.append(endpoint_name(service, leaf))

    return out


def _within(prefix: str, container: str) -> bool:
    return ipaddress.ip_network(prefix).subnet_of(ipaddress.ip_network(container))


def expected_violations(
        readme: CloudReadme, model: Any, blocks: Dict[int, str], policy: str
) -> Set[Tuple[str, str]]:
    """ The (source endpoint, probe endpoint) pairs a run of `policy` SHOULD
    report -- derived from the data, never counted off a previous run.

    Two populations, and they point in opposite directions:

      * **must-REACH failures**, in BOTH policies: the Internet against an
        unpublished endpoint of a public service. Three of them, and they are
        the dataset being LESS permissive than its own matrix (TODO item 16).
      * **must-NOT-reach violations**, in the `matrix` policy only: every denied
        cell into a public service, because the generator implements "public" as
        an ACL rule with no source constraint and so admits every source. The
        `public` policy states those cells as permitted, which is what empties
        this half. 1,312 of them, the dataset being MORE permissive.

    A run that reports a different set is a finding either way: the point of
    deriving the expectation is that "3 violations" and "the RIGHT 3 violations"
    stop being the same sentence (TODO item 1s).
    """
    endpoints = role_endpoints(readme)
    expected = set(
        (INTERNET_ENDPOINT, probe)
        for probe in unpublished_endpoints(readme, model, blocks)
    )

    if policy != 'matrix':
        return expected

    for target in public_services(readme):
        for source in sorted(readme.services):
            if readme.permits(source, target):
                continue
            expected.update(
                (src, dst)
                for src in endpoints[role_name(source)]
                for dst in endpoints[role_name(target)]
            )

    return expected


def emit_policy(readme: CloudReadme, public: bool = False) -> str:
    """ `reach.txt`, or `reach_public.txt` when `public` is set.

    Ordered pairs are emitted as `--->` and Internet pairs as `<-->`; see the
    module docstring for why each operator is the one the data plane has.
    """
    _check_scenario(readme)
    lines = ['def policies (default: deny)']

    lines.append('    # The README\'s 26x26 ACL matrix, one rule per 1-cell.')
    lines.append(
        '    # Service pairs are two unidirectional rules because the data '
        'plane has two')
    lines.append('    # rules, each pinning its own destination port.')

    for source in sorted(readme.services):
        targets = [
            target for target in sorted(readme.services)
            if readme.permits(source, target)
        ]
        for target in targets:
            lines.append('    %s ---> %s.%s' % (
                role_name(source), role_name(target),
                service_name(readme, target)))

    lines.append('')
    lines.append(
        '    # Internet pairs: inbound DNAT + source-less ACL on the service\'s')
    lines.append(
        '    # destination port, outbound SNAT on the same port as SOURCE port.')

    for index in public_services(readme):
        lines.append('    %s <--> %s.%s' % (
            INTERNET_ROLE, role_name(index), service_name(readme, index)))

    if public:
        lines.append('')
        lines.append(
            '    # WHAT THE GENERATOR ACTUALLY IMPLEMENTED. "The Internet may')
        lines.append(
            '    # reach service j" became an ACL rule with no source match, so')
        lines.append(
            '    # EVERY role reaches it -- including the %d the matrix denies.'
            % _unauthorised_cells(readme))
        lines.append(
            '    # Stating that here is what makes this policy\'s run clean.')

        for index in public_services(readme):
            for source in sorted(readme.services):
                if readme.permits(source, index):
                    continue
                lines.append('    %s ---> %s.%s' % (
                    role_name(source), role_name(index),
                    service_name(readme, index)))

    lines.append('end')

    return '\n'.join(lines) + '\n'


def _unauthorised_cells(readme: CloudReadme) -> int:
    return sum(
        1 for index in public_services(readme)
        for source in readme.services
        if not readme.permits(source, index)
    )


def cloud_inventory(inventory: str) -> Dict[str, List[str]]:
    """ {role: [endpoint, ...]} read back out of an emitted inventory file.

    The role -> endpoint mapping that `reach_csv_to_checks --inventory-mapping`
    consumes. It is READ BACK from the FPL rather than returned from
    `role_endpoints` directly, so that the file the translator parses and the
    mapping the checks are expanded over cannot drift apart -- which is the
    wl_ifi defect of TODO item 14, one generation path disagreeing with
    another.

    Unlike `wl_up/inventorygen.py` this accepts every `def` synonym the grammar
    does; see `emit_inventory`.
    """
    roles: Dict[str, List[str]] = {INTERNET_ROLE: [INTERNET_ENDPOINT]}
    role: Optional[str] = None

    for line in inventory.splitlines():
        token = line.split()
        if len(token) == 3 and token[0] in ('def', 'define', 'describe', 'desc'):
            role = token[2] if token[1] == 'role' else None
        elif role and len(token) > 2 and token[0] == 'hosts':
            roles.setdefault(role, []).extend(
                ast.literal_eval(' '.join(token[2:])))

    return roles
