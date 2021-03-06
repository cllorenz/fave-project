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

import ast
import copy
import json
from policy_exceptions import NameTakenException, InvalidAttributeException, InvalidValueException
from policy_exceptions import ServiceUnknownException, RoleUnknownException

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
    default_roles = {"Internet" : [('interface', '"fw.generic.eth1"')]}

    def __init__(self, strict=False, use_internet=True):
        """Initialises a Policy object with role "Internet", no services, no
        policies and default policy "deny"."""

        self.roles = {}
        self.services = {}
        self.policies = {}
        self.default_policy = False
        for role, attributes in [
                (r, a) for r, a in  self.default_roles.iteritems() if (
                    use_internet or r != 'Internet'
                )
        ]:
            self.add_role(role)
            tmp = self.roles[role]
            for key, value in attributes:
                tmp.add_attribute(key, value)
        self.strict = strict

    def __eq__(self, other):
        assert isinstance(other, Policy)

        return all([
            self.roles == other.roles,
            self.services == other.services,
            self.default_policy == other.default_policy
        ])

    def add_role(self, name):
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

    def add_superrole(self, name):
        """Adds a superrole.

        Args:
            name: A string.

        Raises:
            NameTakenException: A role or service with this name already exists.
        """

        if (self.role_exists(name)) or (self.service_exists(name)):
            raise NameTakenException(name)

        self.roles[name] = Superrole(name, self)

    def add_service(self, name):
        """Adds a service.

        Args:
            name: A string.

        Raises:
            NameTakenException: A role or service with this name already exists.
        """

        if (self.role_exists(name)) or (self.service_exists(name)):
            raise NameTakenException(name)

        self.services[name] = Service(name, self)

    def role_exists(self, name):
        """Returns whether a role with the given name exists or not.

        Args:
            name: A string.

        Returns:
            A boolean.
        """

        return name in self.roles.keys()

    def service_exists(self, name):
        """Returns whether a service with the given name exists or not.

        Args:
            name: A string.

        Returns:
            A boolean.
        """

        return name in self.services.keys()

    def policy_exists(self, role_from, role_to):
        """Returns whether a reachability policy concerning the two given roles
        exists or not.

        Args:
            role_from: A string.
            role_to: A string.

        Returns:
            A boolean.
        """

        return (role_from, role_to) in self.policies.keys()


    def conditional_policy_exists(self, role_from, role_to):
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


    def add_reachability_policy(self, role_from, role_to, service_to=None, condition=None):
        """Adds or updates a reachability policy concerning two roles.

        If one or both of the roles are superroles, reachability policies will
        be added or updated for all combinations of their subroles.

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

        for role_from_ in self.roles[role_from].get_roles():
            for role_to_ in self.roles[role_to].get_roles():
                conditions = [copy.deepcopy(condition)] if condition is not None else []

                if service_to == "*":
                    services = self.roles[role_to_].get_services()
                    services = services[role_to_]
                else:
                    services = [service_to] if service_to is not None else []

                for service in services:
                    if self.roles[role_to].offers_service(service):
                        conditions.append(copy.deepcopy(self.services[service].attributes))
                    else:
                        raise ServiceUnknownException(service, role_to_)

                if not self.policy_exists(role_from_, role_to_):
                    self.policies[(role_from_, role_to_)] = ReachabilityPolicy(
                        role_from_, role_to_, self, conditions
                    )
                else:
                    self.policies[(role_from_, role_to_)].update_conditions(conditions)


    def add_ignore_policy(self, role_from, role_to):

        if not self.role_exists(role_from):
            raise RoleUnknownException(role_from)
        if not self.role_exists(role_to):
            raise RoleUnknownException(role_to)

        self.policies[(role_from, role_to)] = IgnorePolicy(role_from, role_to, self)


    def clear_reachability(self):
        """ Resets the reachability policy while keeping the roles and inventory.
        """
        self.policies = {}


    def set_default_policy(self, default):
        """Sets the default policy.

        Args:
            default: Either "deny" or "allow".
        """

        if default == "deny":
            self.default_policy = False
        elif default == "allow":
            self.default_policy = True


    def get_atomic_roles_rec(self, roles):
        res = set([])
        for role in roles:
            r_tmp = self.roles[role]
            if isinstance(r_tmp, Superrole):
                res.update(self.get_atomic_roles_rec(r_tmp.subroles))
            else:
                res.add(role)

        return res


    def get_atomic_roles(self):
        return self.get_atomic_roles_rec(self.roles)


    def to_html(self):
        """Creates a reachability table in HTML format using roles (not
        superroles) as table headings.

        Role attributes as well as reachability conditions are presented in
        boxes that are visible when performing a mouseover over the table cells.

        Returns:
            A string that is an HTML file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.iteritems() if type(role) == Role}

        html_list = [
            "<!DOCTYPE html>\n",
            "<html>\n",
            "\t<head>\n",
            "\t\t<meta charset='UTF-8'>\n",
            "\t\t<title>Policy-Translator -- HTML-Ausgabe</title>\n",
            "\t\t<link rel='stylesheet' href='policies.css'>\n",
            "\t</head>\n",
            "\t<body>\n",
            "\t\t<table>\n",
            "\t\t\t<tr>\n",
            "\t\t\t\t<td></td>\n",
            "\t\t\t\t<td></td>\n",
            "\t\t\t\t<td class='label' colspan='%d'>ZIEL</td>\n" % len(roles),
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
            for key, value in self.roles[role].attributes.iteritems():
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
                        for key, value in cond.iteritems():
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
            "\t\t<h3>Legende:</h3>\n\n"
            "\t\t<table>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='allowed'>&#x2705;</td>\n"
            "\t\t\t\t<td>Erlaubt</td>\n"
            "\t\t\t</tr>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='cond_allowed'>&#x2705;</td>\n"
            "\t\t\t\t<td>Nur bedingt erlaubt (Mouseover f??r mehr Informationen)</td>\n"
            "\t\t\t</tr>\n"
            "\t\t\t<tr>\n"
            "\t\t\t\t<td class='disallowed'>&#x274c;</td>\n"
            "\t\t\t\t<td>Nicht erlaubt</td>\n"
            "\t\t\t</tr>\n"
            "\t\t</table>\n"
            "\t</body>\n"
            "</html>"
        ))

        return "".join(html_list)

    def vlans_to_csv(self):
        """Creates a reachability table in CSV format using VLANs as table
        headings.

        Returns:
            A string that is a CSV file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.iteritems() if type(role) == Role}
        vlans, csv_list = set(), []

        for _name, role in roles.iteritems():
            if "vlan" in role.attributes:
                vlans.add(role.attributes["vlan"])

        reachable = {(id, id) for id in vlans}

        for policy in self.policies:
            if ("vlan" in self.roles[policy[0]].attributes) and ("vlan" in self.roles[policy[1]].attributes):
                vlan_from = self.roles[policy[0]].attributes["vlan"]
                vlan_to = self.roles[policy[1]].attributes["vlan"]
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

    def roles_to_csv(self):
        """Creates a reachability table in CSV format using role names as table
        headings.

        Returns:
            A string that is a CSV file containing a reachability table.
        """

        roles = {name: role for name, role in self.roles.iteritems() if type(role) == Role}
        csv_list = ['']
        csv_list.extend([',' + r for r in sorted(roles)])
        csv_list.append('\n')

        for role_from in sorted(roles):
            csv_list.append(role_from)
            for role_to in sorted(roles):
                if self.conditional_policy_exists(role_from, role_to):
                    if {'state' : 'RELATED,ESTABLISHED'} in self.policies[(role_from, role_to)].conditions:
                        csv_list.append(',(X)')
                    else:
                        csv_list.append(',(%s)' % '|'.join([';'.join(
                            ['%s:%s' % (f, v) for f, v in cond.iteritems()]
                        ) for cond in self.policies[
                            (role_from, role_to)
                        ].conditions]))
                elif self.policy_exists(role_from, role_to):
                    csv_list.append(',X')
                else:
                    csv_list.append(',')

            csv_list.append('\n')

        return ''.join(csv_list)


    def to_mapping(self):
        """ Creates a mapping between role names and technical attributes.

        Returns:
            A string that is JSON file containing a mapping between roles and attributes.
        """

        mapping = {
            name : role.attributes for name, role in self.roles.iteritems() if type(role) == Role
        }
        return json.dumps(mapping, indent=2) + '\n'

    def to_iptables(self):
        """ Creates a list of iptables rules for the given Policies

        Returns:
            A String that contains the iptables rules
        """
        # set needed Variables
        iptable_rules = []
        ip4rule = False
        ip6rule = False

        #defaultrules rules and best practices
        defaultruletarget = " ACCEPT" if self.default_policy else " DROP"
        default4rule = "iptables -P FORWARD" + defaultruletarget
        iptable_rules.append(default4rule)

        #Anti-Spoofing Ipv4
        for role in self.get_atomic_roles():
            if 'ipv4' in self.roles[role].attributes:
                src = self.roles[role].attributes['ipv4']
                bp4rules = "iptables -A FORWARD -i eth1 -s " + src + " -j DROP"
                iptable_rules.append(bp4rules)

        bp4rules = "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        iptable_rules.append(bp4rules)

        default6rule = "ip6tables -P FORWARD" + defaultruletarget
        iptable_rules.append(default6rule)

        #Anti-Spoofing Ipv6
        for role in self.get_atomic_roles():
            if 'ipv6' in self.roles[role].attributes:
                src = self.roles[role].attributes['ipv6']
                bp6rules = "ip6tables -A FORWARD -i eth1 -s " + src + " -j DROP"
                iptable_rules.append(bp6rules)


        #ICMP Traffic
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT"
        iptable_rules.append(bp6rules)

        #Routing-Header
        bp6rules = "ip6tables -N routinghdr"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A routinghdr -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A routinghdr -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A routinghdr -m rt --rt-type 0 --rt-segsleft 0 -j RETURN"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A routinghdr -m rt --rt-type 2 --rt-segsleft 1 -j RETURN"
        iptable_rules.append(bp6rules)
        bp6rules = "ip6tables -A routinghdr -m rt ! --rt-segsleft 0 --j DROP"
        iptable_rules.append(bp6rules)

        bp6rules = "ip6tables -A FORWARD -m ipv6header --header ipv6-route --soft -j routinghdr"
        iptable_rules.append(bp6rules)

        bp6rules = "ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED -j ACCEPT"
        iptable_rules.append(bp6rules)
        # create iptable rule(s) for every Policy
        for policy in self.policies:


            # check if one is Internet
            eth_from = " -i eth1" if (policy[0] == "Internet") else ""
            eth_to = " -o eth1" if (policy[1] == "Internet") else ""

            # Check for interface and vlan
            if not eth_from:
                eth_from_interface = (
                    " -i " + self.roles[policy[0]].attributes["interface"]
                ) if ("interface" in self.roles[policy[0]].attributes) else ""
                eth_from_vlan = (
                    "." + self.roles[policy[0]].attributes["vlan"]
                ) if ("vlan" in self.roles[policy[0]].attributes and "interface" in self.roles[policy[0]].attributes) else ""
                eth_from = eth_from_interface + eth_from_vlan
            if not eth_to:
                eth_to_interface = (
                    " -o " + self.roles[policy[1]].attributes["interface"]
                ) if ("interface" in self.roles[policy[1]].attributes) else ""
                eth_to_vlan = (
                    "." + self.roles[policy[1]].attributes["vlan"]
                ) if ("vlan" in self.roles[policy[1]].attributes and "interface" in self.roles[policy[1]].attributes) else ""
                eth_to = eth_to_interface + eth_to_vlan

            #test if this policy is a relatedrule
            relatedrule = ({'state':'RELATED,ESTABLISHED'} in self.policies[policy].conditions)

            #test for strict rules A--->A to convert to A<-->A later on
            strictrule = policy[0] == policy[1]

            #test for single way policy
            singleway = True
            revpol = (policy[1], policy[0])
            if revpol in self.policies:
                revrelatedrule = ({'state' : 'RELATED,ESTABLISHED'} in self.policies[revpol].conditions)
                singleway = not revrelatedrule

            # set jumptarget depending on standard and singleway policy
            jumptarget = " -j ACCEPT" if not self.default_policy else " -j DROP"

            # Only create ip4table rules if not relatedrule, both have ipv4 or one is Internet and the other one has ipv4
            ip4rule = (not relatedrule) and (
                ("ipv4" in self.roles[policy[0]].attributes) and ("ipv4" in self.roles[policy[1]].attributes)  or
                (policy[0] == "Internet" or policy[1] == "Internet") and (
                    ("ipv4" in self.roles[policy[0]].attributes) or ("ipv4" in self.roles[policy[1]].attributes)
                )
            )

            # get ipv4 source and destination adress
            ip4_from = (" -s " + self.roles[policy[0]].attributes["ipv4"]) if ("ipv4" in self.roles[policy[0]].attributes) else ""
            ip4_to = (" -d " + self.roles[policy[1]].attributes["ipv4"]) if ("ipv4" in self.roles[policy[1]].attributes) else ""

            # Only create ip6table rules if not relatedrule and both have ipv6 or one is Internet and the other one has ipv6
            ip6rule = (not relatedrule) and (
                ("ipv6" in self.roles[policy[0]].attributes) and
                ("ipv6" in self.roles[policy[1]].attributes) or
                (policy[0] == "Internet" or policy[1] == "Internet") and
                (
                    ("ipv6" in self.roles[policy[0]].attributes) or
                    ("ipv6" in self.roles[policy[1]].attributes)
                )
            )

            # get ipv6 source and destination adress
            ip6_from = (" -s " + self.roles[policy[0]].attributes["ipv6"]) if ("ipv6" in self.roles[policy[0]].attributes) else ""
            ip6_to = (" -d " + self.roles[policy[1]].attributes["ipv6"]) if ("ipv6" in self.roles[policy[1]].attributes) else ""

            # add comment for human readability
            comment = " -m comment --comment \"" + policy[0] + " to " + policy[1] + "\""

            # add statemodule plus new if singlerule add notrack
            module = " -m conntrack --ctstate NEW"
            module = " -m conntrack --ctstate NEW,NOTRACK" if (singleway and not strictrule) else module

            #if there are condition handle them
            if self.policies[policy].conditions:
                for cond in self.policies[policy].conditions:
                    provider = []
                    #check if services are given
                    if 'provider' in cond:
                        provider = cond['provider']
                    if 'protocol' in cond:
                        serviceport = " --sport " if provider == policy[0] else " --dport "
                        serviceinfo = " --protocol " + cond['protocol'] + serviceport + cond['port']
                    else:
                        serviceinfo = ""
                    # check for states
                    if 'state' in cond:
                        # a-/-->> rules
                        if cond['state'] == 'NEW,INVALID':
                            rule = "iptables -A FORWARD" + eth_from + serviceinfo + ip4_from + eth_to + ip4_to + " -m conntrack --ctstate NEW" + comment + jumptarget
                            iptable_rules.append(rule)

                    #if serviceinfo is set create rule
                    if serviceinfo:
                        if ip4rule:
                            #create prerouting rule if neccesary
                            #TODO remove ALL strictrule when Policy creation(A<->A insted of A->A) is fixed
                            if singleway and not self.default_policy and not strictrule:
                                rule = "iptables -t raw -A PREROUTING" + eth_from + ip4_from + eth_to + ip4_to + comment + " -j NOTRACK"
                                iptable_rules.append(rule)
                            rule = "iptables -A FORWARD" + eth_from + serviceinfo + ip4_from + eth_to + ip4_to + module + comment + jumptarget
                            iptable_rules.append(rule)

                        if ip6rule:
                            #create prerouting rule if neccesary
                            if singleway and not self.default_policy and not strictrule:
                                rule = "ip6tables -A FORWARD" + eth_from + ip6_from + eth_to + ip6_to + module + comment + " -j NOTRACK"
                                iptable_rules.append(rule)
                            rule = "ip6tables -A FORWARD" + eth_from + serviceinfo + ip6_from + eth_to + ip6_to + module + comment + jumptarget
                            iptable_rules.append(rule)


            #if there are no conditions
            else:
                if ip4rule:
                    if singleway and not strictrule:
                        rule = "iptables -t raw -A PREROUTING" + eth_from + ip4_from + eth_to + ip4_to + comment + " -j NOTRACK"
                        iptable_rules.append(rule)
                    rule = "iptables -A FORWARD" + eth_from + ip4_from + eth_to + ip4_to + module + comment + jumptarget
                    iptable_rules.append(rule)

                if ip6rule:
                    if singleway and not strictrule:
                        rule = "ip6tables -t raw -A PREROUTING" + eth_from + ip6_from + eth_to + ip6_to + comment + " -j NOTRACK"
                        iptable_rules.append(rule)
                    rule = "ip6tables -A FORWARD" + eth_from + ip6_from + eth_to + ip6_to + module + comment + jumptarget
                    iptable_rules.append(rule)

            # reset variables for next run
            ip4rule = ip6rule = False
            eth_to = eth_from = ip4_from = ip4_to = ip6_from = ip6_to = serviceinfo = comment = ""
        return "\n".join(iptable_rules)


    def roles_to_json(self):
        """ Dumps atomic roles as json.
        """
        return [self.roles[r].to_json() for r in self.get_atomic_roles()]


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

    valid_role_attr = ["description", "hosts", "vlan", "ipv4", "ipv6", "gateway", "gateway4", "gateway6", "interface"]

    def __init__(self, name, policy, attributes=None, services=None):
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

    def __eq__(self, other):
        assert isinstance(other, Role)

        return self.name == other.name and self.attributes == other.attributes and all([
            service == other_service for service, other_service in zip(self.services, other.services)
        ])

    def add_attribute(self, key, value):
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

    def add_service(self, name):
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

    def get_roles(self):
        """Returns a list of all roles that are represented by this role, i.e.,
        a list containing only itself.

        Returns:
            A list containing the role name.
        """

        return [self.name]

    def get_services(self):
        """Returns a dictionary of all roles that are represented by this role
        as keys, i.e., only itself, and a dictionary of all services of those
        roles, i.e., its services.

        Returns:
            A dictionary containing the role name as key and the services
            dictionary as value.
        """

        return {self.name: self.services}

    def offers_services(self):
        """Checks whether this role offers services or not.

        Returns:
            A boolean value.
        """

        return len(self.services) > 0

    def offers_service(self, name):
        """Checks whether this role offers a certain service or not.

        Returns:
            A boolean value.
        """

        return name in self.services


    def to_json(self):
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

    def __init__(self, name, policy, subroles=None, subservices=None):
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

    def __eq__(self, other):
        assert isinstance(other, Superrole)

        return self.name == other.name and all([
            role == other_role for role, other_role in zip(self.subroles, other.subroles)
        ]) and all([
            service == other_service for service, other_service in zip(self.subservices, other.subservices)
        ])

    def add_attribute(self, key, value):
        """Sets an attribute value for all subroles. See base class."""

        for subrole in self.subroles.values():
            subrole.add_attribute(key, value)

    def add_subrole(self, name, service=None):
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
                        self.subservices[subrole] = new_subrole.subservices[subrole]
                    else:
                        self.add_subrole(subrole, service=service)
            else:
                self.subroles[name] = new_subrole
                if name not in self.subservices.keys():
                    self.subservices[name] = {}
                if service is not None:
                    self.add_subservice(name, service)
        else:
            raise RoleUnknownException(name)

    def add_subservice(self, subrole, service):
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

    def add_service(self, service):
        """Adds a service to all subroles and adds that service as subservice
        for all roles.

        Args:
            service: A string.
        """

        for subrole in self.subroles.values():
            subrole.add_service(service)
        for subrole in self.subroles.keys():
            self.add_subservice(subrole, service)

    def get_roles(self):
        """Returns a list of all roles that are represented by this role, i.e.,
        a list containing all subroles.

        Returns:
            A list containing the role names of all subroles.
        """

        return self.subroles.keys()

    def get_services(self):
        """Returns a dictionary of all roles that are represented by this role
        as keys, i.e., all subroles, and a dictionary of subservices of those
        roles.

        Returns:
            A dictionary containing the subrole names as keys and the
            subservices dictionaries as values.
        """

        return self.subservices

    def offers_services(self):
        """Checks whether this role offers services or not.

        Returns:
            False. (Only roles offer services.)
        """

        return False

    def offers_service(self, name):
        """Checks whether this role offers a certain service or not.

        Returns:
            False. (Only roles offer services.)
        """

        return False


class Service(object):
    """Represents a service, i.e., a certain port and/or transport layer
    protocol.

    Attributes:
        name: A string.
        policy: A Policy object that the role belongs to.
        attributes: A dictionary containing attributes and their values.
    """

    valid_service_attr = ["protocol", "port"]

    def __init__(self, name, policy, attributes=None):
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

    def __eq__(self, other):
        assert isinstance(other, Service)

        return all([
            self.name == other.name,
            self.attributes == other.attributes
        ])

    def add_attribute(self, key, value):
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

        if key in self.valid_service_attr:
            try:
                self.attributes[key] = ast.literal_eval(value)
            except Exception:
                raise InvalidValueException(key, value)
        else:
            raise InvalidAttributeException(key)

    def to_json(self):
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

    def __init__(self, role_from, role_to, policy, conditions=None):
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

    def __eq__(self, other):
        assert isinstance(other, ReachabilityPolicy)

        return all([
            self.role_from == other.role_from,
            self.role_to == other.role_to,
            self.conditions == other.conditions
        ])

    def update_conditions(self, new_conditions):
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
                if condition.viewitems() <= new_condition.viewitems():
                    append = False
                    break
                elif new_condition.viewitems() < condition.viewitems():
                    self.conditions.remove(condition)
                    break
            if append:
                self.conditions.append(new_condition)


class IgnorePolicy(object):

    def __init__(self, role_from, role_to, policy, conditions=None):
        self.role_from = role_from
        self.role_to = role_to
        self.policy = policy
        self.conditions = copy.deepcopy(conditions) if conditions is not None else []


    def __eq__(self, other):
        assert isinstance(other, IgnorePolicy)

        return all([
            self.role_from == other.role_from,
            self.role_to == other.role_to,
            self.conditions == other.conditions
        ])


    def update_conditions(self, new_conditions):
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
                if condition.viewitems() <= new_condition.viewitems():
                    append = False
                    break
                elif new_condition.viewitems() < condition.viewitems():
                    self.conditions.remove(condition)
                    break
            if append:
                self.conditions.append(new_condition)
