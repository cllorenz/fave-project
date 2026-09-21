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

class InvalidAttributeException(PolicyException):
    def __init__(self, name: str) -> None:
        self.message = "Attribut %s ist ungültig." % name

class InvalidValueException(PolicyException):
    def __init__(self, attribute: str, value: Any) -> None:
        self.message = "Attributwert %s = %s ist ungültig." % (attribute, value)
