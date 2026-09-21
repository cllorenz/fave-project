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

from __future__ import annotations

import re

from typing import Any, Callable, List, Optional

from policy import Policy, Superrole
from policy_exceptions import InvalidSyntaxException, UnparsedBlockException
from policy_logger import PT_LOGGER

class PolicyBuilder(object):
    """Offers class methods to build a policy object from a policy and/or role
    file."""

    define_pattern = "(def | define | describe)"
    name_pattern = "[A-Za-z][A-Za-z0-9_]*"
    value_pattern = r"[A-Za-z0-9 _=\-\[\]'\":.,\*/]+"
    # CATASTROPHIC BACKTRACKING LIVES IN THE OVERLAP OF TWO QUANTIFIERS.
    # This used to read `[ \t]* \# [ \t]* .*`, where the second `[ \t]*` and
    # `.*` can both match the blanks after the `#`. That is the same language
    # -- `[ \t]*.*` accepts exactly what `.*` accepts -- but it gives the
    # engine one extra way to match EVERY comment line, so a run of n of them
    # before a definition has 2^n parses to explore before it can fail.
    #
    # Measured on bench/wl_cloud's inventory, searching a comment block for a
    # definition that never comes: 12 lines 0.010s, 16 lines 0.14s, 20 lines
    # 2.35s, 24 lines over two minutes. Blank lines made it WORSE, not better
    # (three blank-separated blocks of 8 measured 31.8s), because they are
    # another alternative in the same group. Documenting an inventory in this
    # repository's usual style was enough to hang the translator.
    #
    # Dropping the redundant quantifier is exactly equivalent and the exponent
    # goes away entirely -- 20 lines drops from 2.35s to under a millisecond.
    # test_policy_builder.py::TestCommentRunsAreLinear pins both halves.
    comment_pattern = r"[ \t]* \# .* (\r\n|[\r\n])"
    comment_pattern_nl = r"%s+" % comment_pattern
    # A comment may follow any line of a block, and may be a line of its own
    # INSIDE one. Neither used to parse: `role_content` was either a run of
    # attribute lines OR a run of comments, never interleaved, so a single
    # annotated role was dropped whole -- silently, until TODO.md item 15 made
    # an unparsed block an error. `policies_regex` below has always allowed
    # interleaved comments, and wl_ifi/reach_stateless.txt uses them, so a
    # writer met the inconsistency the first time they annotated a role.
    #
    # `line_comment` is the TRAILING form, and it is kept SEPARATE from
    # `value_pattern` rather than folded into it so that the `value` group holds
    # the value and nothing else.
    #
    # Folding `#` in would appear to work -- measured, and it passes every test
    # here -- but only because `Role.add_attribute` hands the group to
    # `ast.literal_eval`, which treats the trailing text as a PYTHON comment and
    # drops it. That is a coincidence between two languages, not a property of
    # this one: it holds for every value FPL currently has because they are all
    # Python literals, and it would stop holding the moment a consumer read the
    # group as text. `test_block_comments.py` pins the group's content directly
    # for that reason.
    line_comment = r"([ \t]* \# [^\r\n]*)?"
    block_comment = r"([ \t]* \# [^\r\n]* (\r\n|[\r\n])+)"

    role_pattern = r"""
    ((\r\n|[\r\n]) | %s)*
    %s [ ] role [ ] (?P<role_name> %s) (\r\n|[\r\n])+
    (?P<role_content>
        (((\t | [ ]{4}) %s [ \t]* = [ \t]*+ %s %s (\r\n|[\r\n])+)
        | ((\t | [ ]{4}) includes [ ] %s([.] (\* | %s) )? %s (\r\n|[\r\n])+)
        | ((\t | [ ]{4}) offers [ ] %s %s (\r\n|[\r\n])+)
        | %s)*
    )
    end (\r\n|[\r\n])+
    """ % (
        comment_pattern, define_pattern, name_pattern, name_pattern, value_pattern,
        line_comment, name_pattern, name_pattern, line_comment, name_pattern,
        line_comment, block_comment
    )
    service_pattern = r"""
    ((\r\n|[\r\n]) | %s)*
    %s [ ] service [ ] (?P<service_name> %s) (\r\n|[\r\n])+
    (?P<service_content>
        (((\t | [ ]{4}) %s [ \t]* = [ \t]*+ %s %s (\r\n|[\r\n])+)
        | %s)*
    )
    end (\r\n|[\r\n])+
    """ % (comment_pattern, define_pattern, name_pattern, name_pattern,
           value_pattern, line_comment, block_comment)

    # Every block the file DECLARES, found by its header alone. The parsers
    # above find a block only if the WHOLE block matches, and they search rather
    # than scan, so a malformed one is skipped while every block after it is
    # still found. Comparing the two is what turns that from a silent smaller
    # inventory into an error -- TODO.md item 15.
    #
    # `desc` is listed here although `define_pattern` does NOT accept it: that
    # divergence (fpl_grammar.py takes all four spellings, this parser three) is
    # itself a way to lose a block silently, so a `desc` block is reported as
    # unparsed rather than ignored.
    block_header_regex = re.compile(
        r"^[ \t]* (?P<keyword> def|define|describe|desc) [ ]+ "
        r"(?P<kind> role|service) [ ]+ (?P<name> %s)" % name_pattern,
        re.X | re.M
    )

    role_service_regex = re.compile(
        "(%s | %s | %s)+" % (comment_pattern, role_pattern, service_pattern),
        re.X
    )
    role_regex = re.compile(role_pattern, re.X)
    service_regex = re.compile(service_pattern, re.X)

    # THE EXTRACTORS MUST ALLOW THE TRAILING COMMENT TOO. The block patterns
    # above decide whether a role parses at all; these three decide what is
    # read OUT of it, and they run over the same text with `search`. Teaching
    # only the block patterns about comments would have turned a loud refusal
    # into a SILENT LOSS -- the role would parse and its annotated attribute,
    # `includes` or `offers` line would simply not be there. Measured while
    # making this change: `description = 'plain'  # note` left a role with no
    # description at all, and an annotated `offers` left a role offering
    # nothing, which surfaced only as "Service unknown" from the policy.
    #
    # The SAME defect, one line lower down: `value_pattern` contains a space,
    # so `[ \t]*` and the value both match the blanks after the `=` and every
    # attribute line doubles the search space of the role it sits in. Latent
    # rather than live -- no inventory in the tree has a role with enough
    # attributes to notice (18 of them measured 0.24s) -- but it is the same
    # bomb with a longer fuse.
    #
    # POSSESSIVE, not deleted: unlike the comment case the quantifier is load
    # bearing, because it is what keeps the blanks out of the captured
    # `value`. `*+` matches what the greedy form matches on its FIRST attempt
    # and then refuses to give any of it back.
    #
    # ONE INPUT CHANGES MEANING, deliberately: `key =   ` followed by nothing
    # but a newline. Backtracking used to hand one blank back so the value
    # could match, capturing a single space; it is now a syntax error. A value
    # made of one space is an artifact of the backtracking, not something any
    # inventory in this tree writes (checked), and an empty attribute is worth
    # refusing. Pinned by TestABlankAttributeValueIsRefused.
    role_attr_regex = re.compile(
        r"(\t | [ ]{4})(?P<key> %s) [ \t]* = [ \t]*+ (?P<value> %s | \*) %s (\r\n|[\r\n])+" % (name_pattern, value_pattern, line_comment),
        re.X
    )
    role_incl_regex = re.compile(
        r"(\t | [ ]{4}) includes [ ] (?P<role> %s)(.(?P<service> [\*] | %s))? %s (\r\n|[\r\n])+" % (name_pattern, name_pattern, line_comment),
        re.X
    )
    role_offers_regex = re.compile(
        r"(\t | [ ]{4}) offers [ ] (?P<service> %s) %s (\r\n|[\r\n])+" % (name_pattern, line_comment),
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
    def build(cls, policy_chars: str, policy: "Policy") -> None:
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
    def build_roles_and_services(cls, policy_chars: str, policy: "Policy") -> int:
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
        PT_LOGGER.trace("use policy string:\n"+policy_chars)
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
                superrole = policy.roles[role]
                assert isinstance(superrole, Superrole)  # just added via add_superrole
                for match_ in role_incl_matches:
                    superrole.add_subrole(match_.group("role"), service=match_.group("service"))
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

        cls._assert_every_block_parsed(
            policy_chars, role_matches, service_matches)

        return role_service_match[0].end()

    @classmethod
    def _assert_every_block_parsed(
            cls, policy_chars: str, role_matches: List[Any],
            service_matches: List[Any]
    ) -> None:
        """Every declared role and service block must have been parsed.

        The failure this prevents is not a wrong answer but a SMALLER question:
        the inventory loses a role, the policy compiles against what is left,
        and the run reports a clean verdict for a matrix that is missing a row
        and a column. Nothing downstream can notice, because nothing downstream
        knows how many blocks the file declared.
        """
        parsed = {
            ('role', match.group('role_name')) for match in role_matches
        } | {
            ('service', match.group('service_name')) for match in service_matches
        }

        declared = [
            (match.group('kind'), match.group('name'))
            for match in cls.block_header_regex.finditer(policy_chars)
        ]

        missing = [block for block in declared if block not in parsed]

        if missing:
            PT_LOGGER.error(
                "declared %d block(s), parsed %d; %s were skipped",
                len(declared), len(parsed), missing
            )
            raise UnparsedBlockException(missing)

    @classmethod
    def build_policies(cls, policy_chars: str, policy: "Policy") -> None:
        """Adds reachability policies to a Policy object as specified by a
        policy file.

        Args:
            policy_chars: A character string of a policy file's content.
            policy: A Policy object.
        """

        PT_LOGGER.debug("match policy regex")
        PT_LOGGER.trace("use policy string:\n"+policy_chars)
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

                policy.raw_policies[(role_from, role_to, service_to, op_)] = None

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
            # SORTED, and this is the site that is easy to miss. The two in
            # `to_iptables` reorder a block directly; this one reorders the
            # order policies are INSERTED into `Policy.policies`, and
            # `to_iptables` walks that dict to emit its Access Rules block. So
            # a `set` here moved rules in a file two modules away.
            #
            # Inert for the same reason: every rule in that block ends in
            # `jumptarget`, which is computed from `default_policy` alone and
            # is therefore the same for every policy -- the block is
            # single-action. The CSV, the prosa and the roles JSON are NOT
            # affected (measured across eight seeds: one output each), because
            # they iterate `roles` or sort for themselves.
            for role in sorted(policy.get_atomic_roles()):
                if not policy.policy_exists(role, role):
                    policy.add_reachability_policy(role, role)
                    PT_LOGGER.debug("self policy: %s ---> %s", role, role)


    @classmethod
    def replace_policy_with_csv(cls, csv: List[List[str]], policy: "Policy") -> None:
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
    def match(cls, regex: "re.Pattern[str]", chars: str, function: Optional[Callable[..., Any]] = None) -> List[Any]:
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

        match: Any = True
        matches: List[Any] = []
        start_pos = 0
        function = regex.match if function is None else function

        while match:
            match = function(chars, start_pos)
            if match:
                matches.append(match)
                start_pos = match.end()

        return matches
