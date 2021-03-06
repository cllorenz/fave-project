# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens
# List of co-authors:
#    Claas Lorenz <claas_lorenz@genua.de>


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
from policy_exceptions import InvalidSyntaxException
from policy_logger import PT_LOGGER

class PolicyBuilder(object):
    """Offers class methods to build a policy object from a policy and/or role
    file."""

    define_pattern = "(def | define | describe)"
    name_pattern = "[A-Za-z][A-Za-z0-9_]*"
    value_pattern = "[A-Za-z0-9 _=\-\[\]'\":.,\*/]+"
    comment_pattern = r"[ \t]* \# [ \t]* .* (\r\n|[\r\n])"
    comment_pattern_nl = r"%s+" % comment_pattern
    role_pattern = r"""
    ((\r\n|[\r\n]) | %s)*
    %s [ ] role [ ] (?P<role_name> %s) (\r\n|[\r\n])+
    (?P<role_content>
        (((\t | [ ]{4}) %s [ \t]* = [ \t]* %s (\r\n|[\r\n])+)
        | ((\t | [ ]{4}) includes [ ] %s([.] (\* | %s) )? (\r\n|[\r\n])+)
        | ((\t | [ ]{4}) offers [ ] %s (\r\n|[\r\n])+))*
        | (%s)
    )
    end (\r\n|[\r\n])+
    """ % (
        comment_pattern, define_pattern, name_pattern, name_pattern, value_pattern,
        name_pattern, name_pattern, name_pattern, comment_pattern_nl
    )
    service_pattern = r"""
    ((\r\n|[\r\n]) | %s)*
    %s [ ] service [ ] (?P<service_name> %s) (\r\n|[\r\n])+
    (?P<service_content>
        ((\t | [ ]{4}) %s [ \t]* = [ \t]* %s (\r\n|[\r\n])+)*
        | (%s)
    )
    end (\r\n|[\r\n])+
    """ % (comment_pattern, define_pattern, name_pattern, name_pattern, value_pattern, comment_pattern_nl)

    role_service_regex = re.compile(
        "(%s | %s | %s)+" % (comment_pattern, role_pattern, service_pattern),
        re.X
    )
    role_regex = re.compile(role_pattern, re.X)
    service_regex = re.compile(service_pattern, re.X)

    role_attr_regex = re.compile(
        r"(\t | [ ]{4})(?P<key> %s) [ \t]* = [ \t]* (?P<value> %s | \*) (\r\n|[\r\n])+" % (name_pattern, value_pattern),
        re.X
    )
    role_incl_regex = re.compile(
        r"(\t | [ ]{4}) includes [ ] (?P<role> %s)(.(?P<service> [\*] | %s))? (\r\n|[\r\n])+" % (name_pattern, name_pattern),
        re.X
    )
    role_offers_regex = re.compile(
        r"(\t | [ ]{4}) offers [ ] (?P<service> %s) (\r\n|[\r\n])+" % name_pattern,
        re.X
    )

    policies_regex = re.compile(r"""
    ((\r\n|[\r\n]) | %s)*
    %s [ ] (policies|policy) [ \t]* \(default: [ \t]+ (?P<default> allow | deny)\) (\r\n|[\r\n])+
        [ \t]* (?P<policies> (%s | (\t)? (\r\n|[\r\n]) | (\t | [ ]{4}) %s [ \t]* (--->|<-->|<->>|--/->|<-/->|-/->>) [ \t]* %s(.(%s | [*]))? (\r\n|[\r\n])+)*)
    end (\r\n|[\r\n])+
    """ % (comment_pattern, define_pattern, comment_pattern, name_pattern, name_pattern, name_pattern), re.X)

    policy_regex = re.compile(r"""
    ((\r\n|[\r\n]) | %s)*
    [ \t]* (?P<role_from> %s?) [ \t]* (?P<op> --->|<-->|<->>|--/->|<-/->|-/->>) [ \t]* (?P<role_to>  %s)(.(?P<service_to> (%s | [*])))? (\r\n|[\r\n])+
    """ % (comment_pattern, name_pattern, name_pattern, name_pattern), re.X)

    @classmethod
    def build(cls, policy_chars, policy):
        """Builds a complete Policy object by reading both a role and a policy
        file.

        Args:
            policy_chars: A character string of an inventory file's content
            followed by a policy file's content.
            policy: A Policy object.
        """

        PT_LOGGER.debug("build roles and services")
        pos = cls.build_roles_and_services(policy_chars, policy)

        PT_LOGGER.debug("build policies")
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

        PT_LOGGER.debug("match roles and services")
        role_service_match = cls.match(cls.role_service_regex, policy_chars)
        if role_service_match:
            for role_service in role_service_match:
                PT_LOGGER.trace(role_service.groupdict())

        if len(role_service_match) != 1:
            PT_LOGGER.debug("error while matching: %s\n[...]", policy_chars.splitlines()[0])
            raise InvalidSyntaxException()

        PT_LOGGER.debug("match roles")
        role_matches = cls.match(cls.role_regex, policy_chars, cls.role_regex.search)
        if role_matches:
            for role_match in role_matches:
                PT_LOGGER.trace(role_match.groupdict())

        PT_LOGGER.debug("match services")
        service_matches = cls.match(cls.service_regex, policy_chars, cls.service_regex.search)
        if service_matches:
            for service_match in service_matches:
                PT_LOGGER.trace(service_match.groupdict())

        for match in service_matches:
            PT_LOGGER.debug("fetch service name")
            service = match.group("service_name")

            PT_LOGGER.debug("service name: %s", service)
            policy.add_service(service)

            PT_LOGGER.debug("fetch service attributes")
            service_attr_matches = cls.match(
                cls.role_attr_regex,
                match.group("service_content"),
                cls.role_attr_regex.search
            )
            if service_attr_matches:
                for match_ in service_attr_matches:
                    PT_LOGGER.debug("service attribute: %s", match_.groupdict())

            for match_ in service_attr_matches:
                policy.services[service].add_attribute(match_.group("key"), match_.group("value"))

        for match in role_matches:
            PT_LOGGER.debug("fetch role name")
            role = match.group("role_name")
            PT_LOGGER.debug("role name: %s", role)

            PT_LOGGER.debug("match role attributes")
            role_attr_matches = cls.match(
                cls.role_attr_regex,
                match.group("role_content"),
                cls.role_attr_regex.search
            )
            if role_attr_matches:
                for role_attr_match in role_attr_matches:
                    PT_LOGGER.debug("role attribute: %s", role_attr_match.groupdict())

            PT_LOGGER.debug("match role includes")
            role_incl_matches = cls.match(
                cls.role_incl_regex,
                match.group("role_content"),
                cls.role_incl_regex.search
            )
            if role_incl_matches:
                for role_incl_match in role_incl_matches:
                    PT_LOGGER.debug("role includes: %s", role_incl_match.groupdict())

            PT_LOGGER.debug("match role offers")
            role_offers_matches = cls.match(
                cls.role_offers_regex,
                match.group("role_content"),
                cls.role_offers_regex.search
            )
            if role_offers_matches:
                for role_offers_match in role_offers_matches:
                    PT_LOGGER.debug("role offers: %s", role_offers_match.groupdict())

            if role_incl_matches:
                policy.add_superrole(role)
                PT_LOGGER.debug("policy: added superrole %s", role)
                for match_ in role_incl_matches:
                    policy.roles[role].add_subrole(match_.group("role"), service=match_.group("service"))
                    PT_LOGGER.debug("%s: added subrole %s", role, match_.group("role"))

#            if len(role_uses_matches) > 0:
#                policy.add_abstract_role(role)
#                PT_LOGGER.debug("policy: added superrole %s", role)
#                for match in role_incl_matches:
#                    policy.roles[role].add_subrole(match.group("role"), service=match.group("service"))
#                    PT_LOGGER.debug("%s: added subrole %s", role, match.group("role"))

            else:
                policy.add_role(role)
                PT_LOGGER.debug("policy: added role %s", role)

            for match_ in role_offers_matches:
                policy.roles[role].add_service(match_.group("service"))
                PT_LOGGER.debug("%s: added service %s", role, match_.group("service"))

            for match_ in role_attr_matches:
                policy.roles[role].add_attribute(match_.group("key"), match_.group("value"))
                PT_LOGGER.debug(
                    "%s: added attribute %s:%s", role, match_.group("key"), match_.group("value")
                )

        return role_service_match[0].end()

    @classmethod
    def build_policies(cls, policy_chars, policy):
        """Adds reachability policies to a Policy object as specified by a
        policy file.

        Args:
            policy_chars: A character string of a policy file's content.
            policy: A Policy object.
        """

        PT_LOGGER.debug("match policy regex")
        policy_matches = cls.match(cls.policies_regex, policy_chars)
        if policy_matches:
            for policy_match in policy_matches:
                PT_LOGGER.trace(policy_match.groupdict())

        if policy_matches:
            PT_LOGGER.debug("fetch first match")
            match = policy_matches[0]
            PT_LOGGER.trace("first match: %s", match.groupdict())

            PT_LOGGER.debug("fetch policies body")
            policies_chars = match.group("policies")
            PT_LOGGER.debug("policies body:\n%s", policies_chars)

            PT_LOGGER.debug("fetch default action")
            policy.set_default_policy(match.group("default"))
            PT_LOGGER.debug("default action: %s", match.group("default"))

            PT_LOGGER.debug("match single policies")
            single_policy_matches = cls.match(cls.policy_regex, policies_chars)
            for match in single_policy_matches:
                role_from, role_to, op_, service_to = match.group("role_from"), match.group("role_to"), match.group("op"), match.group("service_to")
                PT_LOGGER.debug("single policy: %s %s %s", role_from, op_, ("%s.%s" % (role_to, service_to) if service_to else role_to))

                if not policy.default_policy:
                    if op_ == "<->>":
                        policy.add_reachability_policy(role_from, role_to, service_to)
                        PT_LOGGER.debug("created uncoditional forth")
                        policy.add_reachability_policy(role_to, role_from, condition={"state": "RELATED,ESTABLISHED"})
                        PT_LOGGER.debug("created conditional back")
                    elif op_ == "--->" or op_ == "<-->":
                        cond = {"provider": role_to} if service_to else None
                        policy.add_reachability_policy(role_from, role_to, service_to, condition=cond)
                        PT_LOGGER.debug("created unconditional forth")
                        if op_ == "<-->":
                            policy.add_reachability_policy(role_to, role_from, service_to, condition=cond)
                            PT_LOGGER.debug("created unconditional back")
                    else:
                        PT_LOGGER.debug("operator %s not permitted with default %s", op_, policy.default_policy)
                else:
                    if op_ == "--/->" or op_ == "<-/->":
                        policy.add_reachability_policy(role_from, role_to, service_to)
                        PT_LOGGER.debug("created forbidden forth")
                        if op_ == "<-/->":
                            policy.add_reachability_policy(role_to, role_from, service_to)
                            PT_LOGGER.debug("created forbidden back")
                    elif op_ == "-/->>":
                        policy.add_reachability_policy(role_from, role_to, condition={"state": "NEW,INVALID"})
                        PT_LOGGER.debug("created conditionally forbidden forth")
                    else:
                        PT_LOGGER.debug("operator %s not permitted with default %s", op_, policy.default_policy)

        if not policy.strict:
            PT_LOGGER.debug("add default self reachability policies")
            for role in policy.get_atomic_roles():
                if not policy.policy_exists(role, role):
                    policy.add_reachability_policy(role, role)
                    PT_LOGGER.debug("self policy: %s ---> %s", role, role)


    @classmethod
    def replace_policy_with_csv(cls, csv, policy):
        """Replaces reachability policies of a Policy object as specified by a
        policy csv file.

        Args:
            csv: A list of string lists corresponding to the csv of the policy file.
            policy: A Policy object.
        """

        policy.clear_reachability()

        header = csv[0]

        for row in csv[1:]:
            role_from = row[0]

            for idx, role_to in enumerate(header[1:], start=1):
                if row[idx] == 'X':
                    policy.add_reachability_policy(role_from, role_to)
                elif row[idx] == '_':
                    policy.add_ignore_policy(role_from, role_to)


    @classmethod
    def match(cls, regex, chars, function=None):
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
