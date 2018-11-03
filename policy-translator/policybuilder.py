# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens

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

import re
from policy_exceptions import *

class PolicyBuilder(object):
    """Offers class methods to build a policy object from a policy and/or role
    file."""

    name_pattern = "[A-Za-z][A-Za-z0-9_]*"
    role_pattern = r"""
    (\n | \# .*\n)*
    def [ ] role [ ] (?P<role_name> [A-Za-z][A-Za-z0-9_]*) [\n]+
    (?P<role_content>
        ((\t [A-Za-z]* [ \t]* = [ \t]* [A-Za-z0-9 _=\-\[\]'\".,]* [\n]+)
        | (\t includes [ ] %s(. (\* | %s) )? [\n]+)
        | (\t offers [ ] [A-Za-z][A-Za-z0-9_]* [\n]+))*
    )
    end [\n]+
    """ % (name_pattern, name_pattern)
    service_pattern = r"""
    (\n | \# .*\n)*
    def [ ] service [ ] (?P<service_name> [A-Za-z][A-Za-z0-9_]*) [\n]+
    (?P<service_content>
        (\t [A-Za-z]* [ \t]* = [ \t]* [A-Za-z0-9 _=\-\[\]'\".,\*]* [\n]+)*
    )
    end [\n]+
    """

    role_service_regex = re.compile("(%s | %s)+" % (role_pattern, service_pattern), re.X)
    role_regex = re.compile(role_pattern, re.X)
    service_regex = re.compile(service_pattern, re.X)

    role_attr_regex = re.compile(r"\t(?P<key> %s) [ \t]* = [ \t]* (?P<value>[A-Za-z0-9 _=\-\[\]'\".,]* | \*) [\n]+" % name_pattern, re.X)
    role_incl_regex = re.compile(r"\t includes [ ] (?P<role> %s)(.(?P<service> [\*] | %s))? [\n]+" % (name_pattern, name_pattern), re.X)
    role_offers_regex = re.compile(r"\t offers [ ] (?P<service> %s) [\n]+" % name_pattern, re.X)

    policies_regex = re.compile(r"""
    (\n | \# .*\n)*
    def [ ] policies\(default: [ ] (?P<default> allow | deny)\) [\n]+
        (?P<policies> (\t \# .* \n | (\t)? \n | \t %s? [ \t]* (--->|<-->|<->>|--/->|<-/->|-/->>) [ \t]* %s(.(%s | [*]))? [\n]*)*)
    end [\n]+
    """ % (name_pattern, name_pattern, name_pattern), re.X)

    policy_regex = re.compile(r"""
    (\t \# .*\n | (\t)?\n)*
    \t (?P<role_from> %s?) [ \t]* (?P<op> --->|<-->|<->>|--/->|<-/->|-/->>) [ \t]* (?P<role_to>  %s)(.(?P<service_to> (%s | [*])))? [\n]+
    """ % (name_pattern, name_pattern, name_pattern), re.X)

    @classmethod
    def build(cls, policy_chars, policy):
        """Builds a complete Policy object by reading both a role and a policy
        file.

        Args:
            policy_chars: A character string of an inventory file's content
            followed by a policy file's content.
            policy: A Policy object.
        """

        pos = cls.build_roles_and_services(policy_chars, policy)
        cls.build_policies(policy_chars[pos:], policy)

    @classmethod
    def build_roles_and_services(cls, policy_chars, policy):
        """Adds roles and services to a Policy object as specified by an
        inventory file.

        Args:
            policy_chars: A character string of an inventory file's content.
            policy: A Policy object.

        Returns:
            Position of the last role or service block match. The policy
            definition should start at this position.
        """

        role_servie_match = cls.match(cls.role_service_regex, policy_chars)

        if len(role_servie_match) != 1:
            raise InvalidSyntaxException()

        role_matches = cls.match(cls.role_regex, policy_chars, cls.role_regex.search)
        service_matches = cls.match(cls.service_regex, policy_chars, cls.service_regex.search)

        for match in service_matches:
            service = match.group("service_name")
            policy.add_service(service)
            service_attr_matches = cls.match(cls.role_attr_regex, match.group("service_content"), cls.role_attr_regex.search)
            for match in service_attr_matches:
                policy.services[service].add_attribute(match.group("key"), match.group("value"))

        for match in role_matches:
            role = match.group("role_name")
            role_attr_matches = cls.match(cls.role_attr_regex, match.group("role_content"), cls.role_attr_regex.search)
            role_incl_matches = cls.match(cls.role_incl_regex, match.group("role_content"), cls.role_incl_regex.search)
            role_offers_matches = cls.match(cls.role_offers_regex, match.group("role_content"), cls.role_offers_regex.search)

            if len(role_incl_matches) > 0:
                policy.add_superrole(role)
                for match in role_incl_matches:
                    policy.roles[role].add_subrole(match.group("role"), match.group("service"))
            else:
                policy.add_role(role)

            for match in role_offers_matches:
                policy.roles[role].add_service(match.group("service"))

            for match in role_attr_matches:
                policy.roles[role].add_attribute(match.group("key"), match.group("value"))

        return role_servie_match[0].end()

    @classmethod
    def build_policies(cls, policy_chars, policy):
        """Adds reachability policies to a Policy object as specified by a
        policy file.

        Args:
            policy_chars: A character string of a policy file's content.
            policy: A Policy object.
        """

        policy_matches = cls.match(cls.policies_regex, policy_chars)
        if len(policy_matches) > 0:
            match = policy_matches[0]
            policies_chars = match.group("policies")

            policy.set_default_policy(match.group("default"))

            single_policy_matches = cls.match(cls.policy_regex, policies_chars)
            for match in single_policy_matches:
                role_from, role_to, op, service_to = match.group("role_from"), match.group("role_to"), match.group("op"), match.group("service_to")

                if not policy.default_policy:
                    if op == "<->>":
                        policy.add_reachability_policy(role_from, role_to, service_to)
                        policy.add_reachability_policy(role_to, role_from, condition={"state": "RELATED,ESTABLISHED"})
                    elif op == "--->" or op == "<-->":
                        policy.add_reachability_policy(role_from, role_to, service_to)
                        if op == "<-->":
                            policy.add_reachability_policy(role_to, role_from, service_to)
                else:
                    if op == "--/->" or op == "<-/->":
                        policy.add_reachability_policy(role_from, role_to, service_to)
                        if op == "<-/->":
                            policy.add_reachability_policy(role_to, role_from, service_to)
                    elif op == "-/->>":
                        policy.add_reachability_policy(role_from, role_to, condition={"state": "NEW,INVALID"})

    @classmethod
    def match(self, regex, chars, function=None):
        """Returns all matches of a regular expression in a character string.

        Returns all Match objects found using either a match function (for
        consecutive matches starting from position 0) or search function (for
        not necessarily consecutive matches starting at any posiiton)
        of a Regular Expression object.

        Args:
            regex: A Regular Expression object.
            chars: A character string.
            function: Function to be called with a character string and a start
                position that will return the matches. (default: regex.match)

        Returns:
            A list of Match objects.
        """

        match, matches, start_pos = True, [], 0
        function = regex.match if function is None else function

        while match:
            match = function(chars, start_pos)
            if match:
                matches.append(match)
                start_pos = match.end()

        return matches
