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

class PolicyException(Exception):
    def __str__(self):
        return self.message

class NameTakenException(PolicyException):
    def __init__(self, name):
        self.message = "Name %s bereits vergeben." % name

class RoleUnknownException(PolicyException):
    def __init__(self, role):
        self.message = "Rolle %s unbekannt." % role

class ServiceUnknownException(PolicyException):
    def __init__(self, service, role=None):
        if role is not None:
            self.message = "Service %s.%s unbekannt." % (role, service)
        else:
            self.message = "Service %s unbekannt." % service

class InvalidSyntaxException(PolicyException):
    def __init__(self):
        self.message = "Ungültige Syntax."

class InvalidAttributeException(PolicyException):
    def __init__(self, name):
        self.message = "Attribut %s ist ungültig." % name

class InvalidValueException(PolicyException):
    def __init__(self, attribute, value):
        self.message = "Attributwert %s  = %s ist ungültig." % (attribute, value)
