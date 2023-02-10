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

""" This module implements an adapter from FaVe to NetPlumber.
"""

import itertools
import logging
import json
import sys

from copy import deepcopy

from aggregator.aggregator_abstract import TRACE
from aggregator.abstract_engine import AbstractVerificationEngine

import netplumber.jsonrpc as jsonrpc
from netplumber.mapping import Mapping, FIELD_SIZES
from netplumber.vector import set_field_in_vector
from netplumber.vector import Vector, HeaderSpace

from util.ip6np_util import field_value_to_bitvector
from rule.rule_model import Rule, Match, Forward, Rewrite, RuleField


def _calc_port(tab, model, port):
    """ Calculates a port number for a table.

    Keyword arguments:
    tab -- a table id
    model -- the model inheriting the table
    port -- the port index in the table
    """
    try:
        return (tab<<16)+model.port_index(port)
    except KeyError:
        return (tab<<16)+1

_TABLE_IDX_MAX = 2**32-1
_RULE_IDX_MAX = 2**24-1
_NEG_IDX_MAX = 2**12-1

def _calc_rule_index(r_idx, t_idx=0, n_idx=0):
    """ Calculates the rule index within a table

    Keyword arguments:
    t_idx -- a table index
    r_idx -- a rule index within the table
    n_idx -- an optional index for negation expanded rules
    """

    assert t_idx <= _TABLE_IDX_MAX
    assert r_idx <= _RULE_IDX_MAX
    assert n_idx <= _NEG_IDX_MAX

    return (t_idx<<32)+(r_idx<<12)+n_idx


def _expand_field(field):
    """ Expands a negated field to a set of vectors.

    Keyword argument:
    field -- a negated field to be expanded
    """

    assert isinstance(field, RuleField)

    vec = field_value_to_bitvector(field)
    nvectors = []
    for idx, bit in enumerate(vec.vector):
        if bit == '0':
            nvec = deepcopy(vec)
            nvec.vector = "x"*idx + "1" + "x"*(nvec.length-idx-1)
            nvectors.append(nvec)
        elif bit == '1':
            nvec = deepcopy(vec)
            nvec.vector = "x"*idx + "0" + "x"*(nvec.length-idx-1)
            nvectors.append(nvec)
        else: # 'x'
            continue

    return nvectors



class NetPlumberAdapter(AbstractVerificationEngine):
    """ Class that maps and translates a FaVe model to a NetPlumber model.
    """

    def __init__(self, socks, logger, asyncore_socks=None, mapping=None):
        self.socks = socks
        self.asyncore_socks = asyncore_socks if asyncore_socks else {}
        self.mapping = Mapping.from_json(mapping) if mapping else Mapping(0)
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
        """ Stops NetPlumber.
        """
        jsonrpc.stop(self.socks)

    def dump_flows(self, odir):
        """ Dumps flows.

        Arguments:
        odir -- the target directory
        """
        jsonrpc.dump_flows(self.socks, odir)

    def dump_plumbing_network(self, odir):
        """ Dumps plumbing network.

        Arguments:
        odir -- the target directory
        """
        jsonrpc.dump_plumbing_network(self.socks, odir)

    def dump_pipes(self, odir):
        """ Dumps pipes.

        Arguments:
        odir -- the target directory
        """
        jsonrpc.dump_pipes(self.socks, odir)

    def dump_flow_trees(self, odir, keep_simple=False):
        """ Dumps flow trees.

        Arguments:
        odir -- the target directory
        """
        jsonrpc.dump_flow_trees(self.socks, odir, keep_simple)

    def check_anomalies(self, use_shadow=False, use_reach=False, use_general=False):
        """ Orders NetPlumber to check all tables for anomalies.
        """
        jsonrpc.check_anomalies(
            self.socks,
            use_shadow=use_shadow,
            use_reach=use_reach,
            use_general=use_general
        )

    def _expand(self):
        self.logger.debug(
            "worker: expand vector length to %s", self.mapping.length
        )
        jsonrpc.expand(self.socks, self.mapping.length)

    def _get_index_for_src(self, src):
        return self.generators.get(src.rstrip('1').rstrip('.'), [-1, 0, 0])[0]

    def add_links_bulk(self, links, use_dynamic=False):
        """ Add a bulk of links.

        Arguments:
        links -- a list of link tuples

        Keyword arguments:
        use_dynamic -- use a dynamic instead of a round robin distribution (default: False)
        """

        jsonrpc.add_links_bulk(
            self.socks,
            [(
                self._get_index_for_src(src),
                self.global_port(src),
                self.global_port(dst)
            ) for src, dst in links],
            use_dynamic=use_dynamic
        )

    def add_link(self, sport, dport):
        """ Add a link.

        Arguments:
        sport -- the source port
        dport -- the destination port
        """
        jsonrpc.add_link(self.socks, self.global_port(sport), self.global_port(dport))


    def remove_link(self, sport, dport):
        """ Remove a link.

        Arguments:
        sport -- the source port
        dport -- the destination port
        """
        jsonrpc.remove_link(self.socks, sport, dport)
        self.links[sport].remove(dport)
        if not self.links[sport]: del self.links[sport]


    def _expand_negations(self, match):
        """ Expands a match with negated fields to a set of vectors.

        Keyword arguments:
        match -- a match to be expanded
        """

        assert isinstance(match, Match)
        fields = set([f.name for f in match])
        self._update_mapping(fields)

        field_vectors = {}
        for field in match:
            if field.negated:
                field_vectors[field.name] = _expand_field(field)
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
            self._expand()


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
        """ Add a network slice.

        Arguments:
        slicem -- a network slice model
        """

        sid = slicem.sid

        ns_list = [self._build_vector(ns) for ns in slicem.ns_list]
        ns_diff = [self._build_vector(ns) for ns in slicem.ns_diff]

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "worker: add slice %s to netplumber with list %s and diff %s",
                sid,
                ns_list,
                ns_diff if ns_diff else None
            )

        jsonrpc.add_slice(self.socks, sid, ns_list, ns_diff if ns_diff else None)


    def del_slice(self, sid):
        """ Remove a network slice.

        Arguments:
        sid -- a slice ID
        """

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "worker: remove slice %s from netplumber", sid
            )
        jsonrpc.remove_slice(self.socks, sid)


    def add_tables(self, model):
        """ Add model tables.

        Arguments:
        model -- a device model
        """

        self.model_types.setdefault(model.node, model.type)

        for table in model.tables:
            name = table

            if name not in self.tables:
                if hasattr(model, 'table_ids'):
                    idx = model.table_ids[name.rstrip('.1')]
                    self.fresh_table_index = idx + 1 # XXX: only works if tables appear in order
                else:
                    idx = self.fresh_table_index
                    self.fresh_table_index += 1

                self.tables[name] = idx

                ports = []
                for port in [port for port in model.ports if model.ports[port] == table]:
                    portno = _calc_port(idx, model, port)

                    ports.append(portno)
                    self.ports[port] = portno

                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(
                        "worker: add table to netplumber: %s with index %s and ports %s",
                        name, idx, [hex(p) for p in ports]
                    )
                jsonrpc.add_table(self.socks, idx, ports)


    def add_wiring(self, model):
        """ Add internal model wirings.

        Arguments:
        model -- a device model
        """

        # add links between tables
        for port1, port2 in model.wiring:

            # The internals input and the post routing output are never the
            # source of an internal wire. Respectively, the internals output and
            # the post routing output are never targeted internally.
            if port1 in [model.node+".internals_in", model.node+".post_routing"] or \
                port2 in [model.node+".internals_out", model.node+".post_routing"]:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("worker: skip forbidden wire from %s to %s", port1, port2)
                continue

            gport1 = self.global_port(port1)
            gport2 = self.global_port(port2)

            # ignore existing wiring
            if gport1 in self.links and gport2 in self.links[gport1]:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("worker: skip existing wire from %s to %s", port1, port2)
                continue
            else:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("worker: wire %s to %s", port1, port2)

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: add link to netplumber from %s:%s to %s:%s",
                    port1, hex(gport1), port2, hex(gport2)
                )
            jsonrpc.add_link(self.socks, gport1, gport2)

            self.links.setdefault(gport1, [])
            self.links[gport1].append(gport2)


    def _add_pre_routing_rules(self, model):
        table = model.node+'.pre_routing'
        tid = self.tables[table]

        for rule in model.tables[table]:
            if not isinstance(rule, Rule):
                rule = Rule.from_json(rule)
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
                    RuleField(f.name, '{:032b}'.format(
                        self.global_port(f.value)
                    )) if f.name in [
                        'in_port', 'out_port', 'interface'
                    ] else f for f in action.rewrite
                ])

                mask = self._build_vector(
                    [
                        RuleField(
                            f.name,
                            "1"*FIELD_SIZES[f.name]
                        ) if f.name in [
                            'in_port', 'out_port', 'interface'
                        ] else f for f in action.rewrite
                    ],
                    preset='0'
                )

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: add rule %s to %s:%s:\n\t((%s) %s -> (%s) %s)",
                    _calc_rule_index(rid),
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
                _calc_rule_index(rid),
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector,
                rewrite.vector
            )
            np_rid = _calc_rule_index(rid, t_idx=tid)
            self.rule_ids.setdefault(np_rid, [])
            self.rule_ids[np_rid].append(r_id)


    def _add_post_routing_rules(self, model):
        table = model.node+'.post_routing'
        tid = self.tables[table]

        for rule in model.tables[table]:
            if not isinstance(rule, Rule):
                rule = Rule.from_json(rule)
            rid = rule.idx

            rvec = self._build_vector([
                RuleField(f.name, '{:032b}'.format(
                    self.global_port(f.value)
                )) if f.name in [
                    'in_port', 'out_port', 'interface'
                ] else f for f in rule.match
            ])

            rewrite = self._build_vector([])

            mask = self._build_vector(
                [
                    RuleField(
                        p, '1'*FIELD_SIZES[p]
                    ) for p in ['in_port', 'out_port'] if p in self.mapping
                ],
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

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: add rule %s to %s:%s:\n\t(%s -> %s)",
                    _calc_rule_index(rid),
                    table,
                    tid,
                    rvec.vector if rvec else "*",
                    [hex(p) for p in out_ports]
                )
            r_id = jsonrpc.add_rule(
                self.socks,
                tid,
                _calc_rule_index(rid),
                in_ports,
                out_ports,
                rvec.vector,
                mask.vector if mask else None,
                rewrite.vector if rewrite else None
            )
            np_rid = _calc_rule_index(rid, t_idx=tid)
            self.rule_ids.setdefault(np_rid, [])
            self.rule_ids[np_rid].append(r_id)


    def _prepare_generic_rule(self, rule):
        tid = self.tables[rule.tid]
        rid = rule.idx
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
                    RuleField(
                        f.name, '{:032b}'.format(self.global_port(f.value))
                    ) if f.name in [
                        'interface', 'in_port', 'out_port'
                    ] else f for f in action.rewrite
                ])
                mask = self._build_vector([
                    RuleField(
                        f.name, '1'*FIELD_SIZES[f.name]
                    ) for f in action.rewrite
                ], preset='0')

            else:
                if self.logger.isEnabledFor(logging.WARN):
                    self.logger.warn(
                        "worker: ignore unknown action while preparing rule\n%s",
                        json.dumps(action.to_json(), indent=2)
                    )

        in_ports = [
            self.global_port(
                pname
            ) for pname in rule.in_ports
        ]

        matches = self._expand_negations(Match([
            RuleField(
                f.name, '{:032b}'.format(self.global_port(f.value))
            ) if f.name in [
                'interface', 'in_port', 'out_port'
            ] else f for f in rule.match
        ]))

        res = []
        for nid, match in enumerate(matches):
            np_rid = _calc_rule_index(rid, t_idx=tid, n_idx=nid)
            self.rule_ids.setdefault(np_rid, [])
            res.append((
                np_rid,
                tid,
                _calc_rule_index(rid, n_idx=nid),
                in_ports,
                out_ports,
                match.vector if match else None,
                mask.vector if mask else None,
                rewrite.vector if rewrite else None
            ))

        return res


    def _add_generic_table(self, model, table):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("worker: add %s rules to %s:" % (len(model.tables[table]), table))

        if self.logger.isEnabledFor(logging.DEBUG):
            for rule in model.tables[table]:
                self.logger.debug(
                    "worker: %s -> %s",
                    [f.to_json() for f in rule.match],
                    [a.to_json() for a in rule.actions]
                )

        for rule in model.tables[table]:
            prules = self._prepare_generic_rule(rule)

            for np_rid, tid, fave_rid, in_ports, out_ports, match, mask, rewrite in prules:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(
                        "worker: add rule %s to %s:%s:\n\t(%s, %s & %s -> %s, %s)",
                        fave_rid,
                        table,
                        tid,
                        [hex(p) for p in in_ports],
                        match if match else "*",
                        mask if mask else "*",
                        [hex(p) for p in out_ports],
                        rewrite if rewrite else "*"
                    )
                r_id = jsonrpc.add_rule(
                    self.socks,
                    tid,
                    fave_rid,
                    in_ports,
                    out_ports,
                    match,
                    mask,
                    rewrite
                )
                self.rule_ids[np_rid].append(r_id)


    def add_rules(self, model):
        """ Add model rules.

        Arguments:
        model -- a device model
        """

        if self.logger.isEnabledFor(TRACE):
            tables = "\n".join(
                ["\t%s=%s" % (t, len(r)) for t, r in model.tables.items()]
            )
            self.logger.trace(
                "worker: update rules for model %s with tables:\n%s" % (
                    model.node,
                    tables
                )
            )

        for table in [t for t in model.tables if t not in [
                model.node+".pre_routing", model.node+".post_routing"
        ]]:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: add %s rules to table %s" % (
                        len(model.tables[table]),
                        table
                    )
                )

            self.add_rules_batch(model.tables[table])

        if model.node+".post_routing" in model.tables:
            self._add_post_routing_rules(model)

        if model.node+".pre_routing" in model.tables:
            self._add_pre_routing_rules(model)


    def add_rules_batch(self, rules):
        """ Add a batch of rules.

        rules -- a list of rules
        """

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("worker: add a batch of %s rules" % len(rules))

        fields = set()
        for rule in rules:
            fields.update([f.name for f in rule.match])
            for action in [a for a in rule.actions if isinstance(a, Rewrite)]:
                fields.update(set([f.name for f in action.rewrite]))
        self._update_mapping(fields)

        batch = []
        for rule in rules:
            batch.extend(self._prepare_generic_rule(rule))

        for rule in batch:
            np_rid, tid, fave_rid, in_ports, out_ports, match, mask, rewrite = rule

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: add rule %s to %s:\n\t(%s, %s & %s -> %s, %s)",
                    fave_rid,
                    tid,
                    [hex(p) for p in in_ports],
                    match if match else "*",
                    mask if mask else "*",
                    [hex(p) for p in out_ports],
                    rewrite if rewrite else "*"
                )

        rids = []
        if batch != []:
            rids = jsonrpc.add_rules_batch(self.socks, batch)

        for r_id, rule in zip(rids, batch):
            np_rid, _tid, _fave_rid, _in, _out, _match, _mask, _rewrite = rule
            self.rule_ids[np_rid].append(r_id)


    def delete_rules(self, model):
        """ Deletes all rules from a device model.

        Arguments:
        model -- a device model
        """

        for table in model.tables:
            tid = table

            only_rid = lambda x: x[0]
            for rid in [only_rid(x) for x in model.tables[table]]:
                for r_id in self.rule_ids[_calc_rule_index(rid, t_idx=tid)]:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(
                            "worker: remove rule %s from netplumber", r_id
                        )
                    jsonrpc.remove_rule(self.socks, r_id)
                del self.rule_ids[_calc_rule_index(rid, t_idx=tid)]


    def delete_wiring(self, model):
        """ Remove all internal wiring of a device model.

        Arguments:
        model -- a device model
        """

        prefix = lambda x: '.'.join(x.split('.')[:len(x.split('.'))-1])

        for port1, port2 in model.wiring:
            node1 = prefix(port1)
            node2 = prefix(port2)

            idx1 = self.tables[node1]
            idx2 = self.tables[node2]

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: remove link from %s to %s from netplumber",
                    _calc_port(idx1, model, port1),
                    _calc_port(idx2, model, port2)
                )
            jsonrpc.remove_link(
                self.socks,
                _calc_port(idx1, model, port1),
                _calc_port(idx2, model, port2)
            )


    def delete_tables(self, model):
        """ Deletes all tables of a device model.

        Arguments:
        model -- a device model
        """

        for table in model.tables:

            if not self.tables[table]:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(
                        "worker: remove table %s with id %s from netplumber",
                        table,
                        self.tables[table]
                    )
                jsonrpc.remove_table(self.socks, self.tables[table])
                del self.tables[table]


    def _prepare_generator(self, model):
        name = model.node
        if name in self.generators:
            self.delete_generator(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = name+'.1'
        portno = _calc_port(idx, model, port)

        self.ports[port] = portno

        outgoing = self._build_headerspace(model.fields)

        return (name, idx, portno, outgoing)


    def add_generator(self, model):
        """ Add a generator model.

        Arguments:
        model -- a generator model
        """

        name, idx, portno, outgoing = self._prepare_generator(model)

        if self.logger.isEnabledFor(logging.DEBUG):
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


    def add_generators_bulk(self, models, use_dynamic=False):
        """ Add a bulk of generator models.

        Arguments:
        models -- a bulk of generator models

        Keyword arguments:
        use_dynamic -- use dynamic instead of round robin distribution (default: False)
        """

        for model in models:
            self._update_mapping(set([f for f in model.fields.keys()]))

        generators = [self._prepare_generator(m) for m in models]
        idx_to_model = {}
        for generator, model in zip(generators, models):
            _n, idx, _p, _o = generator
            idx_to_model[idx] = model

        for name, idx, portno, outgoing in generators:
            if self.logger.isEnabledFor(logging.DEBUG):
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
            ],
            use_dynamic=use_dynamic
        )

        for name, idx, _portno, _outgoing in generators:
            self.generators[name] = (idx, sids[idx], idx_to_model[idx])


    def delete_generator(self, node):
        """ Deletes a generator model.

        Arguments:
        node -- the generator's name
        """

        only_sid = lambda x: x[1]
        sid = only_sid(self.generators[node])

        # delete links
        port1 = self.global_port(node+'.1')
        ports = self.links[port1]
        for port2 in ports:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: remove link from %s to %s from netplumber", port1, port2
                )
            jsonrpc.remove_link(self.socks, port1, port2)

            self.links[port1].remove(port2)

        if not self.links[port1]: del self.links[port1]


        # delete source and probe
        if self.logger.isEnabledFor(logging.DEBUG):
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

        hs_list = [
            self._build_vector([
                RuleField(
                    f.name, '{:032b}'.format(self.global_port(f.value))
                ) if f.name in [
                    'interface', 'in_port', 'out_port'
                ] else f for f in c
            ]) for c in combinations
        ]

        return HeaderSpace(self.mapping.length, hs_list=hs_list)


    def add_probe(self, model):
        """ Add a probe model.

        Arguments:
        model -- a probe model
        """

        name = model.node
        if name in self.probes:
            self.delete_probe(name)

        idx = self.fresh_table_index
        self.tables[name] = idx
        self.fresh_table_index += 1

        port = name + '.1'
        portno = _calc_port(idx, model, port)

        self.ports[port] = portno

#        filter_fields = self._build_headerspace(model.filter_fields)
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
                "type" : "path",
                "pathlets" : test_path
            }

        # XXX: deactivate using flow expressions due to possible memory explosion in net_plumber
        elif test_fields:
            test_expr = {
                "type" : "true"
            }

        elif test_path:
            test_expr = {
                "type" : "path",
                "pathlets" : test_path
            }

        else:
            print("Error while add probe: no test fields or path. Aborting.", file=sys.stderr)
            return

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "worker: add probe %s and port %s", name, portno
            )
        pid = jsonrpc.add_source_probe(
            self.socks,
            [portno],
            model.quantor,
            self._build_vector([
                RuleField(
                    f.name, '{:032b}'.format(self.global_port(f.value))
                ) if f.name in [
                    'interface', 'in_port', 'out_port'
                ] else f for f in  model.match
            ]).vector,
            filter_expr,
            test_expr,
            idx
        )
        self.probes[name] = (idx, pid, model)


    def delete_probe(self, node):
        """ Delete a probe model

        Arguments:
        node -- the probe's name
        """

        only_sid = lambda x: x[1]
        sid = only_sid(self.probes[node])

        # find links towards probe
        port2 = self.global_port(node+'.1')
        sports = [sport for sport in self.links if port2 in self.ports[sport]]

        for port1 in sports:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "worker: remove link from %s to %s from netplumber", port1, port2
                )
            jsonrpc.remove_link(self.socks, port1, port2)

            self.links[port1].remove(port2)
            if not self.links[port1]: del self.links[port1]

        # delete source and probe
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "worker: remove probe %s from netplumber", sid
            )
        jsonrpc.remove_source_probe(self.socks, sid)

        del self.tables[node]


    def global_port(self, port):
        """ Get global port ID.

        Arguments:
        port -- a port name
        """
        return self.ports[port]
