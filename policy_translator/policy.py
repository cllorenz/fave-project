# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens
# List of co-authors:
#    Claas Lorenz <claas_lorenz@genua.de>
#    Benjamin Plewka <plewka@uni-potsdam.de>


# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import ast
import copy
import json

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from policy_exceptions import NameTakenException, InvalidAttributeException, InvalidValueException
from policy_exceptions import ServiceUnknownException, RoleUnknownException
from policy_exceptions import NoServicesOfferedException
from policy_exceptions import UnrenderableConditionException
from policy_exceptions import UnknownProtocolException
from policy_exceptions import PortWithoutProtocolException
from policy_logger import PT_LOGGER

#: The builtin role standing for everything outside the administrative boundary
#: of whoever writes the policy. It OFFERS EVERY DECLARED SERVICE: a rule naming
#: a service on the Internet side cannot be expected to declare that the
#: Internet offers it, since nobody administers the Internet. "Declared" rather
#: than "anything at all" is deliberate -- a service's conditions come from its
#: inventory entry, never from its name, so accepting an undeclared service name
#: would mean inventing attributes from a table of well-known ports. HTTP would
#: then always mean 80, an HTTP service on port 123 would be unsayable, and a
#: custom service could not be expressed at all. See
#: policy_translator/test/test_internet_services.py.
INTERNET_ROLE = "Internet"

#: The condition a `<->>` rule puts on the return direction. It is the one
#: condition the CSV spells as a bare `X` rather than as `field:value` pairs:
#: its value contains a comma, which a comma-separated cell cannot carry, and
#: `X` is the spelling every consumer of the matrix already knows.
RELATED_CONDITION = {'state': 'RELATED,ESTABLISHED'}


class Policy(object):
    """Represents a security policy for a computer network. Contains roles,
    services and reachability policies.

    Attributes:
        roles: A dictionary of Role and Superrole objects that group together
            a number of hosts. Contains at least the role named "Internet".
        services: A dictionary of Service objects that represent a service
            accessible using a certain port and protocol.
        policies: A dictionary of ReachabilityPolicy objects that specify
            whether one role should be able to reach another and under what
            conditions.
        default_policy: A boolean value indicating whether the default policy
            is "deny" (False) or "allow" (True).
    """

    # XXX: make interface configurable or use more sane default
    default_roles = {INTERNET_ROLE : [('interface', '"fw.generic.eth1"')]}

    def __init__(self, strict: bool = False, use_internet: bool = True) -> None:
        """Initialises a Policy object with role "Internet", no services, no
        policies and default policy "deny"."""

        self.roles: Dict[str, Role] = {}
        self.services: Dict[str, Service] = {}
        self.policies: Dict[Tuple[str, str], Any] = {}
        # DECLARATION ORDER, via a dict used as an ordered set. This is the
        # author's own list of rules and `to_prosa` renders it back to them, so
        # a reader comparing the prosa against the policy file expects the two
        # to read in the same order -- the same division item 18 drew, where a
        # wildcard's services keep the order someone wrote and a traversal
        # nobody wrote is sorted. As a `set` it also reordered itself between
        # runs, which is TODO item 20's defect in a third place.
        #
        # Still deduplicating: writing one rule twice is a redundancy, not two
        # rules, and the set said so. `dict` keeps the first occurrence.
        self.raw_policies: Dict[Any, None] = {}
        self.default_policy = False
        for role, attributes in [
                (r, a) for r, a in  self.default_roles.items() if (
                    use_internet or r != 'Internet'
                )
        ]:
            self.add_role(role)
            tmp = self.roles[role]
            for key, value in attributes:
                tmp.add_attribute(key, value)
        self.strict = strict

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Policy):
            return NotImplemented

        return all([
            self.roles == other.roles,
            self.services == other.services,
            self.policies == other.policies,
            self.default_policy == other.default_policy
        ])

    def add_role(self, name: str) -> None:
        """Adds a role.

        Args:
            name: A string.

        Raises:
            NameTakenException: A role or service with this name already exists.
        """
        if not name in self.default_roles and (
                self.role_exists(name) or self.service_exists(name)
        ):
            raise NameTakenException(name)

        self.roles[name] = Role(name, self)

    def add_superrole(self, name: str) -> None:
        """Adds a superrole.

        Args:
            name: A string.

        Raises:
            NameTakenException: A role or service with this name already exists.
        """

        if (self.role_exists(name)) or (self.service_exists(name)):
            raise NameTakenException(name)

        self.roles[name] = Superrole(name, self)

    def add_service(self, name: str) -> None:
        """Adds a service.

        Args:
            name: A string.

        Raises:
            NameTakenException: A role or service with this name already exists.
        """

        if (self.role_exists(name)) or (self.service_exists(name)):
            raise NameTakenException(name)

        self.services[name] = Service(name, self)

    def role_exists(self, name: str) -> bool:
        """Returns whether a role with the given name exists or not.

        Args:
            name: A string.

        Returns:
            A boolean.
        """

        return name in list(self.roles.keys())

    def service_exists(self, name: str) -> bool:
        """Returns whether a service with the given name exists or not.

        Args:
            name: A string.

        Returns:
            A boolean.
        """

        return name in list(self.services.keys())

    def policy_exists(self, role_from: str, role_to: str) -> bool:
        """Returns whether a reachability policy concerning the two given roles
        exists or not.

        Args:
            role_from: A string.
            role_to: A string.

        Returns:
            A boolean.
        """

        return (role_from, role_to) in list(self.policies.keys())


    def conditional_policy_exists(self, role_from: str, role_to: str) -> bool:
        """Returns whether a conditional reachability policy concerning the two
        given roles exists or not.

        Args:
            role_from: A string.
            role_to: A string.

        Returns:
            A boolean.
        """

        return self.policy_exists(role_from, role_to) and \
            self.policies[(role_from, role_to)].conditions != []


    def add_reachability_policy(self, role_from: str, role_to: str, service_to: Optional[str] = None, condition: Optional[Dict[str, Any]] = None) -> None:
        """Adds or updates a reachability policy concerning two roles.

        If one or both of the roles are superroles, reachability policies will
        be added or updated for all combinations of their subroles -- except,
        in strict mode, the combinations where a subrole would reach itself:
        strict mode requires an explicit rule for self-reachability, and no
        rule over a superrole names a member reaching itself.

        If a service is specified, its attributes will be added as conditions.
        If the service specified is "*" (wildcard), all services of the reached
        role will be considered. If the reached role is a superrole, all
        subservices will be considered. They are added as conditions separately
        (multiple "OR" operands).

        Args:
            role_from: A string.
            role_to: A string.
            service_to: A string.
            condition: A dictionary.

        Raises:
            RoleUnknownException: At least one of the roles is not known.
            ServiceUnknownException: Service is not known to at least one role.
        """

        if not self.role_exists(role_from):
            raise RoleUnknownException(role_from)
        if not self.role_exists(role_to):
            raise RoleUnknownException(role_to)

        # Strict mode promises that self-reachability needs an explicit FPL rule.
        # Expanding a superrole over its own members would break that promise
        # silently: `DMZ <--> DMZ` puts a diagonal on every member, and
        # `AdminConsole <->> DMZ` does so for the one member it names, although
        # neither rule mentions any member reaching itself. A diagonal is only
        # written when both endpoints name the same *atomic* role.
        literal_diagonal = (
            role_from == role_to
            and self.roles[role_from].get_roles() == [role_from]
        )

        # `provider` names the side that OFFERS the service, and it is a
        # QUALIFIER of the service condition rather than a condition of its own:
        # renderers read it off the same dict as `port` to decide whether the
        # service is identified by its destination port (traffic TO the
        # provider) or its source port (traffic FROM it). Seeding `conditions`
        # with it made it a separate OR operand, which disabled that choice
        # everywhere and leaked `provider:<role>` into the CSV. See
        # test/test_service_direction.py.
        provider = condition.get('provider') if condition else None
        standalone = {
            k: v for k, v in condition.items() if k != 'provider'
        } if condition else {}

        for role_from_ in self.roles[role_from].get_roles():
            for role_to_ in self.roles[role_to].get_roles():
                if self.strict and role_from_ == role_to_ and not literal_diagonal:
                    continue

                conditions = [copy.deepcopy(standalone)] if standalone else []

                # A service belongs to its provider. Without one named, the
                # reached role is the provider, which is the plain forward case.
                owner = provider if provider is not None else role_to_

                services: Iterable[str]
                if service_to == "*":
                    # DECLARATION ORDER, and deliberately so. This used to
                    # collect the names into a `set`, whose iteration order
                    # follows string hashing -- randomised per process -- so
                    # the same policy compiled to two different spellings of
                    # the same alternative across runs, and an artifact
                    # compared byte for byte would fail intermittently with no
                    # visible cause (TODO item 18).
                    #
                    # The order chosen is the one the `offers` lines were
                    # written in (for `Internet`, the order of the `def
                    # service` blocks), because that is the order a reader of
                    # the inventory expects to see in the matrix; alphabetical
                    # would be equally reproducible but would reorder the
                    # writer's list for no reason. `get_services()` returns
                    # dicts, which preserve insertion order, so that order
                    # survives; `dict.fromkeys` deduplicates a service offered
                    # by several subroles while keeping its first position.
                    services = list(dict.fromkeys(
                        service
                        for offered in self.roles[owner].get_services().values()
                        for service in offered
                    ))

                    # A `.*` that resolves to nothing is REFUSED, not obeyed.
                    # The empty list is how FPL spells an unconditional rule
                    # and `update_conditions` lets it overpower every other
                    # condition, so the silent reading of `Y.*` over a role
                    # offering nothing was "reach Y by any traffic at all" --
                    # wider than what was written, and it also erased the
                    # conditions an earlier rule had set (TODO item 19).
                    if not services:
                        raise NoServicesOfferedException(owner)
                else:
                    services = [service_to] if service_to is not None else []

                for service in services:
                    if self.roles[owner].offers_service(service):
                        attributes = copy.deepcopy(self.services[service].attributes)
                        if provider is not None:
                            attributes['provider'] = provider
                        conditions.append(attributes)
                    else:
                        raise ServiceUnknownException(service, owner)

                if not self.policy_exists(role_from_, role_to_):
                    self.policies[(role_from_, role_to_)] = ReachabilityPolicy(
                        role_from_, role_to_, self, conditions
                    )
                else:
                    self.policies[(role_from_, role_to_)].update_conditions(conditions)


    def add_ignore_policy(self, role_from: str, role_to: str) -> None:

        if not self.role_exists(role_from):
            raise RoleUnknownException(role_from)
        if not self.role_exists(role_to):
            raise RoleUnknownException(role_to)

        self.policies[(role_from, role_to)] = IgnorePolicy(role_from, role_to, self)


    def clear_reachability(self) -> None:
        """ Resets the reachability policy while keeping the roles and inventory.
        """
        self.policies = {}


    def set_default_policy(self, default: str) -> None:
        """Sets the default policy.

        Args:
            default: Either "deny" or "allow".
        """

        if default == "deny":
            self.default_policy = False
        elif default == "allow":
            self.default_policy = True


    def get_atomic_roles_rec(self, roles: Iterable[str]) -> Set[str]:
        res = set([])
        for role in roles:
            r_tmp = self.roles[role]
            if isinstance(r_tmp, Superrole):
                res.update(self.get_atomic_roles_rec(r_tmp.subroles))
            else:
                res.add(role)

        return res


    def get_atomic_roles(self) -> Set[str]:
        return self.get_atomic_roles_rec(self.roles)


    def to_html(self) -> str:
        """Creates a reachability table in HTML format using roles (not
        superroles) as table headings.

        Role attributes as well as reachability conditions are presented in
        boxes that are visible when performing a mouseover over the table cells.

        Returns:
            A string that is an HTML file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.items() if type(role) == Role}

        html_list = [
            "<!DOCTYPE html>\n",
            "<html>\n",
            "\t<head>\n",
            "\t\t<meta charset='UTF-8'>\n",
            "\t\t<title>Policy Translator -- HTML output</title>\n",
            "\t\t<link rel='stylesheet' href='policies.css'>\n",
            "\t</head>\n",
            "\t<body>\n",
            "\t\t<table>\n",
            "\t\t\t<tr>\n",
            "\t\t\t\t<td></td>\n",
            "\t\t\t\t<td></td>\n",
            "\t\t\t\t<td class='label' colspan='%d'>TARGET</td>\n" % len(roles),
            "\t\t\t</tr>\n",
            "\t\t\t<tr>\n",
            "\t\t\t\t<td></td>\n",
            "\t\t\t\t<td></td>\n"
        ]

        for role in sorted(roles):
            html_list.append((
                "\t\t\t\t<td class='role_rotate'>\n"
                "\t\t\t\t\t<div class='tooltip_rotated'>\n"
                "\t\t\t\t\t\t" + role + "\n"
                "\t\t\t\t\t\t<span class='tooltiptext_unrotated'>"
            ))
            for key, value in self.roles[role].attributes.items():
                html_list.append("%s = %s<br/>" % (key, value))
            html_list.append((
                "</span>\n"
                "\t\t\t\t\t</div>\n"
                "\t\t\t\t</td>\n"
            ))

        html_list.append("\t\t\t</tr>\n")

        for counter, role_from in enumerate(sorted(roles)):
            html_list.append("\t\t\t<tr>\n")

            if counter == 0:
                html_list.append(
                    "\t\t\t\t<td class='label' rowspan='%d'>Q<br/>U<br/>E<br/>L<br/>L<br/>E</td>\n" % len(roles)
                )

            html_list.append("\t\t\t\t<td class='role'>%s</td>\n" % role_from)

            for role_to in sorted(roles):
                if role_from == "Internet" and role_to == "Internet":
                    html_list.append("\t\t\t\t<td>&nbsp;</td>\n")
                elif (role_from, role_to) in self.policies and self.policies[(role_from, role_to)].conditions:
                    html_list.append((
                        "\t\t\t\t<td class='cond_allowed'>\n"
                        "\t\t\t\t\t<div class='tooltip'>\n"
                        "\t\t\t\t\t\t&#x2705;\n"
                        "\t\t\t\t\t\t<span class='tooltiptext'>"
                    ))
                    if self.default_policy:
                        html_list.append("NICHT<br/>(</br>")
                    for cond_counter, cond in enumerate(self.policies[(role_from, role_to)].conditions):
                        if not cond_counter == 0:
                            html_list.append("ODER<br/>")
                        for key, value in cond.items():
                            html_list.append("%s = %s<br/>" % (key, value))
                    if self.default_policy:
                        html_list.append(")")
                    html_list.append((
                        "</span>\n"
                        "\t\t\t\t\t</div>\n"
                        "\t\t\t\t</td>\n"
                    ))
                elif self.default_policy ^ ((role_from, role_to) in self.policies and isinstance(self.policies[(role_from, role_to)], ReachabilityPolicy)):
                    html_list.append("\t\t\t\t<td class='allowed'>&#x2705;</td>\n")
                elif self.default_policy ^ ((role_from, role_to) in self.policies and isinstance(self.policies[(role_from, role_to)], IgnorePolicy)):
                    html_list.append("\t\t\t\t<td>&nbsp;</td>\n")
                else:
                    html_list.append("\t\t\t\t<td class='disallowed'>&#x274c;</td>\n")

            html_list.append("\t\t\t</tr>\n")

        html_list.append((
            "\t\t</table>\n\n"
            "\t\t<br/><br/>\n"
            "\t\t<h3>Legend:</h3>\n\n"
            "\t\t<table>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='allowed'>&#x2705;</td>\n"
            "\t\t\t\t<td>Allowed</td>\n"
            "\t\t\t</tr>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='cond_allowed'>&#x2705;</td>\n"
            "\t\t\t\t<td>Conditionally allowed (mouse over for details)</td>\n"
            "\t\t\t</tr>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='disallowed'>&#x274c;</td>\n"
            "\t\t\t\t<td>Not allowed</td>\n"
            "\t\t\t</tr>\n"
            "\t\t</table>\n"
            "\t</body>\n"
            "</html>"
        ))

        return "".join(html_list)

    def vlans_to_csv(self) -> str:
        """Creates a reachability table in CSV format using VLANs as table
        headings.

        Returns:
            A string that is a CSV file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.items() if type(role) == Role}
        vlans, csv_list = set(), []

        for _name, role in roles.items():
            if "vlan" in role.attributes:
                vlans.add(role.attributes["vlan"])

        reachable = {(id, id) for id in vlans}

        for policy in self.policies:
            from_role = self.roles[policy[0]]
            to_role = self.roles[policy[1]]
            if ("vlan" in from_role.attributes) and ("vlan" in to_role.attributes):
                vlan_from = from_role.attributes["vlan"]
                vlan_to = to_role.attributes["vlan"]
                reachable.add((vlan_from, vlan_to))

        for vlan in sorted(vlans):
            csv_list.append(",%d" % vlan)

        csv_list.append("\n")

        for vlan_from in sorted(vlans):
            csv_list.append("%d" % vlan_from)
            for vlan_to in sorted(vlans, reverse=False):
                if (vlan_from, vlan_to) in reachable:
                    csv_list.append(",X")
                else:
                    csv_list.append(",")
            csv_list.append("\n")

        return "".join(csv_list)

    def _condition_to_csv(self, cond: Dict[str, Any], role_from: str) -> str:
        """One condition as CSV text, with the service's direction resolved.

        `provider` is internal bookkeeping: it names the side that offers the
        service, which is what decides whether the service is identified by its
        destination port or its source port. Traffic TOWARDS the provider is
        addressed to the service (`port`); traffic FROM it is the return
        direction and carries the service as its SOURCE port (`sport`). The
        same choice `to_iptables` makes with `--dport`/`--sport`.

        The marker itself does not belong in the CSV -- a consumer of the
        matrix should read a header field, not have to know who offers what --
        so it is dropped once it has been used.
        """
        if cond == RELATED_CONDITION:
            return 'X'

        provider = cond.get('provider')
        reverse = provider is not None and role_from in set(
            self.roles[provider].get_roles()
        )

        fields = []
        for field, value in cond.items():
            if field == 'provider':
                continue
            if field == 'port' and reverse:
                field = 'sport'
            if ',' in str(value):
                raise UnrenderableConditionException(field, value)
            fields.append('%s:%s' % (field, value))

        return ';'.join(fields)


    def roles_to_csv(self) -> str:
        """Creates a reachability table in CSV format using role names as table
        headings.

        Returns:
            A string that is a CSV file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.items() if type(role) == Role}
        csv_list = ['']
        csv_list.extend([',' + r for r in sorted(roles)])
        csv_list.append('\n')

        for role_from in sorted(roles):
            csv_list.append(role_from)
            for role_to in sorted(roles):
                if self.conditional_policy_exists(role_from, role_to):
                    # ONE PATH, and `X` is just the operand the stateful
                    # condition renders as. The stateful case used to
                    # short-circuit the whole cell, so a pair carrying
                    # RELATED,ESTABLISHED *and* a service lost the service:
                    # `examples/ifi-policy.txt`'s Internet -> Webserver printed
                    # `(X)` while the policy held ports 80 and 443. Worse than
                    # cosmetic, because `bench/reach_csv_to_checks.py` reads
                    # `(X)` as "related traffic and NOTHING else" and emits a
                    # must-NOT-reach check for everything unrelated -- the
                    # opposite of what such a cell permits.
                    #
                    # A cell whose only condition is the stateful one still
                    # renders exactly `(X)`, by construction rather than by a
                    # second branch, which is why the 738 such cells in the
                    # tree are untouched.
                    csv_list.append(',(%s)' % '|'.join([
                        self._condition_to_csv(cond, role_from)
                    for cond in self.policies[
                        (role_from, role_to)
                    ].conditions]))
                elif self.policy_exists(role_from, role_to):
                    csv_list.append(',X')
                else:
                    csv_list.append(',')

            csv_list.append('\n')

        return ''.join(csv_list)


    def to_mapping(self) -> str:
        """ Creates a mapping between role names and technical attributes.

        Returns:
            A string that is JSON file containing a mapping between roles and attributes.
        """

        mapping = {
            name : role.attributes for name, role in self.roles.items() if type(role) == Role
        }
        return json.dumps(mapping, indent=2) + '\n'

    def to_iptables(self) -> str:
        """ Creates a list of iptables rules for the given Policies

        Returns:
            A String that contains the iptables rules
        """
        # set needed Variables
        iptables_rules = []
        # Suppress list (raw/PREROUTING NOTRACK rules). Per Algorithm 7.1 (thesis
        # Sec. 7.3) these stateless-suppression rules are collected separately and
        # prepended to the main list (return Suppress + Main).
        suppress_rules = []
        ip4rule = False
        ip6rule = False

        #defaultrules rules and best practices
        defaultruletarget = " ACCEPT" if self.default_policy else " DROP"
        iptables_rules.append("# === IPv4 Default Policy ===")
        default4rule = "iptables -P FORWARD" + defaultruletarget
        iptables_rules.append(default4rule)

        #Anti-Spoofing Ipv4
        iptables_rules.append("# === IPv4 Anti-Spoofing ===")
        # SORTED, because `get_atomic_roles` returns a `set` and set iteration
        # for strings follows a hash Python randomises per process. Nothing
        # here was ever WRONG -- this block is entirely `-j DROP`, so a packet
        # gets the same verdict from whichever rule matches first, and the
        # thesis's Algorithm 7.1 (Sec. 7.3) rests on exactly that: a block is
        # emitted in a fixed position and is single-action, so order WITHIN it
        # carries no meaning.
        #
        # What it cost was the ARTIFACT. Measured on a five-role fixture before
        # this line: eight `PYTHONHASHSEED` values produced seven different
        # rule sets, so a generated firewall could not be checksummed, diffed
        # against the previous run, or reviewed by eye without the reader
        # having to decide for themselves which differences meant anything.
        # CLOUD_BENCH_PLAN.md §1.8 asks every artifact to be recreatable from
        # its raw data; recreatable and byte-identical is the useful form of
        # that. See TODO item 20 and `test_iptables_reproducible.py`.
        for role in sorted(self.get_atomic_roles()):
            if 'ipv4' in self.roles[role].attributes:
                srcs = self.roles[role].attributes['ipv4']
                srcs = srcs if isinstance(srcs, list) else [srcs]
                for src in srcs:
                    bp4rules = "iptables -A FORWARD -i eth1 -s " + src + " -j DROP"
                    iptables_rules.append(bp4rules)

        iptables_rules.append("# === IPv4 State Tracking ===")
        bp4rules = "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        iptables_rules.append(bp4rules)

        iptables_rules.append("# === IPv6 Default Policy ===")
        default6rule = "ip6tables -P FORWARD" + defaultruletarget
        iptables_rules.append(default6rule)

        #Anti-Spoofing Ipv6
        iptables_rules.append("# === IPv6 Anti-Spoofing ===")
        for role in sorted(self.get_atomic_roles()):
            if 'ipv6' in self.roles[role].attributes:
                srcs = self.roles[role].attributes['ipv6']
                srcs = srcs if isinstance(srcs, list) else [srcs]
                for src in srcs:
                    bp6rules = "ip6tables -A FORWARD -i eth1 -s " + src + " -j DROP"
                    iptables_rules.append(bp6rules)


        # ICMP Traffic
        iptables_rules.append("# === IPv6 ICMP ===")
        iptables_rules += [
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT",
            "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT"
        ]

        #Routing-Header
        iptables_rules.append("# === IPv6 Hardening ===")
        iptables_rules += [
            "ip6tables -N routinghdr",
            "ip6tables -A routinghdr -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP",
            "ip6tables -A routinghdr -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP",
            "ip6tables -A routinghdr -m rt --rt-type 0 --rt-segsleft 0 -j RETURN",
            "ip6tables -A routinghdr -m rt --rt-type 2 --rt-segsleft 1 -j RETURN",
            "ip6tables -A routinghdr -m rt ! --rt-segsleft 0 --j DROP",
            "ip6tables -A FORWARD -m ipv6header --header ipv6-route --soft -j routinghdr"
        ]

        iptables_rules.append("# === IPv6 State Tracking ===")
        iptables_rules.append("ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT")

        # create iptable rule(s) for every Policy
        iptables_rules.append("# === Access Rules ===")
        for policy in self.policies:
            PT_LOGGER.debug(f"handle policy rule: {policy} with conditions: {self.policies[policy].conditions}")

            from_, to_ = policy
            from_role = self.roles[from_]
            to_role = self.roles[to_]

            # check if one is Internet
            eth_from = " -i eth1" if (from_ == "Internet") else ""
            eth_to = " -o eth1" if (to_ == "Internet") else ""

            # Check for interface and vlan
            if not eth_from:
                eth_from_interface = (
                    " -i " + from_role.attributes["interface"]
                ) if ("interface" in from_role.attributes) else ""
                eth_from_vlan = (
                    "." + from_role.attributes["vlan"]
                ) if ("vlan" in from_role.attributes and "interface" in from_role.attributes) else ""
                eth_from = eth_from_interface + eth_from_vlan
            if not eth_to:
                eth_to_interface = (
                    " -o " + to_role.attributes["interface"]
                ) if ("interface" in to_role.attributes) else ""
                eth_to_vlan = (
                    "." + to_role.attributes["vlan"]
                ) if ("vlan" in to_role.attributes and "interface" in to_role.attributes) else ""
                eth_to = eth_to_interface + eth_to_vlan

            conditions = self.policies[policy].conditions

            # Does this direction rely on connection tracking?
            stateful = RELATED_CONDITION in conditions

            # Is it covered ENTIRELY by the global `--ctstate ESTABLISHED`
            # rule, so that no rule of its own is needed?
            #
            # These are two questions and this used to ask only the first,
            # suppressing the pair's rules whenever the stateful condition was
            # present -- `relatedrule` conflated "carries state" with "carries
            # nothing but state". A pair that is both (`A <->> B` giving B -> A
            # the return direction, plus `B ---> A.SERVICE` giving it a
            # service) therefore lost its service rules entirely: the firewall
            # silently permitted less than the policy states. Same conflation
            # `roles_to_csv` made with `(X)`, TODO item 20.
            relatedrule = stateful and len(conditions) == 1

            #test for strict rules A--->A to convert to A<-->A later on
            strictrule = from_ == to_

            #test for single way policy
            singleway = True
            revpol = (to_, from_)
            if revpol in self.policies:
                revrelatedrule = (RELATED_CONDITION in self.policies[revpol].conditions)
                singleway = not revrelatedrule

            # ... and never for a direction that is itself stateful. `singleway`
            # decides whether connection tracking can be switched off for the
            # pair (`--ctstate NEW,NOTRACK` plus a raw/PREROUTING NOTRACK), and
            # it asks that of the REVERSE direction only. That was sound while a
            # stateful direction emitted no rules at all; now that a mixed one
            # does, NOTRACK here would disable the very tracking the global
            # ESTABLISHED rule needs to admit this direction's return traffic.
            singleway = singleway and not stateful

            # set jumptarget depending on standard and singleway policy
            jumptarget = " -j ACCEPT" if not self.default_policy else " -j DROP"

            # Only create ip4table rules if not relatedrule, both have ipv4 or one is Internet and the other one has ipv4
            ip4rule = (not relatedrule) and (
                ("ipv4" in from_role.attributes) and ("ipv4" in to_role.attributes)  or
                (from_ == "Internet" or to_ == "Internet") and (
                    ("ipv4" in from_role.attributes) or ("ipv4" in to_role.attributes)
                )
            )

            # get ipv4 source and destination adress
            ip4_srcs = from_role.attributes.get("ipv4", [""])
            ip4_from = [
                (" -s " + ip4_src if ip4_src else ip4_src) for ip4_src in ip4_srcs
            ] if isinstance(ip4_srcs, list) else [
                " -s " + ip4_srcs
            ]

            ip4_dsts = to_role.attributes.get("ipv4", [""])
            ip4_to = [
                (" -d " + ip4_dst if ip4_dst else ip4_dst) for ip4_dst in ip4_dsts
            ] if isinstance(ip4_dsts, list) else [
                " -d " + ip4_dsts
            ]

            # Only create ip6table rules if not relatedrule and both have ipv6 or one is Internet and the other one has ipv6
            ip6rule = (not relatedrule) and (
                ("ipv6" in from_role.attributes) and
                ("ipv6" in to_role.attributes) or
                (from_ == "Internet" or to_ == "Internet") and
                (
                    ("ipv6" in from_role.attributes) or
                    ("ipv6" in to_role.attributes)
                )
            )

            # get ipv6 source and destination adress
            ip6_srcs = from_role.attributes.get("ipv6", [""])
            ip6_from = [
                (" -s " + ip6_src if ip6_src else ip6_src) for ip6_src in ip6_srcs
            ] if isinstance(ip6_srcs, list) else [
                " -s " + ip6_srcs
            ]

            ip6_dsts = to_role.attributes.get("ipv6", [""])
            ip6_to = [
                (" -d " + ip6_dst if ip6_dst else ip6_dst) for ip6_dst in ip6_dsts if ip6_dst
            ] if isinstance(ip6_dsts, list) else [
                " -d " + ip6_dsts
            ]

            # add comment for human readability
            comment = " -m comment --comment \"" + from_ + " to " + to_ + "\""

            # add statemodule plus new if singlerule add notrack
            module = " -m conntrack --ctstate NEW" + (
                ",NOTRACK" if (singleway and not strictrule) else ""
            )

            #if there are condition handle them
            if self.policies[policy].conditions:
                PT_LOGGER.debug(f"handle conditions: {self.policies[policy].conditions}")
                for cond in self.policies[policy].conditions:
                    provider: Any = []
                    #check if services are given
                    if 'provider' in cond:
                        provider = cond['provider']
                    if 'protocol' in cond:
                        # A service may name a protocol WITHOUT a port -- icmp
                        # and gre carry none. This used to read `cond['port']`
                        # unconditionally and raise `KeyError('port')`.
                        serviceinfo = " --protocol " + str(cond['protocol'])
                        if 'port' in cond:
                            serviceport = (
                                " --sport " if provider == from_ else " --dport "
                            )
                            serviceinfo += serviceport + str(cond['port'])
                    elif 'port' in cond:
                        # A port with no protocol is expressible in FaVe --
                        # `packet.upper.dport` does not depend on the upper
                        # protocol -- but not in iptables, which needs `-p` to
                        # reach a port match. Assuming tcp would invent policy.
                        #
                        # This branch used to fall through to `serviceinfo = ""`
                        # and the rule was then dropped by the `if serviceinfo`
                        # guard below: under a default-deny ruleset the
                        # generated firewall silently withheld traffic the
                        # policy PERMITS (TODO item 21).
                        raise PortWithoutProtocolException(
                            cond['port'], from_, to_)
                    else:
                        serviceinfo = ""
                    # check for states
                    if 'state' in cond:
                        # a-/-->> rules
                        if cond['state'] == 'NEW,INVALID':
                            iptables_rules += [(
                                "iptables -A FORWARD" + eth_from + serviceinfo + ip4_src + eth_to + ip4_dst + " -m conntrack --ctstate NEW" + comment + jumptarget
                            ) for ip4_src in ip4_from for ip4_dst in ip4_to]

                    #if serviceinfo is set create rule
                    if serviceinfo:
                        if ip4rule:
                            #create prerouting rule if neccesary
                            #TODO remove ALL strictrule when Policy creation(A<->A insted of A->A) is fixed
                            if singleway and not self.default_policy and not strictrule:
                                suppress_rules += [(
                                    "iptables -t raw -A PREROUTING" + eth_from + ip4_src + eth_to + ip4_dst + comment + " -j NOTRACK"
                                ) for ip4_src in ip4_from for ip4_dst in ip4_to]
                            iptables_rules += [(
                                "iptables -A FORWARD" + eth_from + serviceinfo + ip4_src + eth_to + ip4_dst + module + comment + jumptarget
                            ) for ip4_src in ip4_from for ip4_dst in ip4_to]

                        if ip6rule:
                            #create prerouting rule if neccesary
                            if singleway and not self.default_policy and not strictrule:
                                suppress_rules += [(
                                    "ip6tables -t raw -A PREROUTING" + eth_from + ip6_src + eth_to + ip6_dst + comment + " -j NOTRACK"
                                ) for ip6_src in ip6_from for ip6_dst in ip6_to]
                            iptables_rules += [(
                                "ip6tables -A FORWARD" + eth_from + serviceinfo + ip6_src + eth_to + ip6_dst + module + comment + jumptarget
                            ) for ip6_src in ip6_from for ip6_dst in ip6_to]

            #if there are no conditions
            else:
                PT_LOGGER.debug(f"no conditions to handle")
                if ip4rule:
                    if singleway and not strictrule:
                        suppress_rules += [(
                            "iptables -t raw -A PREROUTING" + eth_from + ip4_src + eth_to + ip4_dst + comment + " -j NOTRACK"
                        ) for ip4_src in ip4_from for ip4_dst in ip4_to]
                    iptables_rules += [(
                        "iptables -A FORWARD" + eth_from + ip4_src + eth_to + ip4_dst + module + comment + jumptarget
                    ) for ip4_src in ip4_from for ip4_dst in ip4_to]

                if ip6rule:
                    if singleway and not strictrule:
                        suppress_rules += [(
                            "ip6tables -t raw -A PREROUTING" + eth_from + ip6_src + eth_to + ip6_dst + comment + " -j NOTRACK"
                        ) for ip6_src in ip6_from for ip6_dst in ip6_to]
                    iptables_rules += [(
                        "ip6tables -A FORWARD" + eth_from + ip6_src + eth_to + ip6_dst + module + comment + jumptarget
                    ) for ip6_src in ip6_from for ip6_dst in ip6_to]

            # reset variables for next run
            ip4rule = ip6rule = False
            eth_to = eth_from = serviceinfo = comment = ""
            ip4_from = ip4_to = ip6_from = ip6_to = []
            PT_LOGGER.debug(f"finished policy rule: {policy}")

        PT_LOGGER.debug('compile iptables rule set')
        # Algorithm 7.1 (thesis Sec. 7.3) returns Suppress + Main: prepend the
        # stateless-suppression (raw/PREROUTING NOTRACK) rules as a leading block.
        # (Equivalent to inlining them, since netfilter evaluates the raw table
        # before filter regardless of command order -- but this mirrors the spec.)
        out = ["# === Suppress (stateless NOTRACK) ==="] + suppress_rules + iptables_rules
        result = "\n".join(out) + '\n'
        PT_LOGGER.trace(result)
        return result


    #: What each FPL operator says, as a sentence. `%(from)s`, `%(to)s` and
    #: `%(via)s` are filled in; `%(via)s` is empty for a rule naming no service.
    #:
    #: Split by DEFAULT POLICY because FPL's operators are: the three
    #: permissions are read only under `default: deny` and the three
    #: prohibitions only under `default: allow` (`PolicyBuilder.build_policies`).
    #: An operator used under the other default is SKIPPED -- it reaches a
    #: `PT_LOGGER.debug` and nothing else -- so a rule can sit in the policy
    #: file looking effective while contributing nothing. `to_prosa` is the one
    #: output a human reads against that file, which makes it the right place
    #: to say so; see `_PROSA_INERT`.
    prosa_permits = {
        "--->": "%(from)s may reach %(to)s%(via)s.",
        "<-->": "%(from)s and %(to)s may reach each other%(via)s.",
        "<->>": (
            "%(from)s may reach %(to)s%(via)s, and replies may come back."
        ),
    }

    prosa_forbids = {
        "--/->": "%(from)s may not reach %(to)s%(via)s.",
        "<-/->": "%(from)s and %(to)s may not reach each other%(via)s.",
        "-/->>": "%(from)s may not open new connections to %(to)s.",
    }

    def to_prosa(self) -> str:
        """ Renders the policy's own rules as English sentences.

        FOR A HUMAN, and it used to be for nobody: this printed each rule's
        four raw fields to stdout and returned `'\n'.join([])`, so
        `policy_translator.py -p -o FILE` wrote an empty file on every run and
        the only output went to a terminal in a field order (`from to service
        operator`) that is not the order the rule is written in. Nothing in the
        tree consumes prosa, which is why it went unnoticed; TODO item 20.

        Each rule is rendered as its FPL line followed by the sentence, so the
        output can be read straight down against the policy file. A rule the
        default policy does not permit is marked rather than dropped -- the
        translator skips it silently, and a prosa that simply omitted it would
        be a second silent skip on top of the first.

        `raw_policies` holds what the POLICY FILE declared, so the implicit
        self-reachability rules (`policy.strict` false) are deliberately absent:
        they are the translator's, not the author's. For the same reason this
        does not follow `--report`, which replaces the reachability matrix but
        leaves the declared rules alone.

        Returns:
            A String that contains the prosaic rules.
        """
        lines = [
            "# Policy Translator -- prose output",
            "#",
            "# Ground rule: %s" % (
                "everything is allowed that is not forbidden here "
                "(default: allow)." if self.default_policy else
                "everything is forbidden that is not allowed here "
                "(default: deny)."
            ),
            "# %d rule%s." % (
                len(self.raw_policies),
                "" if len(self.raw_policies) == 1 else "s"),
        ]

        for role_from, role_to, service_to, operator in self.raw_policies:
            via = ""
            if service_to:
                via = (
                    " via every service it offers" if service_to == "*"
                    else " via the service %s" % service_to
                )

            fields = {"from": role_from, "to": role_to, "via": via}
            source = "%s %s %s" % (
                role_from, operator,
                "%s.%s" % (role_to, service_to) if service_to else role_to)

            honoured = (
                self.prosa_forbids if self.default_policy else self.prosa_permits
            )
            other = (
                self.prosa_permits if self.default_policy else self.prosa_forbids
            )

            lines.append("")
            lines.append(source)
            if operator in honoured:
                lines.append("\t" + honoured[operator] % fields)
            elif operator in other:
                lines.append(
                    "\tNO EFFECT: `%s` %s, but is only read under "
                    "`default: %s`. This rule was skipped during translation."
                    % (
                        operator,
                        "forbids" if operator in self.prosa_forbids
                        else "permits",
                        "allow" if operator in self.prosa_forbids else "deny"))
            else:
                # Unreachable through `policy_regex`, which matches the six
                # operators and nothing else. Stated anyway: a seventh added to
                # the grammar and not to the two tables above would otherwise
                # render as a blank line under its own source rule.
                lines.append(
                    "\tUNKNOWN OPERATOR `%s` -- neither `Policy.prosa_permits` "
                    "nor `Policy.prosa_forbids` knows it." % operator)

        return "\n".join(lines) + "\n"


    def roles_to_json(self) -> List[Any]:
        """ Dumps atomic roles as json, ordered by name.

        SORTED because this dump is a build artifact of the benchmark pipeline
        (`policy_translator --roles`, consumed by bench/reach_csv_to_checks.py):
        `get_atomic_roles` returns a set, so an unsorted dump reordered itself on
        every run and every regeneration produced a spurious diff.
        """
        return [self.roles[r].to_json() for r in sorted(self.get_atomic_roles())]


class Role(object):
    """Represents a set of hosts that have certain attributes and offer certain
    services.

    Attributes:
        name: A string.
        policy: A Policy object that the role belongs to.
        attributes: A dictionary containing attributes and their values.
        services: A dictionary containing service names as keys and Service
            objects as values.
    """

    valid_role_attr = [
        "description",
        "hosts",
        "vlan",
        "ipv4",
        "ipv6",
        "gateway",
        "gateway4",
        "gateway6",
        "interface"
    ]

    def __init__(self, name: str, policy: "Policy", attributes: Optional[Dict[str, Any]] = None, services: Optional[Dict[str, "Service"]] = None) -> None:
        """Initialises a Role object with the given name, policy, attributes and
        services.

        Args:
            name: A string.
            policy: A Policy object.
            attributes: A dictionary. (default: {})
            services: A dictionary. (default: {})
        """

        self.name = name
        self.policy = policy
        self.attributes = attributes if attributes is not None else {}
        self.services = services if services is not None else {}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented

        # Compare the services dicts directly: the previous zip(self.services,
        # other.services) iterated dict *keys* and ignored both the service
        # values and any length mismatch.
        return all([
            self.name == other.name,
            self.attributes == other.attributes,
            self.services == other.services,
        ])

    def add_attribute(self, key: str, value: str) -> None:
        """Sets an attribute value. If already set, it will be overwritten.

        Args:
            key: A string.
            value: A string; may be a list in string from. (example:
                "['a', 'b']")

        Raises:
            InvalidValueException: Value could not be read.
            InvalidAttributeException: Attribute is not part of the list of
                valid attributes.
        """

        if key in self.valid_role_attr:
            try:
                self.attributes[key] = ast.literal_eval(value)
            except Exception:
                raise InvalidValueException(key, value)
        else:
            raise InvalidAttributeException(key)

    def add_service(self, name: str) -> None:
        """Adds an existing service to the role.

        Args:
            name: A string.

        Raises:
            ServiceUnknownException: Service name is not known to the Policy
                object.
        """

        if self.policy.service_exists(name):
            self.services[name] = self.policy.services[name]
        else:
            raise ServiceUnknownException(name)

    def get_roles(self) -> List[str]:
        """Returns a list of all roles that are represented by this role, i.e.,
        a list containing only itself.

        Returns:
            A list containing the role name.
        """

        return [self.name]

    def get_services(self) -> Dict[str, Dict[str, "Service"]]:
        """Returns a dictionary of all roles that are represented by this role
        as keys, i.e., only itself, and a dictionary of all services of those
        roles, i.e., its services.

        Returns:
            A dictionary containing the role name as key and the services
            dictionary as value.
        """

        if self.name == INTERNET_ROLE:
            return {self.name: self.policy.services}

        return {self.name: self.services}

    def offers_services(self) -> bool:
        """Checks whether this role offers services or not.

        Returns:
            A boolean value.
        """

        if self.name == INTERNET_ROLE:
            return len(self.policy.services) > 0

        return len(self.services) > 0

    def offers_service(self, name: str) -> bool:
        """Checks whether this role offers a certain service or not.

        Returns:
            A boolean value.
        """

        if self.name == INTERNET_ROLE:
            return name in self.policy.services

        return name in self.services


    def to_json(self) -> Dict[str, Any]:
        """ Dumps the role to json.
        """
        return {
            'name' : self.name,
            'attributes' : self.attributes,
            'services' : [self.policy.services[s].to_json() for s in self.services]
        }


class Superrole(Role):
    """Contains a set of roles. May contain all services of a role or only a
    certain subset of services.

    Attributes:
        name: A string.
        policy: A Policy object that the superrole belongs to.
        subroles: A dictionary containing role names as keys and Role
            objects as values.
        subservices: A dictionary containing role names as keys and dictionaries
             containing service names as keys and Service objects as values.
    """

    def __init__(self, name: str, policy: "Policy", subroles: Optional[Dict[str, "Role"]] = None, subservices: Optional[Dict[str, Dict[str, "Service"]]] = None) -> None:
        """Initialises a Superrole object with the given name, policy, subroles
        and subservices.

        Args:
            name: A string.
            policy: A Policy object.
            subroles: A dictionary. (default: {})
            subservices: A dictionary. (default: {})
        """

        self.name = name
        self.policy = policy
        self.subroles = subroles if subroles is not None else {}
        self.subservices = subservices if subservices is not None else {}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Superrole):
            return NotImplemented

        # Compare the subrole/subservice dicts directly: the previous
        # zip(self.subroles, other.subroles) iterated dict *keys* and ignored
        # both the values and any length mismatch.
        return all([
            self.name == other.name,
            self.subroles == other.subroles,
            self.subservices == other.subservices,
        ])

    def add_attribute(self, key: str, value: str) -> None:
        """Sets an attribute value for all subroles. See base class."""

        for subrole in list(self.subroles.values()):
            subrole.add_attribute(key, value)

    def add_subrole(self, name: str, service: Optional[str] = None) -> None:
        """Adds a subrole along with a service as subservice (optional).

        If the subrole added is a superrole, all of its subroles will be added
        in its stead. If a service name is given, only that service will be
        added as subservice. If no service name is given, only those services
        of the role that are subservices in the superrole will be added as
        subservices here (may be None).

        Args:
            name: A string.
            service: A string (default: None).

        Raises:
            RoleUnknownException: Role name is not known to the Policy object.
        """

        if self.policy.role_exists(name):
            new_subrole = self.policy.roles[name]

            if isinstance(new_subrole, Superrole):
                for subrole in new_subrole.get_roles():
                    if service is None:
                        self.subroles[subrole] = self.policy.roles[subrole]
                        # COPIED, not shared. The two superroles then own
                        # separate records of what each offers through this
                        # member, and `Outer.add_service` no longer writes
                        # through into `Mid.subservices` -- which made `Mid.*`
                        # resolve to a service `Mid` never declared, purely
                        # because something else included it (TODO item 19).
                        self.subservices[subrole] = dict(
                            new_subrole.subservices[subrole])
                    else:
                        self.add_subrole(subrole, service=service)
            else:
                self.subroles[name] = new_subrole
                if name not in list(self.subservices.keys()):
                    self.subservices[name] = {}
                if service is not None:
                    self.add_subservice(name, service)
        else:
            raise RoleUnknownException(name)

    def add_subservice(self, subrole: str, service: str) -> None:
        """Adds one or all services of a subrole as subservices.

        Args:
            subrole: A string.
            service: A string, may be "*" (wildcard).

        Raises:
            ServiceUnknownException: Service name is not known to the Role
                object.
        """

        if service == "*":
            for service_ in self.policy.roles[subrole].services:
                self.subservices[subrole][service_] = self.policy.services[service_]
        elif self.policy.roles[subrole].offers_service(service):
            self.subservices[subrole][service] = self.policy.services[service]
        else:
            raise ServiceUnknownException(service, subrole)

    def add_service(self, service: str) -> None:
        """Adds a service to all subroles and adds that service as subservice
        for all roles.

        Args:
            service: A string.
        """

        for subrole in list(self.subroles.values()):
            subrole.add_service(service)
        for subrole_name in list(self.subroles.keys()):
            self.add_subservice(subrole_name, service)

    def get_roles(self) -> List[str]:
        """Returns a list of all roles that are represented by this role, i.e.,
        a list containing all subroles.

        Returns:
            A list containing the role names of all subroles.
        """

        return list(self.subroles.keys())

    def get_services(self) -> Dict[str, Dict[str, "Service"]]:
        """Returns a dictionary of all roles that are represented by this role
        as keys, i.e., all subroles, and a dictionary of the services this
        superrole offers through each of them.

        SERVICES TRAVEL DOWN, NEVER UP (owner decision 2026-09-21). A superrole
        offers what its own `offers` lines declare -- `Superrole.add_service`
        writes those into every subrole and records them here -- plus whatever
        an `includes Alpha.HTTPS` names explicitly. A subrole's OWN services
        stay its own: `R ---> SR.*` reaches only what `SR` offers, so a plain
        `includes Alpha` contributes nothing to the group even when Alpha
        offers a great deal.

        `subservices` is therefore read as written, with no fallback to the
        subrole. An entry that is empty means the group offers nothing through
        that member, which is a statement and not a gap.

        Returns:
            A dictionary containing the subrole names as keys and the offered
            services as values.
        """

        return self.subservices

    def offers_services(self) -> bool:
        """Checks whether this role offers services or not.

        A superrole offers what its own `offers` lines declare, not what its
        members happen to offer. Answering False unconditionally made
        `X ---> Superrole.SERVICE` raise `ServiceUnknownException` for a service
        the group declares itself -- `All ---> All.ARP` in
        `examples/fml-paper-policy.txt`, over a `def role All` whose body reads
        `offers ARP`, could not be compiled at all.

        Returns:
            A boolean value.
        """

        return any(self.get_services().values())

    def offers_service(self, name: str) -> bool:
        """Checks whether this role offers a certain service or not.

        Read off `get_services`, deliberately: `add_reachability_policy` uses
        this method to GUARD the services that method produces, so a definition
        of its own could reject a service the wildcard had just resolved.

        Returns:
            A boolean value.
        """

        return any(name in offered for offered in self.get_services().values())


class Service(object):
    """Represents a service, i.e., a certain port and/or transport layer
    protocol.

    Attributes:
        name: A string.
        policy: A Policy object that the role belongs to.
        attributes: A dictionary containing attributes and their values.
    """

    valid_service_attr = ["protocol", "port"]

    #: The IP protocols a service may name. `protocol` is an IP protocol and
    #: nothing else (owner decision 2026-09-21): both consumers of a service
    #: map it to the same packet field -- `fave/util/match_util.py` and
    #: `fave/iptables/generator.py` each send `protocol` to
    #: `packet.ipv6.proto` -- so a value outside this set is one neither the
    #: model nor a firewall can represent.
    #
    #: This list DUPLICATES `fave/util/packet_util.py`'s `normalize_ipv6_proto`,
    #: because policy_translator is a standalone tree and cannot import from
    #: fave/. The duplication is pinned by
    #: `fave/test/test_protocol_vocabulary_agrees.py`, which fails if the two
    #: drift apart -- the alternative, guessing here, is how `arp` and `1616`
    #: came to be written in the first place.
    #
    #: Layer 2 is deliberately absent. FPL expresses layer 2 through role
    #: attributes (`vlan`); a service-level `l2proto` would be the way to say
    #: ARP, and nothing needs it yet (owner, 2026-09-21).
    valid_protocols = ["gre", "esp", "icmp", "icmpv6", "tcp", "udp"]

    def __init__(self, name: str, policy: "Policy", attributes: Optional[Dict[str, Any]] = None) -> None:
        """Initialises a Service object with the given name, policy, attributes
        and    services.

        Args:
            name: A string.
            policy: A Policy object.
            attributes: A dictionary. (default: {})
        """

        self.name = name
        self.policy = policy
        self.attributes = attributes if attributes is not None else {}

    def __eq__(self, other: object) -> bool:
        assert isinstance(other, Service)

        return all([
            self.name == other.name,
            self.attributes == other.attributes
        ])

    def add_attribute(self, key: str, value: str) -> None:
        """Sets an attribute value. If already set, it will be overwritten.

        Args:
            key: A string.
            value: A string; may be a list in string from. (example:
                "['a', 'b']")

        Raises:
            InvalidValueException: Value could not be read.
            InvalidAttributeException: Attribute is not part of the list of
                valid attributes.
        """

        if key not in self.valid_service_attr:
            raise InvalidAttributeException(key)

        try:
            parsed = ast.literal_eval(value)
        except Exception:
            raise InvalidValueException(key, value)

        # Checked HERE, where the writer can act on it, rather than in a
        # renderer. `examples/fml-paper-policy.txt` declares `protocol = 1616`
        # and `protocol = 'arp'`, and the three consumers disagreed about what
        # to do with them: `roles_to_csv` rendered `protocol:1616` happily,
        # `to_iptables` raised TypeError on the int and KeyError('port') on the
        # name, and FaVe's own normaliser rejects both -- so the matrix
        # compiled into checks the verifier could not read. One refusal, at the
        # declaration (TODO item 21).
        if key == 'protocol' and parsed not in self.valid_protocols:
            raise UnknownProtocolException(self.name, parsed, self.valid_protocols)

        self.attributes[key] = parsed

    def to_json(self) -> Dict[str, Any]:
        """ Dump service as json.
        """
        return {
            'name' : self.name,
            'attributes' : self.attributes
        }


class ReachabilityPolicy(object):
    """Represents a reachability policy from one role to another that differs
    from the default policy.

    Attributes:
        role_from: A string.
        role_to: A string.
        policy: A Policy object.
        conditions: A list of dictionaries containing attribute-value-pairs
            that specify some condition, e.g., "port": 22.
            All list entries are considered to be connected by "OR".
            Semantics differ depending on the default policy of the Policy
            object this reachability policy belongs to. If the default policy
            is "deny", these are the conditions under which reachability will
            be allowed. If the default policy is "allow", these are the
            conditions under which reachability will be denied.
    """

    def __init__(self, role_from: str, role_to: str, policy: "Policy", conditions: Optional[List[Dict[str, Any]]] = None) -> None:
        """Initialises a ReachabilityPolicy object with the given role names,
        policy and conditions.

        Args:
            name: A string.
            policy: A Policy object.
            conditions: A list of dictionaries. (default: [])
        """

        self.role_from = role_from
        self.role_to = role_to
        self.policy = policy
        self.conditions = copy.deepcopy(conditions) if conditions is not None else []

    def __eq__(self, other: object) -> bool:
        assert isinstance(other, ReachabilityPolicy)

        return all([
            self.role_from == other.role_from,
            self.role_to == other.role_to,
            self.conditions == other.conditions
        ])

    def update_conditions(self, new_conditions: List[Dict[str, Any]]) -> None:
        """Adds or removes conditions.

        Each new condition is considered separately.
        If it is a superset of some condition that already exists (= more strict),
        it will be discarded.
        If it is a subset of some condition that already exists (= less strict),
        the already existing condition will be replaced by it.
        If it is neither, it will be added as an additional "OR" operand.

        An empty list of conditions means that reachability is allowed or denied
        (depending on the default policy) unconditionally. Therefore, the empty
        list overpowers all other lists of conditions.

        Args:
            new_conditions: A list of dictionaries.
        """
        if self.conditions == []:
            return
        elif new_conditions == []:
            self.conditions = []
            return

        for new_condition in new_conditions:
            append = True
            for condition in self.conditions:
                if condition.items() <= new_condition.items():
                    append = False
                    break
                elif new_condition.items() < condition.items():
                    self.conditions.remove(condition)
                    break
            if append:
                self.conditions.append(new_condition)


class IgnorePolicy(object):

    def __init__(self, role_from: str, role_to: str, policy: "Policy", conditions: Optional[List[Dict[str, Any]]] = None) -> None:
        self.role_from = role_from
        self.role_to = role_to
        self.policy = policy
        self.conditions = copy.deepcopy(conditions) if conditions is not None else []


    def __eq__(self, other: object) -> bool:
        assert isinstance(other, IgnorePolicy)

        return all([
            self.role_from == other.role_from,
            self.role_to == other.role_to,
            self.conditions == other.conditions
        ])


    def update_conditions(self, new_conditions: List[Dict[str, Any]]) -> None:
        """Adds or removes conditions.

        Each new condition is considered separately.
        If it is a superset of some condition that already exists (= more strict),
        it will be discarded.
        If it is a subset of some condition that already exists (= less strict),
        the already existing condition will be replaced by it.
        If it is neither, it will be added as an additional "OR" operand.

        An empty list of conditions means that reachability is allowed or denied
        (depending on the default policy) unconditionally. Therefore, the empty
        list overpowers all other lists of conditions.

        Args:
            new_conditions: A list of dictionaries.
        """
        if self.conditions == []:
            return
        elif new_conditions == []:
            self.conditions = []
            return

        for new_condition in new_conditions:
            append = True
            for condition in self.conditions:
                if condition.items() <= new_condition.items():
                    append = False
                    break
                elif new_condition.items() < condition.items():
                    self.conditions.remove(condition)
                    break
            if append:
                self.conditions.append(new_condition)
