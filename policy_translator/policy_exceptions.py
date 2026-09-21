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
        self.message = "Name %s bereits vergeben." % name

class RoleUnknownException(PolicyException):
    def __init__(self, role: str) -> None:
        self.message = "Rolle %s unbekannt." % role

class ServiceUnknownException(PolicyException):
    def __init__(self, service: str, role: Optional[str] = None) -> None:
        if role is not None:
            self.message = "Service %s.%s unbekannt." % (role, service)
        else:
            self.message = "Service %s unbekannt." % service

class InvalidSyntaxException(PolicyException):
    def __init__(self) -> None:
        self.message = "Ungültige Syntax."

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
            "Nicht lesbare Blöcke: %s. Deklariert, aber nicht geparst -- der "
            "Block wurde übersprungen, nicht abgelehnt. Häufigste Ursache: ein "
            "Zeichen im Attributwert, das die Grammatik nicht kennt "
            "(erlaubt sind Buchstaben, Ziffern und _=-[]'\":.,*/ und "
            "Leerzeichen; ein `+` etwa nicht). Auch `desc` als Schlüsselwort "
            "wird hier nicht akzeptiert, anders als in fpl_grammar.py."
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
            "Rolle %s bietet keine Services an, daher ist %s.* leer. Eine "
            "leere Bedingungsliste bedeutet in FPL uneingeschränkte "
            "Erreichbarkeit -- die Regel wäre also weiter als geschrieben. "
            "Services werden nach UNTEN vererbt, nicht nach oben: eine "
            "Superrolle bietet an, was ihre eigenen `offers`-Zeilen nennen "
            "(bzw. ein `includes <Rolle>.<Service>`), nicht das, was ihre "
            "Mitglieder anbieten. Entweder `offers` ergänzen oder den Dienst "
            "in der Regel explizit nennen." % (role, role)
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
            "Bedingung %s = %s kann nicht als CSV dargestellt werden: der Wert "
            "enthält ein Komma und würde die Zelle zerteilen. Bekannt ist nur "
            "`state = RELATED,ESTABLISHED`, das als `X` geschrieben wird."
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
            "Service %s: %r ist kein IP-Protokoll. Erlaubt sind %s. "
            "`protocol` bezeichnet ausschließlich ein IP-Protokoll -- Layer-2-"
            "Protokolle wie ARP lassen sich damit nicht ausdrücken (dafür wäre "
            "ein eigenes Attribut nötig), und eine Protokollnummer ist kein "
            "gültiger Wert, da beide Verbraucher den Namen erwarten."
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
            "Regel %s -> %s nennt einen Port (%s) ohne Protokoll. iptables "
            "kann einen Port nur zusammen mit `-p` prüfen, und ein angenommenes "
            "`tcp` wäre eine erfundene Richtlinie. Dem Service ein `protocol` "
            "geben."
        ) % (role_from, role_to, service_port)


class InvalidAttributeException(PolicyException):
    def __init__(self, name: str) -> None:
        self.message = "Attribut %s ist ungültig." % name

class InvalidValueException(PolicyException):
    def __init__(self, attribute: str, value: Any) -> None:
        self.message = "Attributwert %s = %s ist ungültig." % (attribute, value)
