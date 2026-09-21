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

class InvalidAttributeException(PolicyException):
    def __init__(self, name: str) -> None:
        self.message = "Attribut %s ist ungültig." % name

class InvalidValueException(PolicyException):
    def __init__(self, attribute: str, value: Any) -> None:
        self.message = "Attributwert %s = %s ist ungültig." % (attribute, value)
