""" This module provides utilities and a class to convert paths between JSON and
    a regex string representation.
"""

import json
import re

PATH_PATHLETS = ['end', 'start', 'skip', 'skip_next']
STR_PATHLETS = ['^', '$', '.', '.*']

PORT_VALUE = r"\w+(\.\w+)*\.\d+"
TABLE_VALUE = r"\w+(\.\w+)*"

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


def check_pathlet(pathlet):
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


def check_str_pathlet(pathlet):
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


def pathlet_to_str(pathlet):
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


def str_to_pathlet(paths):
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



def pathlet_to_json(pathlet):
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


def json_to_pathlet(j):
    """ Creates a pathlet from JSON.

    Keyword arguments:
    j -- a JSON object
    """

    ptype = j["type"]
    return {
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
    }[ptype]()


def _normalize_pathlet(pathlet):
    if check_str_pathlet(pathlet):
        return str_to_pathlet(pathlet)[0]
    elif check_pathlet(pathlet):
        return pathlet


class Path(object):
    """ This class stores a path.
    """

    def __init__(self, pathlets=None):
        """ Constructs a path from a list of pathlets.

        Keyword arguments:
        pathlets -- a list of pathlets (Default: [])
        """

        if pathlets is not None:
            self.pathlets = [_normalize_pathlet(p) for p in pathlets]
        else:
            self.pathlets = []


    def to_json(self):
        """ Converts the path to JSON.
        """
        return {
            'pathlets' : [pathlet_to_json(p) for p in self.pathlets]
        }


    @staticmethod
    def from_json(j):
        """ Creates a path from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        return Path(pathlets=[json_to_pathlet(p) for p in j['pathlets']])


    def __str__(self):
        return ''.join([pathlet_to_str(p) for p in self.pathlets])


    @staticmethod
    def from_string(paths):
        """ Creates path from regex string.

        Keyword arguments:
        paths -- a path regex string
        """

        pathlets = []
        while paths:
            pathlet, end = str_to_pathlet(paths)
            pathlets.append(pathlet)
            paths = paths[end:]
        return Path(pathlets=pathlets)


    def __eq__(self, other):
        return self.pathlets == other.pathlets
