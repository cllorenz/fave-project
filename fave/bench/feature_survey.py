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

""" Survey what a workload asks of a verification engine.

WHY THIS EXISTS. VERIFLOW_PLAN.md V0 needs each workload's features before a
line of VeriFlow-FR is written -- which fields are matched and how, what is
rewritten, how forwarding is shaped -- and D6 needs, per workload, which fields
are trie dimensions and which are scanned (`vf_fields`). TODO item 31's
accommodation registry needs the same facts for every other tool: Delta-net
matches destination prefixes only, the 5-tuple tools five fields.

WHERE IT LOOKS. At what an engine is HANDED. `RecordingEngine` stands where an
engine stands, behind a real in-process aggregator (`util.in_process_driver`),
so it sees exactly the device models NetPlumber, APKeep and ad6 see -- after
FaVe's model building, before any adapter's encoding. What an adapter
synthesises for itself (NetPlumber's pre-routing tables, APKeep's ingress
demultiplexing) is therefore NOT counted: that is the adapter's accommodation,
and the registry records it there.

HOW A VALUE IS CLASSIFIED. By its bit vector, the form every engine sees (see
`classify_vector`); a negated value is its own kind. The kinds are pinned by
test/test_feature_survey.py.

Usage, from fave/ with PYTHONPATH=. and the venv active:

    python3 bench/feature_survey.py --bench bench/wl_ifi
    python3 bench/feature_survey.py --bench bench/wl_i2/i2-json \\
        --files topology=device_topology.json,policies=probes.json --json out.json

Firewall workloads with an `-o` match in a filter chain need
FAVE_ALLOW_OUT_IFACE=1 (TODO item 13a); the model then leaves that match
unmodelled, and the survey says so in its `notes`.
"""

import argparse
import contextlib
import json
import os
import sys
import threading

from collections import Counter, defaultdict
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

from aggregator.abstract_engine import AbstractVerificationEngine
from rule.rule_model import Forward, Miss, Rewrite
from util.ip6np_util import VectorConstructionError, field_value_to_bitvector


#: The kinds a vector can have, in the order a table prints them.
KINDS = ("any", "exact", "prefix", "ternary", "negated")

#: Kinds that make a field a trie dimension under D6 -- an arbitrary wildcard.
#: A negation counts: its expansion is a set of single-bit ternary vectors.
_TRIE_KINDS = frozenset(("prefix", "ternary", "negated"))


def classify_vector(bits: str) -> str:
    """ ANY, EXACT, PREFIX (wildcards only at the end) or TERNARY. """
    bits = bits.replace(",", "")
    if all(b == "x" for b in bits):
        return "any"
    if "x" not in bits:
        return "exact"
    first = bits.index("x")
    if all(b == "x" for b in bits[first:]):
        return "prefix"
    return "ternary"


#: Port-typed fields: before an adapter resolves it, the value is a port NAME.
_PORT_FIELDS = frozenset(("in_port", "out_port", "interface"))


def classify_field(field: Any) -> str:
    """ Classify a RuleField through FaVe's own bit-vector conversion. """
    if field.negated:
        return "negated"
    try:
        vector = field_value_to_bitvector(field).vector
    except VectorConstructionError:
        if field.name in _PORT_FIELDS:
            return "exact"      # a named port denotes exactly one port
        raise
    return classify_vector(vector)


def classify_rewrite(field: Any) -> str:
    """ FULL (set to one value), MASKED (set some bits, keep the rest -- NAT to
    a subnet), or CLEAR (set to ANY: FaVe's way of forgetting its in_port /
    out_port metadata at post-routing). """
    kind = classify_field(field)
    return {"exact": "full", "any": "clear"}.get(kind, "masked")


def vf_fields(kinds: Dict[str, Dict[str, int]]) -> Dict[str, List[str]]:
    """ D6's per-workload field classification: TRIE if any rule constrains the
    field with an arbitrary wildcard, SCAN if every constraint is exact, UNUSED
    if nothing constrains it. """
    buckets: Dict[str, List[str]] = {"trie": [], "scan": [], "unused": []}
    for name, counts in kinds.items():
        used = {k for k, n in counts.items() if n and k != "any"}
        if used & _TRIE_KINDS:
            buckets["trie"].append(name)
        elif used:
            buckets["scan"].append(name)
        else:
            buckets["unused"].append(name)
    return {k: sorted(v) for k, v in buckets.items()}


class RecordingEngine(AbstractVerificationEngine):
    """ An engine that verifies nothing and remembers everything it is given. """

    def __init__(self) -> None:
        # Read and written by the aggregator itself (links bookkeeping and the
        # dynamic-socket test), so they must exist even though they mean nothing.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}
        self.models: List[Any] = []
        self.generators: List[Any] = []
        self.probes: List[Any] = []
        self.link_list: List[Any] = []
        self._port_ids: Dict[Any, int] = {}

    def global_port(self, port: Any) -> int:
        """ A stable number per port name; the aggregator keys its link
        bookkeeping by it. """
        return self._port_ids.setdefault(port, len(self._port_ids) + 1)

    def add_tables(self, model: Any) -> None:
        pass

    def add_wiring(self, model: Any) -> None:
        pass

    def add_rules(self, model: Any) -> None:
        # The aggregator hands the engine a DIFF per call (aggregator_service
        # `add = model - self.models[...]`), so each call is new content -- but
        # only AT CALL TIME: it keeps the first model object per device and
        # later extends that object in place with the next command's rules. A
        # reference would therefore count those rules twice (79,000 on
        # wl_airtel1 for a 39,500-rule model), so the recorder snapshots.
        self.models.append(SimpleNamespace(
            node=model.node,
            type=model.type,
            table_semantics=dict(getattr(model, "table_semantics", {}) or {}),
            tables={table: list(rules) for table, rules in model.tables.items()},
        ))

    def add_link(self, sport: Any, dport: Any) -> None:
        self.link_list.append((sport, dport))

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        self.link_list.extend(links)

    def add_generator(self, model: Any) -> None:
        self.generators.append(model)

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        self.generators.extend(models)

    def add_probe(self, model: Any) -> None:
        self.probes.append(model)

    def check_compliance(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def get_compliance_results(self) -> List[Any]:
        return []

    def stop(self, *_args: Any, **_kwargs: Any) -> None:
        pass


def _count_fields(fields: Any, into: Dict[str, Counter]) -> None:
    for field in fields:
        into[field.name][classify_field(field)] += 1


def _plain(counters: Dict[str, Counter]) -> Dict[str, Dict[str, int]]:
    return {name: dict(c) for name, c in sorted(counters.items())}


def survey(engine: RecordingEngine) -> Dict[str, Any]:
    """ Count what `engine` recorded. """
    devices: Counter = Counter()
    semantics: Counter = Counter()
    fields: Dict[str, Counter] = defaultdict(Counter)
    rewrites: Dict[str, Counter] = defaultdict(Counter)
    rules: Counter = Counter(total=0, in_port_qualified=0, multi_in_port=0,
                             in_port_expanded=0, multi_port_forward=0,
                             drop=0, miss=0, rewriting=0)
    tables: Counter = Counter()
    raw_lines: Counter = Counter()
    seen_nodes = set()

    for model in engine.models:
        if model.node not in seen_nodes:
            seen_nodes.add(model.node)
            devices[model.type] += 1
        declared = getattr(model, "table_semantics", {}) or {}
        for table, table_rules in model.tables.items():
            if not table_rules:
                continue
            if table not in tables:
                semantics[declared.get(table, "first_match")] += 1
            tables[table] += len(table_rules)
            for rule in table_rules:
                rules["total"] += 1
                if rule.in_ports:
                    rules["in_port_qualified"] += 1
                if len(rule.in_ports) > 1:
                    rules["multi_in_port"] += 1
                # One rule per ingress port: what an engine whose match holds a
                # single IN_PORT value (OpenFlow, VeriFlow) must expand it into.
                rules["in_port_expanded"] += max(1, len(rule.in_ports))
                _count_fields(rule.match, fields)
                forwards = [a for a in rule.actions if isinstance(a, Forward)]
                ports = [p for a in forwards for p in a.ports]
                if len(ports) > 1:
                    rules["multi_port_forward"] += 1
                if any(isinstance(a, Miss) for a in rule.actions):
                    rules["miss"] += 1
                elif not ports:
                    rules["drop"] += 1
                rws = [a for a in rule.actions if isinstance(a, Rewrite)]
                if rws:
                    rules["rewriting"] += 1
                for action in rws:
                    for field in action.rewrite:
                        rewrites[field.name][classify_rewrite(field)] += 1
                if rule.raw_line_no is not None:
                    raw_lines[(model.node, table, rule.raw_line_no)] += 1

    gen_fields: Dict[str, Counter] = defaultdict(Counter)
    for gen in engine.generators:
        for values in gen.fields.values():
            _count_fields(values, gen_fields)

    probe_fields: Dict[str, Counter] = defaultdict(Counter)
    probe_paths = 0
    for probe in engine.probes:
        for group in (probe.filter_fields, probe.test_fields):
            for values in group.values():
                _count_fields(values, probe_fields)
        if getattr(probe.test_path, "pathlets", None) or \
                getattr(probe.filter_path, "pathlets", None):
            probe_paths += 1

    expansion: Dict[str, Any] = {"raw_lines": len(raw_lines)}
    if raw_lines:
        sizes = list(raw_lines.values())
        expansion.update(
            max=max(sizes),
            mean=round(sum(sizes) / len(sizes), 3),
            expanded_lines=sum(1 for s in sizes if s > 1))

    plain_fields = _plain(fields)
    return {
        "devices": dict(devices),
        "tables": len(tables),
        "semantics": dict(semantics),
        "rules": dict(rules),
        "fields": plain_fields,
        "rewrites": _plain(rewrites),
        "expansion": expansion,
        "links": len(engine.link_list),
        "generators": {"count": len(engine.generators),
                       "fields": _plain(gen_fields)},
        "probes": {"count": len(engine.probes), "with_path": probe_paths,
                   "fields": _plain(probe_fields)},
        "vf_fields": vf_fields(plain_fields),
    }


def survey_checks(checks: List[str]) -> Dict[str, Any]:
    """ Survey a workload's checks.json. Checks reach an engine through
    check_compliance, not the replay, so the recorder never sees them; parsed
    with the harness's own parser so both read a check the same way. """
    from bench.compliance_checker import _parse_check
    from rule.rule_model import RuleField

    counts: Counter = Counter(count=0, must_reach=0, must_not_reach=0,
                              conditioned=0)
    fields: Dict[str, Counter] = defaultdict(Counter)
    for check in checks:
        _src, _dst, negated, cond = _parse_check(check)
        counts["count"] += 1
        counts["must_not_reach" if negated else "must_reach"] += 1
        if cond:
            counts["conditioned"] += 1
        _count_fields((RuleField(c["name"], c["value"], negated=c["negated"])
                       for c in cond), fields)
    result: Dict[str, Any] = dict(counts)
    result["fields"] = _plain(fields)
    return result


@contextlib.contextmanager
def raise_thread_errors() -> Iterator[None]:
    """ Re-raise, in the caller, the first exception any thread raised inside
    the block. The aggregator applies commands on a worker thread, whose
    exceptions would otherwise only be printed -- and a survey of the part of the
    model that did arrive would look like a survey of the whole. """
    errors: List[BaseException] = []
    previous = threading.excepthook

    def hook(args: Any) -> None:
        errors.append(args.exc_value)
        previous(args)

    threading.excepthook = hook
    try:
        yield
    finally:
        threading.excepthook = previous
    if errors:
        raise errors[0]


def run(prefix: str, files: Optional[Dict[str, str]] = None,
        checks: Optional[str] = None) -> Dict[str, Any]:
    """ Replay a workload through a real in-process aggregator and survey it. """
    from util.in_process_driver import InProcessFaVe

    engine = RecordingEngine()
    with raise_thread_errors():
        with InProcessFaVe(engine) as fave:
            fave.replay(prefix, files=files)
    result = survey(engine)
    result["workload"] = prefix
    if checks:
        with open(checks) as raw:
            result["checks"] = survey_checks(json.load(raw))
    notes = []
    if os.environ.get("FAVE_ALLOW_OUT_IFACE"):
        notes.append("FAVE_ALLOW_OUT_IFACE=1: `-o` matches in filter chains "
                     "are left unmodelled (TODO item 13a)")
    result["notes"] = notes
    return result


def _parse_files(spec: Optional[str]) -> Optional[Dict[str, str]]:
    if not spec:
        return None
    return dict(item.split("=", 1) for item in spec.split(","))


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bench", required=True,
                        help="workload directory holding the model JSON")
    parser.add_argument("--files", default=None,
                        help="role=file overrides, e.g. topology=device_topology.json")
    parser.add_argument("--checks", default=None,
                        help="the workload's checks.json (default: <bench>/checks.json if present)")
    parser.add_argument("--json", default=None, help="write the result here")
    args = parser.parse_args(argv)

    checks = args.checks
    if checks is None and os.path.isfile(os.path.join(args.bench, "checks.json")):
        checks = os.path.join(args.bench, "checks.json")
    result = run(args.bench, _parse_files(args.files), checks)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as out:
            out.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
