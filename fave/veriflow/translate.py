#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" FaVe model -> VeriFlow-FR IR (VERIFLOW_PLAN.md V1).

The engine-neutral half of the VeriFlow-FR adapter: it records what the
aggregator hands an engine and translates it, in BULK mode (FaVe's regime:
load everything, then answer the checks), into an IR of tables, ports, links,
prioritised rules, query sets and probes. Pure Python, so each decision of
VERIFLOW_PLAN.md §7 it implements is unit-tested without the native engine
(test/test_veriflow_translate.py):

  * priority (Q9) -- a first-match table resolves by rule index, the lower
    winning, as NetPlumber's; a table DECLARED longest-prefix-match is ordered
    longest prefix first, ties by index, exactly as
    `NetPlumberAdapter._lpm_ordered_batch` orders it;
  * IN_PORT is a matched field (Q7), and a rule with several ingress ports
    becomes one engine rule per port at the same priority (Q16), the factor
    stamped;
  * a graph node is a FaVe table, and FaVe's wiring and links are its edges
    (Q20);
  * a generator's header space is the product of its per-field value lists,
    each a query set started where its links enter the network (Q21);
  * a probe is a table with one consuming rule, its match (Q8). NetPlumber
    ignores a probe's filter fields and answers compliance from the flows
    arriving at it whatever its test fields say (`NetPlumberAdapter.add_probe`),
    and this does the same; a probe with a PATH is refused in V1;
  * negated check conditions expand into non-negated sets (Q17).

Everything V1 cannot translate faithfully is REFUSED, at translation time, with
the reason -- never approximated: router and packet-filter models (they rewrite
FaVe's in_port/out_port metadata, which is V3), rewrites, table misses and
negated rule fields.
"""

import itertools

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from devices.abstract_device import LPM, lpm_prefix_len
from netplumber.mapping import FIELD_SIZES
from rule.rule_model import Forward, Miss, Rewrite
from util.ip6np_util import field_value_to_bitvector


#: The engine's value for "no ingress port" -- and for a rule, "any".
ANY_PORT = -1

#: Port-typed header fields: their value is a port NAME, encoded as the port's
#: engine id in 32 bits, as NetPlumber encodes its global port number.
_PORT_FIELDS = ("interface", "in_port", "out_port")

#: Model types V1 translates.
_SUPPORTED_MODELS = ("switch",)


class Unsupported(Exception):
    """ Something VeriFlow-FR does not (yet) translate faithfully. """


@dataclass
class IrRule:
    id: int
    table: int
    priority: int
    in_port: int
    match: str
    out_ports: List[int]
    consume: bool = False


@dataclass
class Ir:
    fields: List[Tuple[str, int]]
    tables: Dict[str, int]
    ports: Dict[str, int]
    port_table: Dict[int, int]
    links: List[Tuple[int, int]]
    rules: List[IrRule]
    #: generator -> (starts as (table, arrival port), query sets)
    generators: Dict[str, Tuple[List[Tuple[int, int]], List[str]]]
    #: probe -> its table
    probes: Dict[str, int]
    #: engine rule id -> (node, FaVe table, FaVe rule index, ingress port name)
    origin: Dict[int, Tuple[str, str, int, Optional[str]]]
    stamps: Dict[str, Any] = field(default_factory=dict)

    def offset(self, name: str) -> int:
        """ The bit offset of a field in the layout. """
        off = 0
        for fname, width in self.fields:
            if fname == name:
                return off
            off += width
        raise KeyError(name)

    @property
    def width(self) -> int:
        return sum(w for _n, w in self.fields)


def _intersect(a: str, b: str) -> Optional[str]:
    """ Bitwise intersection of two ternary strings; None when empty. """
    out = []
    for x, y in zip(a, b):
        if x == 'x':
            out.append(y)
        elif y == 'x' or x == y:
            out.append(x)
        else:
            return None
    return ''.join(out)


def expand_negated(base: str, offset: int, bits: str) -> List[str]:
    """ The complement of `bits` (a field at `offset`), within `base`, as a
    union of ternary sets: per fixed bit, the set where that bit differs (Q17,
    the expansion `netplumber/adapter._expand_field` makes). """
    out = []
    for i, bit in enumerate(bits):
        if bit not in '01':
            continue
        flipped = 'x' * (offset + i) + ('1' if bit == '0' else '0') + \
            'x' * (len(base) - offset - i - 1)
        met = _intersect(base, flipped)
        if met is not None:
            out.append(met)
    return out


class Translator:
    """ Records the models an engine is handed; translates them on demand. """

    def __init__(self, invert_lpm: bool = False) -> None:
        # SHORTEST prefix first in declared-LPM tables. Exists for one purpose:
        # to show the LPM guard can fail (test/test_veriflow_airtel.py). Stamped.
        self.invert_lpm = invert_lpm
        # Read and written by the aggregator on the engine it drives.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}
        self._port_ids: Dict[Any, int] = {}
        self._models: List[Any] = []
        self._links: List[Tuple[str, str]] = []
        self._generators: List[Any] = []
        self._probes: List[Any] = []

    # -- recording: the AbstractVerificationEngine calls the aggregator makes --

    def global_port(self, port: Any) -> int:
        """ A stable number per port name, for the aggregator's bookkeeping. """
        return self._port_ids.setdefault(port, len(self._port_ids) + 1)

    def add_tables(self, model: Any) -> None:
        pass

    def add_wiring(self, model: Any) -> None:
        pass

    def add_rules(self, model: Any) -> None:
        # A snapshot, never a reference: the aggregator keeps its first model
        # object per device and later extends it in place with the next
        # command's rules, while handing the engine only the diff
        # (bench/feature_survey.py, where holding a reference double-counted).
        self._models.append(SimpleNamespace(
            node=model.node,
            type=model.type,
            ports=dict(getattr(model, "ports", {}) or {}),
            wiring=list(getattr(model, "wiring", []) or []),
            table_semantics=dict(getattr(model, "table_semantics", {}) or {}),
            tables={t: list(rs) for t, rs in model.tables.items()},
        ))

    def add_link(self, sport: Any, dport: Any) -> None:
        self._links.append((sport, dport))

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        self._links.extend(links)

    def add_generator(self, model: Any) -> None:
        self._generators.append(model)

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        self._generators.extend(models)

    def add_probe(self, model: Any) -> None:
        self._probes.append(model)

    # -- translation ----------------------------------------------------------

    def translate(self, extra_fields: Sequence[str] = ()) -> Ir:
        """ The IR of everything recorded. `extra_fields` names the fields the
        checks' conditions use, which the layout must contain too. """
        for model in self._models:
            if model.type not in _SUPPORTED_MODELS:
                raise Unsupported(
                    "%s model %s: VeriFlow-FR V1 translates switch models only. "
                    "Routers and packet filters rewrite FaVe's in_port/out_port "
                    "metadata, which arrives with V3 (VERIFLOW_PLAN.md §10)."
                    % (model.type, model.node))

        layout = self._layout(extra_fields)
        ir = Ir(fields=layout, tables={}, ports={}, port_table={}, links=[],
                rules=[], generators={}, probes={}, origin={})

        def table(name: str) -> int:
            return ir.tables.setdefault(name, len(ir.tables) + 1)

        def port(name: str, tname: str) -> int:
            if name not in ir.ports:
                ir.ports[name] = len(ir.ports) + 1
                ir.port_table[ir.ports[name]] = table(tname)
            return ir.ports[name]

        for model in self._models:
            for tname in model.tables:
                table(tname)
            for pname, tname in model.ports.items():
                port(pname, tname)
        probe_ports = {}
        for probe in self._probes:
            pname = probe.node + ".1"
            port(pname, probe.node)
            probe_ports[pname] = probe.node
            ir.probes[probe.node] = ir.tables[probe.node]

        # Engine links: wiring inside a device, and links between ports the IR
        # knows. A link leaving a generator is not a link but a start (Q21).
        gen_ports = {g.node + ".1": g.node for g in self._generators}
        starts: Dict[str, List[Tuple[int, int]]] = {g.node: [] for g in self._generators}
        for model in self._models:
            for a, b in model.wiring:
                ir.links.append((ir.ports[a], ir.ports[b]))
        for a, b in self._links:
            if a in gen_ports:
                if b not in ir.ports:
                    raise Unsupported("generator %s is linked to unknown port %s"
                                      % (gen_ports[a], b))
                starts[gen_ports[a]].append((ir.port_table[ir.ports[b]], ir.ports[b]))
            else:
                ir.links.append((ir.ports[a], ir.ports[b]))

        fave_rules = 0
        for model in self._models:
            for tname, rules in model.tables.items():
                fave_rules += len(rules)
                self._translate_table(ir, model, tname, rules)

        for probe in self._probes:
            self._reject_probe_paths(probe)
            match = self._ternary(ir, probe.match)
            if match is None:
                continue  # contradictory match fields: it consumes nothing
            rid = len(ir.rules) + 1
            ir.rules.append(IrRule(rid, ir.tables[probe.node], 0, ANY_PORT,
                                   match, [], True))
            ir.origin[rid] = (probe.node, probe.node, 0, None)

        for gen in self._generators:
            ir.generators[gen.node] = (starts[gen.node], self._header_space(ir, gen))

        ir.stamps = {
            "impl": "reimpl-literature",
            "vf_mode": "bulk",
            "vf_node": "table",
            "vf_ports": "field",
            "vf_fields": "plain",
            "vf_invert_lpm": self.invert_lpm,
            "vf_field_order": [n for n, _w in layout],
            "vf_inport_expansion": (
                round(sum(1 for r in ir.rules if not r.consume) / fave_rules, 3)
                if fave_rules else 1.0),
        }
        return ir

    def _layout(self, extra_fields: Sequence[str]) -> List[Tuple[str, int]]:
        """ Every field anything matches on, in FaVe's canonical field order
        (`FIELD_SIZES`), which is also the trie's dimension order: a stamp. """
        used = set(extra_fields)
        for model in self._models:
            for rules in model.tables.values():
                for rule in rules:
                    used.update(f.name for f in rule.match)
        for gen in self._generators:
            used.update(gen.fields.keys())
        for probe in self._probes:
            used.update(f.name for f in probe.match)
        unknown = used - set(FIELD_SIZES)
        if unknown:
            raise Unsupported("fields without a known width: %s" % sorted(unknown))
        return [(name, FIELD_SIZES[name]) for name in FIELD_SIZES if name in used]

    def _field_bits(self, ir: Ir, fld: Any) -> str:
        if fld.name in _PORT_FIELDS:
            if fld.value not in ir.ports:
                raise Unsupported("%s names unknown port %s" % (fld.name, fld.value))
            return '{:032b}'.format(ir.ports[fld.value])
        return field_value_to_bitvector(fld).vector

    def _ternary(self, ir: Ir, fields: Any) -> Optional[str]:
        """ A match as a ternary string over the layout; None if its fields
        contradict each other (it matches nothing). """
        bits = 'x' * ir.width
        for fld in fields:
            if fld.negated:
                raise Unsupported(
                    "negated rule field %s: VeriFlow-FR V1 does not translate "
                    "negations in rules (none occurs in the suite, "
                    "VERIFLOW_PLAN.md §9)" % fld.name)
            off = ir.offset(fld.name)
            piece = 'x' * off + self._field_bits(ir, fld) + \
                'x' * (ir.width - off - FIELD_SIZES[fld.name])
            met = _intersect(bits, piece)
            if met is None:
                return None
            bits = met
        return bits

    def _translate_table(self, ir: Ir, model: Any, tname: str, rules: List[Any]) -> None:
        tid = ir.tables[tname]
        if model.table_semantics.get(tname) == LPM:
            # NetPlumberAdapter._lpm_ordered_batch: longest prefix first, ties
            # by the index the model gave the rule.
            sign = 1 if self.invert_lpm else -1
            order = sorted(rules, key=lambda r: (sign * lpm_prefix_len(r), r.idx))
            prio = {id(r): -(pos + 1) for pos, r in enumerate(order)}
        else:
            prio = {id(r): -r.idx for r in rules}
        seen = set()
        for rule in rules:
            if rule.idx in seen:
                raise Unsupported("%s holds two rules with index %s" % (tname, rule.idx))
            seen.add(rule.idx)
            out: List[int] = []
            for action in rule.actions:
                if isinstance(action, Forward):
                    out.extend(ir.ports[p] for p in action.ports)
                elif isinstance(action, Rewrite):
                    raise Unsupported(
                        "rewrite in %s rule %s: rewrites arrive with V3 "
                        "(VERIFLOW_PLAN.md §10)" % (tname, rule.idx))
                elif isinstance(action, Miss):
                    raise Unsupported("table miss in %s rule %s" % (tname, rule.idx))
                else:
                    raise Unsupported("unknown action %s in %s" % (action, tname))
            match = self._ternary(ir, rule.match)
            if match is None:
                continue  # contradictory fields: the rule matches nothing
            for in_port in (rule.in_ports or [None]):
                rid = len(ir.rules) + 1
                ir.rules.append(IrRule(
                    rid, tid, prio[id(rule)],
                    ANY_PORT if in_port is None else ir.ports[in_port],
                    match, out))
                ir.origin[rid] = (model.node, tname, rule.idx, in_port)

    def _header_space(self, ir: Ir, gen: Any) -> List[str]:
        """ The product of the generator's per-field value lists, as
        NetPlumberAdapter._build_headerspace forms it. """
        keys = sorted(gen.fields)
        sets = []
        for combo in itertools.product(*(gen.fields[k] for k in keys)):
            t = self._ternary(ir, combo)
            if t is not None:
                sets.append(t)
        return sets

    @staticmethod
    def _reject_probe_paths(probe: Any) -> None:
        for path in (probe.test_path, probe.filter_path):
            if path is not None and path.to_json().get("pathlets"):
                raise Unsupported(
                    "probe %s has a path condition: path-constrained probes "
                    "are not translated in V1" % probe.node)

    def match_sets(self, lpm_only: bool = False,
                   fields: Optional[Sequence[str]] = None
                   ) -> Tuple[List[Tuple[str, int]], List[str], int]:
        """ Every rule's match as a ternary set, for the EC census (V2): ECs depend
        on matches alone, so any model type counts and actions are ignored.
        `lpm_only` keeps the declared longest-prefix-match tables only; `fields`
        projects onto those fields (a rule's other fields are dropped). Returns
        (layout, sets, rules counted). """
        models = self._models
        layout = _census_layout(models, fields)
        names = {n for n, _w in layout}
        ir = Ir(fields=layout, tables={}, ports={}, port_table={}, links=[],
                rules=[], generators={}, probes={}, origin={})
        for model in models:
            for pname in model.ports:
                ir.ports.setdefault(pname, len(ir.ports) + 1)
        sets, counted = [], 0
        for model in models:
            for tname, rules in model.tables.items():
                if lpm_only and model.table_semantics.get(tname) != LPM:
                    continue
                for rule in rules:
                    counted += 1
                    t = self._ternary(ir, [f for f in rule.match if f.name in names])
                    if t is not None:
                        sets.append(t)
        return layout, sets, counted

    def condition_sets(self, ir: Ir, base: str, cond: Sequence[Any]) -> List[str]:
        """ `base` restricted by a check's condition fields; negated ones
        expand (Q17). """
        sets = [base]
        for fld in cond:
            off = ir.offset(fld.name)
            bits = self._field_bits(ir, fld)
            nxt = []
            for s in sets:
                if fld.negated:
                    nxt.extend(expand_negated(s, off, bits))
                else:
                    piece = 'x' * off + bits + 'x' * (ir.width - off - len(bits))
                    met = _intersect(s, piece)
                    if met is not None:
                        nxt.append(met)
            sets = nxt
        return sets


def node_edges(ir: Ir) -> List[Tuple[int, int, int]]:
    """ Delta-net's graph (DN §4.3.2) over the IR: a node per (table, ingress
    port), an edge (table, in_port) -> the port it enters wherever a rule at
    the node forwards to a port linked there. Edges into probes are FaVe's
    delivery wiring and are left out. Sorted (table, in_port, to_port). """
    links: Dict[int, List[int]] = {}
    for a, b in ir.links:
        links.setdefault(a, []).append(b)
    probe_tables = set(ir.probes.values())
    edges = set()
    for rule in ir.rules:
        if rule.consume:
            continue
        for port in rule.out_ports:
            for to in links.get(port, []):
                if ir.port_table[to] not in probe_tables:
                    edges.add((rule.table, rule.in_port, to))
    return sorted(edges)


def _census_layout(models: List[Any], fields: Optional[Sequence[str]]) -> List[Tuple[str, int]]:
    if fields is not None:
        wanted = set(fields)
    else:
        wanted = {f.name for m in models for rs in m.tables.values()
                  for r in rs for f in r.match}
    unknown = wanted - set(FIELD_SIZES)
    if unknown:
        raise Unsupported("fields without a known width: %s" % sorted(unknown))
    return [(name, FIELD_SIZES[name]) for name in FIELD_SIZES if name in wanted]
