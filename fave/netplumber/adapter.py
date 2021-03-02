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

from ip6np.ip6np_util import field_value_to_bitvector

from openflow.rule import SwitchRule, Match, Forward, Miss, Rewrite, SwitchRuleField


class NetPlumberAdapter(object):

    def __init__(self, socks, logger):
        self.socks = socks
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
        jsonrpc.stop(self.socks)

    def dump_flows(self, odir):
        jsonrpc.dump_flows(self.socks, odir)

    def dump_plumbing_network(self, odir):
        jsonrpc.dump_plumbing_network(self.socks, odir)

    def dump_pipes(self, odir):
        jsonrpc.dump_pipes(self.socks, odir)

    def dump_flow_trees(self, odir, keep_simple=False):
        jsonrpc.dump_flow_trees(self.socks, odir, keep_simple)

    def expand(self):
        self.logger.debug(
            "worker: expand vector length to %s", self.mapping.length
        )
        jsonrpc.expand(self.socks, self.mapping.length)

    def _get_index_for_src(self, src):
        return self.generators.get(src.rstrip('.1'), [-1, 0, 0])[0]

    def add_links_bulk(self, links):
         jsonrpc.add_links_bulk(
            self.socks,
            [(
                self._get_index_for_src(src),
                self.global_port(src),
                self.global_port(dst)
            ) for src, dst in links]
         )

    def add_link(self, src, dst):
        jsonrpc.add_link(self.socks, self.global_port(src), self.global_port(dst))


    def remove_link(self, sport, dport):
        jsonrpc.remove_link(self.net_plumber.sock, sport, dport)
        self.links[sport].remove(dport)
        if not self.links[sport]: del self.links[sport]


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
        jsonrpc.add_slice(self.socks, sid, ns_list, ns_diff if ns_diff else None)


    def del_slice(self, sid):
        self.logger.debug(
            "worker: remove slice %s from netplumber", sid
        )
        jsonrpc.remove_slice(self.socks, sid)


    def add_tables(self, model, prefixed=False):
        self.model_types.setdefault(model.node, model.type)

        for table in model.tables:
            name = table

            if name not in self.tables:
                idx = self.fresh_table_index
                self.tables[name] = idx
                self.fresh_table_index += 1

                ports = []
                for port in [port for port in model.ports if model.ports[port] == table]:
                    portno = calc_port(idx, model, port)

                    ports.append(portno)
                    self.ports[port] = portno

                self.logger.debug(
                    "worker: add table to netplumber: %s with index %s and ports %s",
                    name, idx, [hex(p) for p in ports]
                )
                jsonrpc.add_table(self.socks, idx, ports)


    def add_wiring(self, model):
        # add links between tables
        for port1, port2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if port1 in [model.node+".internals_in", model.node+".post_routing"] or \
                port2 in [model.node+".internals_out", model.node+".post_routing"]:
                self.logger.debug("worker: skip wiring %s to %s", port1, port2)
                continue

            self.logger.debug("worker: wire %s to %s", port1, port2)

            gport1 = self.global_port(port1)
            gport2 = self.global_port(port2)

            self.logger.debug(
                "worker: add link to netplumber from %s:%s to %s:%s",
                port1, hex(gport1), port2, hex(gport2)
            )
            jsonrpc.add_link(self.socks, gport1, gport2)

            self.links.setdefault(gport1, [])
            self.links[gport1].append(gport2)


    def _add_pre_routing_rules(self, model):
        table = model.node+'.pre_routing'

        if table not in model.tables:
            return

        tid = self.tables[table]

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
                "worker: add rule %s to %s:%s:\n\t((%s) %s -> (%s) %s)",
                calc_rule_index(rid),
                table,
                self.tables[table],
                [hex(self.global_port(p)) for p in rule.in_ports],
                rvec.vector if rvec else "*",
                rewrite.vector if rewrite else "*",
                [hex(p) for p in out_ports]
            )
            r_id = jsonrpc.add_rule(
                self.socks,
                self.tables[table],
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
        table = model.node+'.post_routing'

        if table not in model.tables:
            return

        tid = self.tables[table]

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
                self.global_port(p) for p in rule.in_ports
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
                "worker: add rule %s to %s:%s:\n\t(%s -> %s)",
                calc_rule_index(rid), table, tid, rvec.vector if rvec else "*", [hex(p) for p in out_ports]
            )
            r_id = jsonrpc.add_rule(
                self.socks,
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
        tid = self.tables[table]

        self.logger.debug("worker: add rules to %s", table)

        for rule in model.tables[table]:
            self.logger.debug("worker: %s -> %s", [f.to_json() for f in rule.match], [a.to_json() for a in rule.actions])

            rid = rule.idx
            act = rule.actions

            for field in [
                f for f in rule.match if f.name in [
                    'in_port', 'out_port', 'interface'
                ]
            ]:
                if not Vector.is_vector(field.value, name=field.name):
                    field.value = "{:032b}".format(self.global_port(field.value))
                    field.vectorize()

            for action in [a for a in act if isinstance(a, Rewrite)]:
                for field in action.rewrite:
                    if field.name in [
                        'in_port', 'out_port', 'interface'
                    ] and not Vector.is_vector(field.value, name=field.name):
                        field.value = "{:032b}".format(self.global_port(field.value))

                    field.vectorize()

            rvec = self._build_vector(rule.match)

            in_ports = [
                self.global_port(
                    pname
                ) for pname in rule.in_ports
            ]

            out_ports = []
            mask = None
            rewrite = None
            for action in rule.actions:
                if isinstance(action, Forward):
                    out_ports.extend(
                        [self.global_port(
                            port
                        ) for port in action.ports]
                    )

                elif isinstance(action, Rewrite):
                    rewrite = self._build_vector(action.rewrite)
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
                    "worker: add rule %s to %s:\n\t(%s, %s & %s -> %s, %s)",
                    calc_rule_index(rid),
                    tid,
                    [hex(p) for p in in_ports],
                    match.vector if match else "*",
                    mask.vector if mask else "*",
                    [hex(p) for p in out_ports],
                    rewrite.vector if rewrite else "*"
                )

                r_id = jsonrpc.add_rule(
                    self.socks,
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
                model.node+".pre_routing",
                model.node+".post_routing"
            ]:
                self.logger.debug("worker: skip adding rules to table %s", table)
                continue

            self._add_rule_table(model, table)

        for table in [model.node+".post_routing"]:
            self._add_post_routing_rules(model)

        for table in [model.node+".pre_routing"]:
            self._add_pre_routing_rules(model)


    # XXX: merge with pre- post-routing handling above?
    def add_switch_rules(self, model):
        for table in model.tables:

            tid = self.tables[table]

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
                                f.name, '{:032b}'.format(self.global_port(f.value))
                            ) if f.name in [
                                'interface', 'in_port', 'out_port'
                            ] else f for f in action.rewrite
                        ])
                        mask = self._build_vector([
                            SwitchRuleField(
                                f.name, '1'*FIELD_SIZES[f.name]
                            ) for f in action.rewrite
                        ], preset='0')

                self.logger.debug(
                    "worker: add rule %s to %s:%s:\n\t(%s & %s -> %s, %s)",
                    calc_rule_index(rid),
                    table,
                    tid,
                    rvec.vector if rvec else "*",
                    mask.vector if mask else "*",
                    [hex(p) for p in out_ports],
                    rewrite.vector if rewrite else "*"
                )

                in_ports = [self.global_port(
                    "%s.%s" % (model.node, p)
                ) for p in rule.in_ports] if rule.in_ports else []

                r_id = jsonrpc.add_rule(
                    self.socks,
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
            tid = table

            only_rid = lambda x: x[0]
            for rid in [only_rid(x) for x in model.tables[table]]:
                for r_id in self.rule_ids[calc_rule_index(rid, t_idx=tid)]:
                    self.logger.debug(
                        "worker: remove rule %s from netplumber", r_id
                    )
                    jsonrpc.remove_rule(self.socks, r_id)
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
                self.socks,
                calc_port(idx1, model, port1),
                calc_port(idx2, model, port2)
            )


    def delete_tables(self, model):
        for table in model.tables:
            name = table

            if not self.models[model.node].tables[table]:
                self.logger.debug(
                    "worker: remove table %s with id %s from netplumber", name, self.tables[name]
                )
                jsonrpc.remove_table(self.socks, self.tables[name])
                del self.tables[name]


    def _prepare_generator(self, model):
        name = model.node
        if name in self.generators:
            self._delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = name+'.1'
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
            self.socks,
            idx,
            [v.vector for v in outgoing.hs_list],
            [v.vector for v in outgoing.hs_diff],
            [portno]
        )

        self.generators[name] = (idx, sid, model)


    def add_generators_bulk(self, models):
        for model in models:
            self._update_mapping(set([f for f in model.fields.iterkeys()]))

        generators = [self._prepare_generator(m) for m in models]
        idx_to_model = {}
        for generator, model in zip(generators, models):
            _n, idx, _p, _o = generator
            idx_to_model[idx] = model

        for name, idx, portno, outgoing in generators:
            self.logger.debug(
                "worker: add source %s and port %s to netplumber with list %s and diff %s",
                name,
                portno,
                [v.vector for v in outgoing.hs_list],
                [v.vector for v in outgoing.hs_diff]
            )

        sids = jsonrpc.add_sources_bulk(
            self.socks,
            [
                (
                    idx,
                    [v.vector for v in outgoing.hs_list],
                    [v.vector for v in outgoing.hs_diff],
                    [portno]
                ) for _name, idx, portno, outgoing in generators
            ]
        )

        for name, idx, _portno, _outgoing in generators:
            self.generators[name] = (idx, sids[idx], idx_to_model[idx])


    def delete_generator(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self.global_port(node+'.1')
        ports = self.links[port1]
        for port2 in ports:
            self.logger.debug(
                "worker: remove link from %s to %s from netplumber", port1, port2
            )
            jsonrpc.remove_link(self.socks, port1, port2)

            self.links[port1].remove(port2)

        if not self.links[port1]: del self.links[port1]


        # delete source and probe
        self.logger.debug(
            "worker: remove source %s with id %s from netplumber", node, sid
        )
        jsonrpc.remove_source(self.socks, sid)

        del self.tables[node]


    def _get_model_table(self, node):
        mtype = self.model_types[node]
        return self.tables[
            node+'.post_routing' if mtype == 'packet_filter' else node+'.1'
        ]


    def _build_headerspace(self, fields):
        keys = sorted(fields.keys())
        combinations = itertools.product(*(fields[k] for k in keys))

        hs_list=[
            self._build_vector([
                SwitchRuleField(
                    f.name, '{:032b}'.format(self.global_port(f.value))
                ) if f.name in [
                    'interface', 'in_port', 'out_port'
                ] else f for f in c
            ]) for c in combinations
        ]

        return HeaderSpace(self.mapping.length, hs_list=hs_list)


    def add_probe(self, model):
        name = model.node
        if name in self.probes:
            self._delete_probe(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = name + '.1'
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
            self.socks,
            [portno],
            model.quantor,
            self._build_vector([
                SwitchRuleField(
                    f.name, '{:032b}'.format(self.global_port(f.value))
                ) if f.name in [
                    'interface', 'in_port', 'out_port'
                ] else f for f in  model.match]
            ).vector,
            filter_expr,
            test_expr,
            idx
        )
        self.probes[name] = (idx, pid, model)


    def delete_probe(self, node):
        only_sid = lambda x: x[1]
        sid = only_sid(self.probes[node])

        # find links towards probe
        port2 = self.global_port(node+'.1')
        sports = [sport for sport in self.links if port1 in self.ports[sport]]

        for port1 in sports:
            self.logger.debug(
                "worker: remove link from %s to %s from netplumber", port1, port2
            )
            jsonrpc.remove_link(self.socks, port1, port2)

            self.links[port1].remove(port2)
            if not self.links[port1]: del self.links[port1]

        # delete source and probe
        self.logger.debug(
            "worker: remove probe %s from netplumber", sid
        )
        jsonrpc.remove_source_probe(self.socks, sid)

        del self.tables[node]


    def global_port(self, port):
        try:
            return self.ports[port]
        except KeyError:
            import pprint
            pprint.pprint(self.ports, indent=2)
            raise
