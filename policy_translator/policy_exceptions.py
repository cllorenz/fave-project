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

from typing import Any, List, Optional, Tuple


class PolicyException(Exception):
    message: str

    def __str__(self) -> str:
        return self.message

class NameTakenException(PolicyException):
    def __init__(self, name: str) -> None:
        self.message = "Name %s is already taken." % name

class RoleUnknownException(PolicyException):
    def __init__(self, role: str) -> None:
        self.message = "Role %s is unknown." % role

class ServiceUnknownException(PolicyException):
    def __init__(self, service: str, role: Optional[str] = None) -> None:
        if role is not None:
            self.message = "Service %s.%s is unknown." % (role, service)
        else:
            self.message = "Service %s is unknown." % service

class InvalidSyntaxException(PolicyException):
    def __init__(self) -> None:
        self.message = "Invalid syntax."

class UnparsedBlockException(PolicyException):
    """A block the inventory DECLARES but the parser did not produce.

    `PolicyBuilder` finds role and service blocks with `regex.search` over the
    whole file, so a malformed one is simply not found while every block after
    it still is. Without this the result was a smaller inventory, a policy that
    compiled against what survived, and exit 0 -- see TODO.md item 15, where
    eight of wl_cloud's 25 roles vanished because their description contained a
    `+`.
    """

    def __init__(self, blocks: List[Tuple[str, str]]) -> None:
        listing = ", ".join("%s %s" % (kind, name) for kind, name in blocks)
        self.message = (
            "Unreadable block(s): %s. Declared, but not parsed -- the block "
            "was skipped rather than rejected. Most common cause: a character "
            "in an attribute value the grammar does not know (letters, digits "
            "and _=-[]'\":.,*/ and spaces are allowed; a `+`, for instance, is "
            "not). `desc` as a keyword is also not accepted here, unlike in "
            "fpl_grammar.py."
        ) % listing

class NoServicesOfferedException(PolicyException):
    """`X ---> Y.*` where `Y` offers nothing, which cannot mean what it says.

    An empty condition list is how FPL spells UNCONDITIONAL reachability, and
    `ReachabilityPolicy.update_conditions` states that "the empty list
    overpowers all other lists of conditions" -- so a wildcard that resolved to
    no service did not merely fail to restrict its own rule, it ERASED whatever
    an earlier rule had established for the same pair. `Internet ---> Server.*`
    in `examples/ifi-policy.txt` did exactly that, and the cell came out a bare
    `X` (TODO item 19).

    A writer naming `.*` is asking for the services a role offers. If there are
    none, every available reading -- "no traffic" and "all traffic" -- is a
    guess, so the rule is refused instead.

    Services travel DOWN, so the usual cause over a superrole is a group that
    declares no `offers` of its own: its members' services are theirs, not the
    group's, and `SR.*` is empty however much the members offer.
    """

    def __init__(self, role: str) -> None:
        self.message = (
            "Role %s offers no services, so %s.* is empty. In FPL an empty "
            "condition list means UNRESTRICTED reachability, so the rule "
            "would be wider than written. Services are inherited DOWNWARDS, "
            "not upwards: a superrole offers what its own `offers` lines name "
            "(or an `includes <Role>.<Service>`), not what its members offer. "
            "Either add an `offers` line or name the service in the rule "
            "explicitly." % (role, role)
        )

class UnrenderableConditionException(PolicyException):
    """A condition value the CSV cannot carry, refused instead of written.

    A cell is comma-separated, so a value containing a comma silently splits it
    and the row ends up with more fields than the header has columns. The one
    such value in the language, `state = RELATED,ESTABLISHED`, has always been
    spelled `X` instead; `-/->>` produces `state = NEW,INVALID`, which had no
    spelling and so corrupted the file -- `(state:NEW` and `INVALID)` in
    adjacent columns, and no error.

    No inventory in the tree writes `-/->>`, so this refuses a shape that is
    reachable rather than one that is used. Giving it a rendering would mean
    giving every consumer of the matrix a new token to understand, which is a
    language decision; corrupting the file quietly is not an option either way.
    """

    def __init__(self, field: str, value: Any) -> None:
        self.message = (
            "Condition %s = %s cannot be rendered as CSV: the value contains "
            "a comma and would split the cell. The only known such value is "
            "`state = RELATED,ESTABLISHED`, which is written as `X`."
        ) % (field, value)

class UnknownProtocolException(PolicyException):
    """A service naming something that is not an IP protocol.

    `protocol` is an IP protocol and nothing else: both consumers of a service
    map it to `packet.ipv6.proto` (`fave/util/match_util.py` and
    `fave/iptables/generator.py`), so a value outside that vocabulary is one
    neither the model nor a firewall can represent.

    It was not checked anywhere, and the three renderers disagreed about what
    to do with it: `roles_to_csv` wrote `protocol:1616` without complaint,
    `to_iptables` raised `TypeError` on an int and `KeyError('port')` on a name
    with no port, and FaVe's `normalize_ipv6_proto` rejects both -- so a matrix
    could compile into checks the verifier could not read. Refused at the
    declaration now, where the writer can act on it (TODO item 21).

    Layer 2 is deliberately out of scope rather than forgotten: FPL expresses
    it through role attributes (`vlan`), and a service-level `l2proto` would be
    the way to say ARP if a policy ever needs to (owner, 2026-09-21).
    """

    def __init__(self, service: str, value: Any, known: List[str]) -> None:
        self.message = (
            "Service %s: %r is not an IP protocol. Allowed are %s. `protocol` "
            "denotes an IP protocol and nothing else -- layer 2 protocols such "
            "as ARP cannot be expressed with it (that would need an attribute "
            "of its own), and a protocol NUMBER is not a valid value either, "
            "because both consumers expect the name."
        ) % (service, value, ", ".join(known))


class PortWithoutProtocolException(PolicyException):
    """A service naming a port but no protocol, at the point of writing a
    firewall rule.

    Refused HERE rather than at the declaration, because the two targets differ
    in what they can express: FaVe matches `packet.upper.dport` independently of
    the upper protocol, so a port-only service is meaningful in the model and in
    the matrix. iptables cannot match a port without `-p`, and choosing tcp on
    the writer's behalf would invent policy.

    `to_iptables` used to build no service match at all for such a service and
    then drop the rule entirely, because the emission is guarded by `if
    serviceinfo`. Under a default-deny ruleset that silently withholds traffic
    the policy PERMITS -- the generated firewall no longer implements the
    specification it was derived from (TODO item 21).
    """

    def __init__(self, service_port: Any, role_from: str, role_to: str) -> None:
        self.message = (
            "Rule %s -> %s names a port (%s) but no protocol. iptables can "
            "only match a port together with `-p`, and assuming `tcp` would "
            "invent policy. Give the service a `protocol`."
        ) % (role_from, role_to, service_port)


class InvalidAttributeException(PolicyException):
    def __init__(self, name: str) -> None:
        self.message = "Attribute %s is invalid." % name

class InvalidValueException(PolicyException):
    def __init__(self, attribute: str, value: Any) -> None:
        self.message = "Attribute value %s = %s is invalid." % (attribute, value)
