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

import itertools

from aggregator_singleton import AGGREGATOR

import netplumber.jsonrpc as jsonrpc
from aggregator_util import normalize_port, calc_rule_index, calc_port
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import copy_field_between_vectors, set_field_in_vector
from netplumber.vector import align_headerspace
from netplumber.vector import Vector, HeaderSpace

from ip6np.generator import field_value_to_bitvector

from openflow.rule import SwitchRule, Match, Forward, Miss, Rewrite, SwitchRuleField


class NetPlumberAdapter(object):

    def __init__(self, sock, logger):
        self.sock = sock
        self.mapping = Mapping(0)
        self.mapping_keys = set(self.mapping.keys())
        self.tables = {}
        self.model_types = {}
        self.links = {}
        self.fresh_table_index = 1
        self.ports = {}
        self.rule_ids = {}
        self.generators = {}
        self.probes = {}
        self.logger = logger

    def stop(self):
        jsonrpc.stop(self.sock)

    def dump_flows(self, odir):
        jsonrpc.dump_flows(self.sock, odir)

    def dump_plumbing_network(self, odir):
        jsonrpc.dump_plumbing_network(self.sock, odir)

    def dump_pipes(self, odir):
        jsonrpc.dump_pipes(self.sock, odir)

    def dump_flow_trees(self, odir):
        jsonrpc.dump_flow_trees(self.sock, odir)

    def expand(self):
        jsonrpc.expand(self.sock, self.mapping.length)

    def add_links_bulk(self, links):
        jsonrpc.add_links_bulk(
            self.sock,
            [(
                self.global_port(src),
                self.global_port(dst)
            ) for src, dst in links]
        )

    def remove_link(self, sport, dport):
        jsonrpc.remove_link(self.net_plumber.sock, sport, dport)
        del self.links[sport]


    def extend_mapping(self, mapping):
        assert isinstance(mapping, Mapping)

        self.mapping.expand(mapping)


    def _expand_field(self, field):
        """ Expands a negated field to a set of vectors.

        Keyword argument:
        field -- a negated field to be expanded
        """

        assert isinstance(field, SwitchRuleField)

        vec = field_value_to_bitvector(field)
        nvectors = []
        for idx, bit in enumerate(vec.vector):
            if bit == '0':
                nvec = dc(vec)
                nvec.vector = "x"*idx + "1" + "x"*(nvec.length-idx-1)
                nvectors.append(nvec)
            elif bit == '1':
                nvec = dc(vec)
                nvec.vector = "x"*idx + "0" + "x"*(nvec.length-idx-1)
                nvectors.append(nvec)
            else: # 'x'
                continue

        return nvectors


    def _expand_negations(self, match):
        """ Expands a match with negated fields to a set of vectors.

        Keyword arguments:
        match -- a match to be expanded
        """

        assert isinstance(match, Match)
        fields = set([f.name for f in match])
        self._update_mapping(fields)

        field_vectors = {}
        for idx, field in enumerate(match):
            if field.negated:
                field_vectors[field.name] = self._expand_field(field)
            else:
                field_vectors[field.name] = [field_value_to_bitvector(field)]

        matches = []

        keys = sorted(fields)
        combinations = itertools.product(*(field_vectors[k] for k in keys))

        for comb in combinations:
            vec = Vector(self.mapping.length)
            for i, name in enumerate(keys):
                set_field_in_vector(
                    self.mapping, vec, name, comb[i].vector
                )
            matches.append(vec)

        return matches


    def _update_mapping(self, field_names):
        diff = field_names - self.mapping_keys

        if diff:
            for field in diff:
                self.mapping.extend(field)
            self.mapping_keys.update(diff)
            self.expand()


    def _build_vector(self, fields, preset='x'):
        self._update_mapping(set([f.name for f in fields]))

        vec = Vector(length=self.mapping.length, preset=preset)
        for field in fields:
            set_field_in_vector(
                self.mapping,
                vec,
                field.name,
                field_value_to_bitvector(field).vector
            )

        return vec


    def add_slice(self, slicem):
        sid = slicem.sid

        ns_list = []
        for ns in slicem.ns_list:
            vec = self._build_vector(ns)
            ns_list.append(vec)

        for ns in slicem.ns_diff:
            vec = self._build_vector(ns)
            ns_diff.append(vec)

        self.logger.debug(
            "worker: add slice %s to netplumber with list %s and diff %s", sid, ns_list, ns_diff if ns_diff else None
        )
        jsonrpc.add_slice(self.sock, sid, ns_list, ns_diff if ns_diff else None)


    def del_slice(self, sid):
        self.logger.debug(
            "worker: remove slice %s from netplumber", sid
        )
        jsonrpc.remove_slice(self.sock, sid)


    def add_tables(self, model, prefixed=False):
        self.model_types.setdefault(model.node, model.type)

        for table in model.tables:
            name = '_'.join([model.node, table])

            if name not in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for port in model.ports:
                    if prefixed and port.startswith("in_") and (
                            table.startswith("pre_routing")
                    ):
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port[3:]]))

                    elif prefixed and port.startswith("out_") and table.startswith("post_routing"):
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port[4:]]))

                    elif prefixed and not port.startswith(table):
                        continue

                    else:
                        portno = calc_port(idx, model, port)
                        portname = normalize_port('.'.join([model.node, port]))

                    ports.append(portno)
                    self.ports[portname] = portno

                self.logger.debug(
                    "worker: add table to netplumber: %s with index %s and ports %s",
                    name, idx, ports
                )
                jsonrpc.add_table(self.sock, idx, ports)


    def add_wiring(self, model):
        # add links between tables
        for port1, port2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if port1 in ["internals_in", "post_routing"] or \
                port2 in ["internals_out", "post_routing"]:
                self.logger.debug("worker: skip wiring %s to %s", port1, port2)
                continue

            self.logger.debug("worker: wire %s to %s", port1, port2)

            gport1 = self.global_port('_'.join([model.node, port1]))

            if gport1 not in self.links:
                gport2 = self.global_port('_'.join([model.node, port2]))

                self.logger.debug(
                    "worker: add link to netplumber from %s to %s", hex(gport1), hex(gport2)
                )
                jsonrpc.add_link(self.sock, gport1, gport2)

                self.links[gport1] = gport2


    def _add_pre_routing_rules(self, model):
        table = 'pre_routing'

        if table not in model.tables:
            return

        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        for rule in model.tables[table]:
            if not isinstance(rule, SwitchRule):
                rule = SwitchRule.from_json(rule)
            rid = rule.idx

            rvec = self._build_vector(rule.match)

            in_ports = [self.global_port(p) for p in rule.in_ports]

            out_ports = []
            for act in [a for a in rule.actions if isinstance(a, Forward)]:
                out_ports.extend([self.global_port(p) for p in act.ports])

            rewrite = None
            mask = None
            if "in_port" not in self.mapping:
                self.mapping.extend("in_port")
                rvec.enlarge(FIELD_SIZES["in_port"])

            rewrite = Vector(length=self.mapping.length)
            mask = Vector(length=rewrite.length, preset='0')

            for action in [a for a in rule.actions if isinstance(a, Rewrite)]:
                rewrite = self._build_vector([
                    SwitchRuleField(f.name, '{:032b}'.format(
                        self.global_port(f.value)
                    )) if f.name in [
                        'in_port', 'out_port', 'interface'
                    ] else f for f in action.rewrite
                ])

                mask = self._build_vector([
                    SwitchRuleField(
                        f.name,
                        "1"*FIELD_SIZES[f.name]
                    ) if f.name in [
                        'in_port', 'out_port', 'interface'
                    ] else f for f in action.rewrite],
                    preset='0'
                )

            self.logger.debug(
                "worker: add rule %s to %s:\n\t((%s) %s -> (%s) %s)",
                calc_rule_index(rid),
                self.tables["%s_%s" % (model.node, table)],
                (self.global_port(p) for p in rule.in_ports),
                rvec.vector if rvec else "*",
                rewrite.vector if rewrite else "*",
                out_ports
            )
            r_id = jsonrpc.add_rule(
                self.sock,
                self.tables["%s_%s" % (model.node, table)],
                calc_rule_index(rid),
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector,
                rewrite.vector
            )
            np_rid = calc_rule_index(rid, t_idx=tid)
            self.rule_ids.setdefault(np_rid, [])
            self.rule_ids[np_rid].append(r_id)


    def _add_post_routing_rules(self, model):
        table = 'post_routing'

        if table not in model.tables:
            return

        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        for rule in model.tables[table]:
            if not isinstance(rule, SwitchRule):
                rule = SwitchRule.from_json(rule)
            rid = rule.idx

            rvec = self._build_vector([
                SwitchRuleField(f.name, '{:032b}'.format(
                        self.global_port(f.value)
                    )) if f.name in [
                        'in_port', 'out_port', 'interface'
                    ] else f for f in rule.match
            ])

            rewrite = self._build_vector([])

            mask = self._build_vector([
                SwitchRuleField(
                    p, '1'*FIELD_SIZES[p]
                ) for p in ['in_port', 'out_port'] if p in self.mapping],
                preset='0'
            )

            in_ports = [
                self.global_port("%s_%s" % (tname, p)) for p in rule.in_ports
            ]

            out_ports = []
            for act in [a for a in rule.actions if isinstance(a, Forward)]:

                out_ports.extend([self.global_port(p) for p in act.ports])
                # XXX: ugly workaround
                if model.type == 'router':
                    for port in act.ports:
                        set_field_in_vector(
                            self.mapping,
                            rvec,
                            "out_port",
                            "{:032b}".format(self.global_port(port))
                        )

            self.logger.debug(
                "worker: add rule %s to %s:\n\t(%s -> %s)",
                calc_rule_index(rid), tid, rvec.vector if rvec else "*", out_ports
            )
            r_id = jsonrpc.add_rule(
                self.sock,
                tid,
                calc_rule_index(rid),
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector if mask else None,
                rewrite.vector if rewrite else None
            )
            np_rid = calc_rule_index(rid, t_idx=tid)
            self.rule_ids.setdefault(np_rid, [])
            self.rule_ids[np_rid].append(r_id)


    def _add_rule_table(self, model, table):
        tname = '_'.join([model.node, table])
        tid = self.tables[tname]

        self.logger.debug("worker: add rules to %s", tname)

        for rule in model.tables[table]:
            rid = rule.idx
            act = rule.actions

            for field in [f for f in rule.match if f.name in ['in_port', 'out_port', 'interface']]:
                if not Vector.is_vector(field.value, name=field.name):
                    field.value = "{:032b}".format(self.global_port("%s_%s" % (model.node, field.value)))
                    field.vectorize()

            for action in [a for a in act if isinstance(a, Rewrite)]:
                for field in action.rewrite:
                    if field.name in ['in_port', 'out_port', 'interface'] and not Vector.is_vector(field.value, name=field.name):
                        field.value = "{:032b}".format(self.global_port(field.value))

                    field.vectorize()

            rvec = self._build_vector(rule.match)

            in_ports = [
                self.global_port(
                    "%s_%s" % (tname, pname)
                ) for pname in rule.in_ports
            ]

            out_ports = []
            mask = None
            rewrite = None
            for action in rule.actions:
                if isinstance(action, Forward):
                    out_ports.extend(
                        [self.global_port(
                            '%s_%s' %(tname, port.lower())
                        ) for port in action.ports]
                    )

                #XXX: remove?
                elif isinstance(action, Miss):
                    out_ports.append(
                        self.global_port('%s_miss' % tname)
                    )

                elif isinstance(action, Rewrite):
                    if not rewrite:
                        rewrite = self._build_vector(action.rewrite)
                    if not mask:
                        mask = self._build_vector([
                            SwitchRuleField(
                                f.name, '1'*FIELD_SIZES[f.name]
                            ) for f in action.rewrite],
                            preset='0'
                        )

                else:
                    self.logger.warn(
                        "worker: ignore unknown action while adding rule\n%s",
                        json.dumps(action.to_json(), indent=2)
                    )

            matches = self._expand_negations(rule.match)

            for nid, match in enumerate(matches):
                self.logger.debug(
                    "worker: add rule %s to %s:\n\t(%s, %s -> %s)",
                    calc_rule_index(rid), tid, in_ports, match.vector if match else "*", out_ports
                )

                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    calc_rule_index(rid, n_idx=nid),
                    in_ports,
                    out_ports,
                    match.vector if match.vector else 'x'*8,
                    mask.vector if mask else None,
                    rewrite.vector if rewrite else None
                )
                np_rid = calc_rule_index(rid, t_idx=tid, n_idx=nid)
                self.rule_ids.setdefault(np_rid, [])
                self.rule_ids[np_rid].append(r_id)


    def add_rules(self, model):
        for table in model.tables:
            # XXX: ugly as f*ck... eliminate INPUT/OUTPUT and make PREROUTING static???
            if table in [
                    "pre_routing",
                    "post_routing"
            ]:
                self.logger.debug("worker: skip adding rules to table %s", table)
                continue

            self._add_rule_table(model, table)

        for table in ["post_routing"]:
            self._add_post_routing_rules(model)

        for table in ["pre_routing"]:
            self._add_pre_routing_rules(model)


    # XXX: merge with pre- post-routing handling above?
    def add_switch_rules(self, model):
        for table in model.tables:

            tname = '_'.join([model.node, table])
            tid = self.tables[tname]

            for rule in model.tables[table]:
                rid = rule.idx

                rvec = self._build_vector(rule.match)

                out_ports = []
                mask = None
                rewrite = None
                for action in rule.actions:
                    if isinstance(action, Forward):
                        out_ports.extend(
                            [self.global_port(port) for port in action.ports]
                        )

                    elif isinstance(action, Rewrite):
                        rewrite = self._build_vector([
                            SwitchRuleField(
                                f.name, '{:032b}'.format(self.global_port(field.value))
                            ) if f.name in [
                                'interface', 'in_port', 'out_port'
                            ] else f for f in action.rewrite
                        ])
                        mask = self._build_vector([
                            SwitchRuleField(
                                f.name, '1'*FIELD_SIZES[f.name]
                            ) for f in action.rewrite if f.name in [
                                'interface', 'in_port', 'out_port'
                            ]
                        ])

                self.logger.debug(
                    "worker: add rule %s to %s:\n\t(%s & %s -> %s, %s)",
                    calc_rule_index(rid),
                    tid,
                    rvec.vector if rvec else "*",
                    mask.vector if mask else "*",
                    out_ports,
                    rewrite.vector if rewrite else "*"
                )

                in_ports = []
                if rule.in_ports:
                    in_ports = [self.global_port(
                        "%s_%s" % (model.node, p)
                    ) for p in rule.in_ports]

                r_id = jsonrpc.add_rule(
                    self.sock,
                    tid,
                    calc_rule_index(rid),
                    in_ports,
                    out_ports,
                    rvec.vector,
                    mask.vector if mask else None,
                    rewrite.vector if rewrite else None
                )
                np_rid = calc_rule_index(rid, t_idx=tid)
                self.rule_ids.setdefault(np_rid, [])
                self.rule_ids[np_rid].append(r_id)


    def delete_rules(self, model):
        for table in model.tables:
            tid = self.tables['_'.join([model.node, table])]

            only_rid = lambda x: x[0]
            for rid in [only_rid(x) for x in model.tables[table]]:
                for r_id in self.rule_ids[calc_rule_index(rid, t_idx=tid)]:
                    self.logger.debug(
                        "worker: remove rule %s from netplumber", r_id
                    )
                    jsonrpc.remove_rule(self.sock, r_id)
                del self.rule_ids[calc_rule_index(rid, t_idx=tid)]


    def delete_wiring(self, model):
        prefix = lambda x: '.'.join(x.split('.')[:len(x.split('.'))-1])

        for port1, port2 in model.wiring:
            node1 = prefix(port1)
            node2 = prefix(port2)

            idx1 = self.tables[node1]
            idx2 = self.tables[node2]

            self.logger.debug(
                "worker: remove link from %s to %s from netplumber", calc_port(idx1, model, port1), calc_port(idx2, model, port2)
            )
            jsonrpc.remove_link(
                self.sock,
                calc_port(idx1, model, port1),
                calc_port(idx2, model, port2)
            )


    def delete_tables(self, model):
        for table in model.tables:
            name = '_'.join([model.node, table])

            if not self.models[model.node].tables[table]:
                self.logger.debug(
                    "worker: remove table %s with id %s from netplumber", name, self.tables[name]
                )
                jsonrpc.remove_table(self.sock, self.tables[name])
                del self.tables[name]


    def _prepare_generator(self, model):
        name = model.node
        if name in self.generators:
            self._delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        outgoing = self._build_headerspace(model.fields)

        return (name, idx, portno, outgoing)


    def add_generator(self, model):
        name, idx, portno, outgoing = self._prepare_generator(model)

        self.logger.debug(
            "worker: add source %s and port %s to netplumber with list %s and diff %s",
            name,
            portno,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff]
        )
        sid = jsonrpc.add_source(
            self.sock,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )

        self.generators[name] = (idx, sid, model)


    def add_generators_bulk(self, models):
        generators = [self._prepare_generator(m) for m in models]

        for name, idx, portno, outgoing in generators:
            self.logger.debug(
                "worker: add source %s and port %s to netplumber with list %s and diff %s",
                name,
                portno,
                [v.vector for v in outgoing.hs_list],
                [v.vector for v in outgoing.hs_diff]
            )

        sids = jsonrpc.add_sources_bulk(
            self.sock,
            [
                (
                    [v.vector for v in outgoing.hs_list],
                    [v.vector for v in outgoing.hs_diff],
                    [portno]
                ) for _name, _idx, portno, outgoing in generators
            ]
        )

        for name, model, sid in zip([n for n, _i, _p, _o in generators], models, sids):
            self.generators[name] = (idx, sid, model)


    def delete_generator(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self.global_port(node+'.1')
        port2 = self.links[port1]
        self.logger.debug(
            "worker: remove link from %s to %s from netplumber", port1, port2
        )
        jsonrpc.remove_link(self.sock, port1, port2)
        self.logger.debug(
            "worker: remove link from %s to %s from netplumber", port2, port1
        )
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        self.logger.debug(
            "worker: remove source %s with id %s from netplumber", node, sid
        )
        jsonrpc.remove_source(self.sock, sid)

        del self.tables[node]


    def _get_model_table(self, node):
        mtype = self.model_types[node]
        return self.tables[
            node+'_post_routing' if mtype == 'packet_filter' else node+'.1'
        ]


    def _build_headerspace(self, fields):
        keys = sorted(fields.keys())
        combinations = itertools.product(*(fields[k] for k in keys))

        hs_list=[
            self._build_vector(c) for c in combinations
        ]

        return HeaderSpace(self.mapping.length, hs_list=hs_list)


    def add_probe(self, model):
        name = model.node
        if name in self.probes:
            self._delete_probe(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = normalize_port(name + '.1')
        portno = calc_port(idx, model, port)

        self.ports[port] = portno

        filter_fields = self._build_headerspace(model.filter_fields)
        test_fields = self._build_headerspace(model.test_fields)


        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
#        filter_expr = {"type" : "header", "header" : filter_hs}
        filter_expr = None

        test_path = []
        for pathlet in model.test_path.to_json()['pathlets']:
            ptype = pathlet['type']

            if ptype not in ['start', 'end', 'skip', 'skip_next']:
                key, val = {
                    'port' : ('port', lambda pl: self.global_port(pl['port'])),
                    'next_ports' : (
                        'ports',
                        lambda pl: [self.global_port(p) for p in pl['ports']]
                    ),
                    'last_ports' : (
                        'ports',
                        lambda pl: [self.global_port(p) for p in pl['ports']]
                    ),
                    'table' : ('table', lambda pl: self._get_model_table(pl['table'])),
                    'next_tables' : (
                        'tables',
                        lambda pl: [self._get_model_table(t) for t in pl['tables']]
                    ),
                    'last_tables' : (
                        'tables',
                        lambda pl: [self._get_model_table(t) for t in pl['tables']]
                    )
                }[ptype]
                pathlet[key] = val(pathlet)

            test_path.append(pathlet)


        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
        if test_fields and test_path:
            test_expr = {
#                "type": "and",
#                "arg1" : {
#                    "type" : "header",
#                    "header" : test_hs
#                },
#                "arg2" : {
                    "type" : "path",
                    "pathlets" : test_path
#                }
            }

        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
        elif test_fields:
            test_expr = {
                "type" : "true"
#                "type" : "header",
#                "header" : test_hs
            }

        elif test_path:
            test_expr = {
                "type" : "path",
                "pathlets" : test_path
            }

        else:
            eprint("Error while add probe: no test fields or path. Aborting.")
            return

        self.logger.debug(
            "worker: add probe %s and port %s", name, portno
        )
        pid = jsonrpc.add_source_probe(
            self.sock,
            [portno],
            model.quantor,
            filter_expr,
            test_expr
        )
        self.probes[name] = (idx, pid, model)


    def delete_probe(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.probes[node])

        # delete links
        port1 = self.global_port(node+'.1')
        port2 = self.links[port1]
        self.logger.debug(
            "worker: remove link from %s to %s from netplumber", port1, port2
        )
        jsonrpc.remove_link(self.sock, port1, port2)
        self.logger.debug(
            "worker: remove link from %s to %s from netplumber", port2, port1
        )
        jsonrpc.remove_link(self.sock, port2, port1)

        del self.links[port1]
        del self.links[port2]

        # delete source and probe
        self.logger.debug(
            "worker: remove probe %s from netplumber", sid
        )
        jsonrpc.remove_source_probe(self.sock, sid)

        del self.tables[node]


    def global_port(self, port):
        return self.ports[normalize_port(port)]

