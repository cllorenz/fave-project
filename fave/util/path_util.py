# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" This module provides utilities and a class to convert paths between JSON and
    a regex string representation.
"""

from __future__ import annotations

import json
import re

from typing import List, Optional, Tuple, Union, cast

from util.typing_util import JSONDict

PATH_PATHLETS = ['end', 'start', 'skip', 'skip_next']
STR_PATHLETS = ['^', '$', '.', '.*']

PORT_VALUE = r"[a-zA-Z0-9][a-zA-Z0-9-_]*(\.[a-zA-Z0-9-_]+)*\.[a-zA-Z0-9-_]+"
TABLE_VALUE = r"[a-zA-Z0-9][a-zA-Z0-9-_]*(\.[a-zA-Z0-9-_]+)*"

PORT = r"\.\*\(port=(?P<value>%s)\)" % PORT_VALUE
NPORTS = r"\(port in \((?P<value>(%s,)*%s)\)\)" % (PORT_VALUE, PORT_VALUE)
LPORTS = r"\.\*\(port in \((?P<value>(%s,)*%s)\)\)\$" % (PORT_VALUE, PORT_VALUE)
TABLE = r"\.\*\(table=(?P<value>%s)\)" % TABLE_VALUE
NTABLES = r"\(table in \((?P<value>(%s,)*%s)\)\)" % (TABLE_VALUE, TABLE_VALUE)
LTABLES = r"\.\*\(table in \((?P<value>(%s,)*%s)\)\)\$" % (TABLE_VALUE, TABLE_VALUE)

PORT_REGEX = re.compile("^%s$" % PORT)
NPORTS_REGEX = re.compile("^%s$" % NPORTS)
LPORTS_REGEX = re.compile("^%s$" % LPORTS)
TABLE_REGEX = re.compile("^%s$" % TABLE)
NTABLES_REGEX = re.compile("^%s$" % NTABLES)
LTABLES_REGEX = re.compile("^%s$" % LTABLES)


SPORT = r"\.\*\(p=(?P<value>%s)\)" % PORT_VALUE
SNPORTS = r"\(p in \((?P<value>(%s,)*%s)\)\)" % (PORT_VALUE, PORT_VALUE)
SLPORTS = r"\.\*\(p in \((?P<value>(%s,)*%s)\)\)\$" % (PORT_VALUE, PORT_VALUE)
STABLE = r"\.\*\(t=(?P<value>%s)\)" % TABLE_VALUE
SNTABLES = r"\(t in \((?P<value>(%s,)*%s)\)\)" % (TABLE_VALUE, TABLE_VALUE)
SLTABLES = r"\.\*\(t in \((?P<value>(%s,)*%s)\)\)\$" % (TABLE_VALUE, TABLE_VALUE)

SPORT_REGEX = re.compile("^%s" % SPORT)
SNPORTS_REGEX = re.compile("^%s" % SNPORTS)
SLPORTS_REGEX = re.compile("^%s" % SLPORTS)
STABLE_REGEX = re.compile("^%s" % STABLE)
SNTABLES_REGEX = re.compile("^%s" % SNTABLES)
SLTABLES_REGEX = re.compile("^%s" % SLTABLES)


def check_pathlet(pathlet: str) -> bool:
    """ Checks if a pathlet is valid.

    Keyword arguments:
    pathlet -- a pathlet
    """

    return pathlet in PATH_PATHLETS or \
        re.match(PORT_REGEX, pathlet)    is not None or \
        re.match(NPORTS_REGEX, pathlet)  is not None or \
        re.match(LPORTS_REGEX, pathlet)  is not None or \
        re.match(TABLE_REGEX, pathlet)   is not None or \
        re.match(NTABLES_REGEX, pathlet) is not None or \
        re.match(LTABLES_REGEX, pathlet) is not None


def check_str_pathlet(pathlet: str) -> bool:
    """ Checks if a string represents a valid pathlet.

    Keyword arguments:
    pathlet -- a pathlet string
    """

    return pathlet in STR_PATHLETS or \
        re.match(SPORT_REGEX, pathlet)    is not None or \
        re.match(SNPORTS_REGEX, pathlet)  is not None or \
        re.match(SLPORTS_REGEX, pathlet)  is not None or \
        re.match(STABLE_REGEX, pathlet)   is not None or \
        re.match(SNTABLES_REGEX, pathlet) is not None or \
        re.match(SLTABLES_REGEX, pathlet) is not None


def pathlet_to_str(pathlet: str) -> Optional[str]:
    """ Converts a pathlet to a string.

    Keyword arguments:
    pathlet -- a pathlet
    """

    conv = {
        'start' : '^',
        'end' : '$',
        'skip' : '.',
        'skip_next' : '.*'
    }

    if pathlet in conv:
        return conv[pathlet]

    match = re.match(PORT_REGEX, pathlet)
    if match:
        return ".*(p=%s)" % match.group('value')

    match = re.match(NPORTS_REGEX, pathlet)
    if match:
        return "(p in (%s))" % match.group('value')

    match = re.match(LPORTS_REGEX, pathlet)
    if match:
        return ".*(p in (%s))$" % match.group('value')

    match = re.match(TABLE_REGEX, pathlet)
    if match:
        return ".*(t=%s)" % match.group('value')

    match = re.match(NTABLES_REGEX, pathlet)
    if match:
        return "(t in (%s))" % match.group('value')

    match = re.match(LTABLES_REGEX, pathlet)
    if match:
        return ".*(t in (%s))$" % match.group('value')

    return None


def str_to_pathlet(paths: str) -> Optional[Tuple[str, int]]:
    """ Converts a path string to a pathlet.

    Keyword arguments:
    paths -- a path string
    """

    match = re.match(SPORT_REGEX, paths)
    if match:
        return ".*(port=%s)" % match.group("value"), match.end()

    match = re.match(SNPORTS_REGEX, paths)
    if match:
        return "(port in (%s))" % match.group('value'), match.end()

    match = re.match(SLPORTS_REGEX, paths)
    if match:
        return ".*(port in (%s))$" % match.group('value'), match.end()

    match = re.match(STABLE_REGEX, paths)
    if match:
        return ".*(table=%s)" % match.group('value'), match.end()

    match = re.match(SNTABLES_REGEX, paths)
    if match:
        return "(table in (%s))" % match.group('value'), match.end()

    match = re.match(SLTABLES_REGEX, paths)
    if match:
        return ".*(table in (%s))$" % match.group('value'), match.end()

    if paths.startswith('^'):
        return 'start', 1
    elif paths.startswith('$'):
        return 'end', 1
    elif paths.startswith('.*'):
        return 'skip_next', 2
    elif paths.startswith('.'):
        return 'skip', 1

    return None



def pathlet_to_json(pathlet: str) -> Optional[JSONDict]:
    """ Converts a pathlet to JSON.

    Keyword arguments:
    pathlet -- a pathlet
    """

    if pathlet in ['start', 'end', 'skip', 'skip_next']:
        return {'type':pathlet}

    match = re.match(PORT_REGEX, pathlet)
    if match:
        return {"type":"port", "port":match.group('value')}

    match = re.match(NPORTS_REGEX, pathlet)
    if match:
        return {"type":"next_ports", "ports":match.group('value').split(',')}

    match = re.match(LPORTS_REGEX, pathlet)
    if match:
        return {"type":"last_ports", "ports":match.group('value').split(',')}

    match = re.match(TABLE_REGEX, pathlet)
    if match:
        return {"type":"table", "table":match.group('value')}

    match = re.match(NTABLES_REGEX, pathlet)
    if match:
        return {"type":"next_tables", "tables":match.group('value').split(',')}

    match = re.match(LTABLES_REGEX, pathlet)
    if match:
        return {"type":"last_tables", "tables":match.group('value').split(',')}

    return None


def json_to_pathlet(j: JSONDict) -> str:
    """ Creates a pathlet from JSON.

    Keyword arguments:
    j -- a JSON object
    """

    ptype = j["type"]
    # the dispatch always yields a pathlet string
    return cast(str, {
        'start' : lambda: ptype,
        'end' : lambda: ptype,
        'skip' : lambda: ptype,
        'skip_next' : lambda: ptype,
        'port' : lambda: ".*(port=%s)" % j["port"],
        'next_ports' : lambda: "(port in (%s))" % ','.join(j["ports"]),
        'last_ports' : lambda: ".*(port in (%s))$" % ','.join(j["ports"]),
        'table' : lambda: ".*(table=%s)" % j["table"],
        'next_tables' : lambda: "(table in (%s))" % ','.join(j["tables"]),
        'last_tables' : lambda: ".*(table in (%s))$" % ','.join(j["tables"])
    }[ptype]())


def _normalize_pathlet(pathlet: str) -> str:
    if check_str_pathlet(pathlet):
        result = str_to_pathlet(pathlet)
        assert result is not None  # guaranteed by check_str_pathlet
        return result[0]
    elif check_pathlet(pathlet):
        return pathlet
    else:
        raise Exception("unable to parse pathlet: %s" % pathlet)


class Path(object):
    """ This class stores a path.
    """

    def __init__(self, pathlets: Optional[List[str]] = None) -> None:
        """ Constructs a path from a list of pathlets.

        Keyword arguments:
        pathlets -- a list of pathlets (Default: [])
        """

        if pathlets is not None:
            self.pathlets = [_normalize_pathlet(p) for p in pathlets]
        else:
            self.pathlets = []


    def to_json(self) -> JSONDict:
        """ Converts the path to JSON.
        """
        return {
            'pathlets' : [pathlet_to_json(p) for p in self.pathlets]
        }


    @staticmethod
    def from_json(j: Union[str, JSONDict]) -> "Path":
        """ Creates a path from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        jd: JSONDict = json.loads(j) if isinstance(j, str) else j

        return Path(pathlets=[json_to_pathlet(p) for p in jd['pathlets']])


    def __str__(self) -> str:
        parts = []
        for pathlet in self.pathlets:
            part = pathlet_to_str(pathlet)
            assert part is not None  # pathlets are normalized/valid by construction
            parts.append(part)
        return ''.join(parts)


    @staticmethod
    def from_string(paths: str) -> "Path":
        """ Creates path from regex string.

        Keyword arguments:
        paths -- a path regex string
        """

        pathlets = []
        while paths:
            result = str_to_pathlet(paths)
            assert result is not None  # non-empty path must yield a pathlet
            pathlet, end = result
            pathlets.append(pathlet)
            paths = paths[end:]
        return Path(pathlets=pathlets)


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Path):
            return NotImplemented
        return self.pathlets == other.pathlets
