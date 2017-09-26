import json
import re

path_pathlets = ['end','start','skip']
str_pathlets  = ['^','$','.']

pv = '\w+\.\d+'
tv = '\w+'

port    = '\.\*\(port=(?P<value>%s)\)' % pv
nports  = '\(port in \((?P<value>(%s,)*%s)\)\)' % (pv,pv)
lports  = '\.\*\(port in \((?P<value>(%s,)*%s)\)\)\$' % (pv,pv)
table   = '\.\*\(table=(?P<value>%s)\)' % tv
ntables = '\(table in \((?P<value>(%s,)*%s)\)\)' % (tv,tv)
ltables = '\.\*\(table in \((?P<value>(%s,)*%s)\)\)\$' % (tv,tv)

port_regex    = re.compile("^%s$"%port)
nports_regex  = re.compile("^%s$"%nports)
lports_regex  = re.compile("^%s$"%lports)
table_regex   = re.compile("^%s$"%table)
ntables_regex = re.compile("^%s$"%ntables)
ltables_regex = re.compile("^%s$"%ltables)


sport = "\.\*\(p=(?P<value>%s)\)" % pv
snports = "\(p in \((?P<value>(%s,)*%s)\)\)" % (pv,pv)
slports = "\.\*\(p in \((?P<value>(%s,)*%s)\)\)\$" % (pv,pv)
stable = "\.\*\(t=(?P<value>%s)\)" % tv
sntables = "\(t in \((?P<value>(%s,)*%s)\)\)" % (tv,tv)
sltables = "\.\*\(t in \((?P<value>(%s,)*%s)\)\)\$" % (tv,tv)

sport_regex = re.compile("^%s" % sport)
snports_regex = re.compile("^%s" % snports)
slports_regex = re.compile("^%s" % slports)
stable_regex = re.compile("^%s" % stable)
sntables_regex = re.compile("^%s" % sntables)
sltables_regex = re.compile("^%s" % sltables)


def check_pathlet(pathlet):
    return pathlet in path_pathlets or \
        re.match(port_regex,pathlet)    is not None or \
        re.match(nports_regex,pathlet)  is not None or \
        re.match(lports_regex,pathlet)  is not None or \
        re.match(table_regex,pathlet)   is not None or \
        re.match(ntables_regex,pathlet) is not None or \
        re.match(ltables_regex,pathlet) is not None


def pathlet_to_str(pathlet):
    if pathlet == 'start':
        return '^'
    elif pathlet == 'end':
        return '$'
    elif pathlet == 'skip':
        return '.'

    match = re.match(port_regex,pathlet)
    if match:
        return ".*(p=%s)" % match.group('value')

    match = re.match(nports_regex,pathlet)
    if match:
        return "(p in (%s))" % match.group('value')

    match = re.match(lports_regex,pathlet)
    if match:
        return ".*(p in (%s))$" % match.group('value')

    match = re.match(table_regex,pathlet)
    if match:
        return ".*(t=%s)" % match.group('value')

    match = re.match(ntables_regex,pathlet)
    if match:
        return "(t in (%s))" % match.group('value')

    match = re.match(ltables_regex,pathlet)
    if match:
        return ".*(t in (%s))$" % match.group('value')


def str_to_pathlet(s):
    match = re.match(sport_regex,s)
    if match:
        return ".*(port=%s)" % match.group("value"),match.end()

    match = re.match(snports_regex,s)
    if match:
        return "(port in (%s))" % match.group('value'),match.end()

    match = re.match(slports_regex,s)
    if match:
        return ".*(port in (%s))$" % match.group('value'),match.end()

    match = re.match(stable_regex,s)
    if match:
        return ".*(table=%s)" % match.group('value'),match.end()

    match = re.match(sntables_regex,s)
    if match:
        return "(table in (%s))" % match.group('value'),match.end()

    match = re.match(sltables_regex,s)
    if match:
        return ".*(table in (%s))$" % match.group('value'),match.end()

    if s.startswith('^'):
        return 'start',1
    elif s.startswith('$'):
        return 'end',1
    elif s.startswith('.'):
        return 'skip',1



def pathlet_to_json(pathlet):
    if pathlet == 'start':
        return {"type":"start"}
    elif pathlet == 'end':
        return {"type":"end"}
    elif pathlet == 'skip':
        return {"type":"skip"}

    match = re.match(port_regex,pathlet)
    if match:
        return {"type":"port","port":match.group('value')}

    match = re.match(nports_regex,pathlet)
    if match:
        return {"type":"next_ports","ports":match.group('value').split(',')}

    match = re.match(lports_regex,pathlet)
    if match:
        return {"type":"last_ports","ports":match.group('value').split(',')}

    match = re.match(table_regex,pathlet)
    if match:
        return {"type":"table","table":match.group('value')}

    match = re.match(ntables_regex,pathlet)
    if match:
        return {"type":"next_tables","tables":match.group('value').split(',')}

    match = re.match(ltables_regex,pathlet)
    if match:
        return {"type":"last_tables","tables":match.group('value').split(',')}


def json_to_pathlet(j):
    ptype = j["type"]
    if ptype == "start":
        return "start"
    elif ptype == "end":
        return "end"
    elif ptype == "skip":
        return "skip"
    elif ptype == "port":
        return ".*(port=%s)" % j["port"]
    elif ptype == "next_ports":
        return "(port in (%s))" % ','.join(j["ports"])
    elif ptype == "last_ports":
        return ".*(port in (%s))$" % ','.join(j["ports"])
    elif ptype == "table":
        return ".*(table=%s)" % j["table"]
    elif ptype == "next_tables":
        return "(table in (%s))" % ','.join(j["tables"])
    elif ptype == "last_tables":
        return ".*(table in (%s))$" % ','.join(j["tables"])


class Path(object):
    def __init__(self,pathlets=[]):
        self.pathlets = [p for p in pathlets if check_pathlet(p)]
        assert(pathlets == self.pathlets)

    def to_json(self):
        return {
            'pathlets' : [pathlet_to_json(p) for p in self.pathlets]
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        return Path(pathlets=[json_to_pathlet(p) for p in j['pathlets']])

    def to_string(self):
        return ''.join([pathlet_to_str(p) for p in self.pathlets])

    @staticmethod
    def from_string(s):
        pathlets = []
        while s:
            pathlet,end = str_to_pathlet(s)
            pathlets.append(pathlet)
            s = s[end:]
        return Path(pathlets=pathlets)

    def __eq__(self,other):
        return self.pathlets == other.pathlets
