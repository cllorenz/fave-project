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

""" An AbstractVerificationEngine backed by ad6 (SAT/QBF model checking),
via a subprocess bridge into the ad6/ package (AD6_PLAN.md, item 11 in
TODO.md; §4.2/§4.4 for the integration-architecture rationale).

Unlike APKeepAdapter/NetPlumberLibAdapter, ad6 does not run in-process:
running its Kripke/SAT model construction requires ad6's own `src.*` package
tree (rooted at the top-level `ad6/` directory, a sibling of `fave/`, with
its own PYTHONPATH assumptions), which we deliberately do not import into
FaVe's process (avoiding any risk of `src`-namespace collisions and mirroring
this project's existing isolation discipline for cross-backend contamination,
e.g. bench/apkeep_tum_diff.py's subprocess-per-backend workers). Instead this
adapter BUFFERS the FaVe model exactly like APKeepAdapter does, then at
check_compliance() translates it to ad6's config XML and drives
`ad6/fave_bridge.py` as a subprocess to build the ad6 model and answer the
queries.

THE TRANSLATION IS STRUCTURAL, AND SINCE §9.3 PHASE 5 IT IS THE ONLY ONE.
A FaVe table becomes an ad6 table, a FaVe rule becomes an ad6 rule AT ITS OWN
`idx`, a FaVe match field becomes an ad6 match, a FaVe action becomes an ad6
action, a FaVe link becomes an ad6 connection. No device or table NAME is ever
read. This works because ad6 evaluates a table first-match-wins in document
order (measured, not assumed -- §9.5, `ad6/test/core/instantiatortest.py::
RuleOrderSemanticsTest`), so preserving FaVe's own rule order preserves the
semantics, including the state semantics: FaVe's `_interweave_state_shell`
strips conntrack matches and re-emits plain `related` header fields, whose
meaning survives PURELY AS RULE POSITION (§9.2a).

The translation itself lives in `fave/ad6/translate.py`; this module buffers,
serializes and drives the bridge.

WHAT WAS DELETED HERE, AND WHERE TO FIND IT. Until Phase 5 this adapter also
carried a SEMANTIC path that reconstructed meaning from FaVe's naming
conventions (`in.`/`mid.`/`out.` stage prefixes, `.acl_in`/`.routing` table
suffixes) into an IR of interpreted concepts, which `ad6/src/parser/favemodel.py`
built from. Every measurement archived before Phase 5 came from it, and every
generality bug §9 chased traced back to it -- the LPM tiebreak, the
per-(port, VLAN) admission cross-product, the out-stage collapse, the wl_up
NO-GO, and a literal `if any(d.split('.', 1)[0] == 'mid' ...)` workload sniff in
the production path. It is gone as of §9.25, together with `favemodel.py`, the
`faithful_vlan`/`probe_untag` flags it alone honoured (§9.16.1), and the IR
snapshot tripwires Phase 0.2 raised for the rewrite.

**To reproduce a pre-Phase-5 number, check out commit 86114970** -- the last
one where the semantic path exists and runs. Passing `translation='semantic'`
here RAISES and says so, rather than silently answering a different question.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Optional, Tuple

from aggregator.abstract_engine import AbstractVerificationEngine
from aggregator.aggregator_abstract import TraceLogger

_SRC = 'packet.ipv4.source'
_SRC6 = 'packet.ipv6.source'
_SRCS = (_SRC, _SRC6)
_VLAN = 'packet.ether.vlan'

# AD6_PLAN.md §9: the model-construction path, kept as an explicit, stamped
# field even though only one value is live -- a result file must say what
# produced it, and 'structural' is what distinguishes a post-Phase-5 number
# from an archived one stamped 'semantic'. This module imports nothing from
# ad6/ or from translate.py at module scope, so the spelling is pinned by a
# test (fave/test/test_ad6_translation_flag.py) rather than shared.
TRANSLATION_STRUCTURAL = 'structural'
TRANSLATIONS = (TRANSLATION_STRUCTURAL,)

# Deleted at §9.25. Named here so the refusal below can be specific: a caller
# asking for it is asking for an encoding this tree no longer contains, and
# the useful answer is which commit still has it -- not a silent fallback to a
# different one.
_TRANSLATION_DELETED = 'semantic'
_TRANSLATION_DELETED_AT = '86114970'

_HERE = os.path.dirname(os.path.abspath(__file__))         # .../fave/ad6
_FAVE = os.path.dirname(_HERE)                              # .../fave
AD6_ROOT = os.path.normpath(os.path.join(_FAVE, '..', 'ad6'))
BRIDGE = os.path.join(AD6_ROOT, 'fave_bridge.py')

# AD6_PLAN.md §5.4 B1 / §5.5: the grounding strategies `fave_bridge.py`
# accepts. DUPLICATED, not imported, on purpose -- this module drives ad6 as a
# SUBPROCESS and deliberately imports nothing from the `ad6/` package (no
# sys.path surgery, no pysat dependency on the FaVe side). The canonical
# definition is `ad6/src/solver/incremental.py`'s GROUNDINGS, and
# fave/test/test_ad6_grounding.py asserts these two lists stay identical, so
# the duplication cannot drift silently.
GROUNDING_RANK = 'rank'
GROUNDING_FLOW = 'flow'
GROUNDINGS = (GROUNDING_RANK, GROUNDING_FLOW)


def available() -> bool:
    """ True iff the ad6 bridge script exists (no JVM/native-lib check needed
    -- ad6 is pure Python + the pycosat/minisat/clasp solvers). """
    return os.path.isfile(BRIDGE)


class Ad6Adapter(AbstractVerificationEngine):
    """ Drive ad6 as a FaVe verification backend. """

    def __init__(self, logger: TraceLogger,
                 grounding: str = GROUNDING_RANK,
                 translation: str = TRANSLATION_STRUCTURAL) -> None:
        self.logger = logger
        # AD6_PLAN.md §5.4 B1 / §5.5: WHICH constraint grounds a witness in a
        # real origin, closing the SECRYPT'15 formalism's gap
        # (ad6/FAVE_CHANGES.md §20). Both answer the same question and are
        # held to identical ground truth in ad6's own test suite; they differ
        # in cost and in scope.
        #
        # 'rank' (default) is property-agnostic -- it forbids every floating
        # cycle in the shared base, so it is the only option for a question
        # that is not a single source->destination reachability query, and
        # changing the default would silently re-measure every existing
        # wl_ifi/wl_up/wl_tum/wl_stanford result.
        #
        # 'flow' is a per-query single-unit s-t flow: reachability-SPECIFIC,
        # and on wl_stanford N=16 faithful-VLAN, under a matched configuration
        # (both cadical195), measured 7.0x faster wall / 9.3x faster query /
        # 1.4x lower peak RSS for the identical answer (165 reachable pairs).
        # Prefer it for an all-pairs reachability sweep; it cannot express
        # anything else.
        #
        # Kept as an explicit constructor argument rather than inferred, so a
        # result can be STAMPED with the encoding that produced it -- see
        # AD6_PLAN.md's generality-debt gate.
        if grounding not in GROUNDINGS:
            raise ValueError(
                "unknown grounding strategy %r -- expected one of %s" % (
                    grounding, ', '.join(repr(g) for g in GROUNDINGS)))
        self.grounding = grounding

        # AD6_PLAN.md §9.25: one live translation, still stamped. The argument
        # survives the deletion of the second path on purpose -- it is what a
        # result file carries to distinguish a structural number from an
        # archived semantic one.
        if translation == _TRANSLATION_DELETED:
            raise ValueError(
                "the %r translation was DELETED at AD6_PLAN.md §9.25 -- it "
                "reconstructed meaning from FaVe's device and table names, and "
                "every generality bug §9 chased traced back to it. This tree "
                "cannot produce a %r result. To reproduce a measurement "
                "archived under it, check out commit %s, where it still runs. "
                "Refusing rather than falling back to %r, which would answer a "
                "DIFFERENT question under the requested label."
                % (_TRANSLATION_DELETED, _TRANSLATION_DELETED,
                   _TRANSLATION_DELETED_AT, TRANSLATION_STRUCTURAL))
        if translation not in TRANSLATIONS:
            raise ValueError(
                "unknown translation %r -- expected one of %s" % (
                    translation, ', '.join(repr(t) for t in TRANSLATIONS)))
        self.translation = translation

        # The raw model capture the translator reads. `_raw_edges` keeps the
        # UNNORMALISED port names -- the "_ingress"/"_egress" suffix is what
        # names which interface a port is, and translate.PortGraph needs it.
        self._tables: Dict[str, Dict[str, Any]] = {}
        self._wiring: Dict[str, List[Any]] = {}
        self._raw_edges: List[List[str]] = []
        self._gen_fields: Dict[str, Any] = {}
        self._generators: Dict[str, str] = {}          # name -> "device.port"
        self._probes: Dict[str, str] = {}              # name -> "device.port"
        self._gen_src: Dict[str, str] = {}              # name -> cidr
        self._results: List[Tuple[str, str, bool, str]] = []
        # Surface the aggregator dispatch touches, like APKeepAdapter.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}

    def configuration_stamp(self) -> Dict[str, Any]:
        """ The honest configuration behind this adapter's answers, for a
        caller that records measurements.

        `faithful_vlan`/`probe_untag` are gone rather than reported as None:
        they were semantic-path flags that §9.16.1 already established DO NOT
        APPLY to a structural model (which carries VLAN unconditionally,
        whatever a flag says), and the path they configured no longer exists.
        An archived stamp carrying them came from a run this tree cannot
        reproduce -- see this module's docstring. """
        return {
            "translation": self.translation,
            "grounding": self.grounding,
        }

    def global_port(self, port: Any) -> Any:
        return port

    # --- AbstractVerificationEngine: model construction (buffered) ----------

    def add_tables(self, model: Any) -> None:
        """ Nothing to do: a device enters the model through its RULES, and
        `add_rules` records the table structure they arrive in. The semantic
        path kept a separate device set because its IR was keyed by device
        independently of any rule; the translator has no such notion. Kept as
        an explicit no-op because the aggregator dispatches it. """

    def add_rules(self, model: Any) -> None:
        device_tables = self._tables.setdefault(model.node, {})
        for table_name, table_rules in model.tables.items():
            device_tables[table_name] = list(table_rules)

    def add_wiring(self, model: Any) -> None:
        """ FaVe DECLARES each device's internal pipeline as unidirectional
        port-to-port links (AbstractDevice.wiring), and the translator uses
        that declaration rather than rebuilding an approximation of it from
        table-name suffixes (AD6_PLAN.md §9.8.2). """
        pairs = getattr(model, 'wiring', None) or []
        if pairs:
            self._wiring.setdefault(model.node, []).extend(
                [list(pair) for pair in pairs])

    def add_link(self, sport: str, dport: str) -> None:
        self._raw_edges.append([sport, dport])

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        for sport, dport in links:
            self.add_link(sport, dport)

    def add_generator(self, model: Any) -> None:
        self._generators[model.node] = model.node + '.1'
        self._gen_fields[model.node] = getattr(model, 'fields', None) or {}
        fields = getattr(model, 'fields', None)
        if fields:
            for fname, rfields in fields.items():
                if not rfields:
                    continue
                if fname in _SRCS:
                    self._gen_src[model.node] = str(rfields[0].value)

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        for model in models:
            self.add_generator(model)

    def add_probe(self, model: Any) -> None:
        self._probes[model.node] = model.node + '.1'

    # --- build + query --------------------------------------------------

    @staticmethod
    def _cond_to_json(cond: Any) -> List[Dict[str, Any]]:
        """ `cond` arrives here as whatever check_compliance's caller passed:
        real dispatch through aggregator_service.py's `_handler` (the
        InProcessFaVe/JSON-socket path every backend shares) has already
        turned each entry into a RuleField object -- not JSON-serialisable
        as-is, so this normalises to RuleField.to_json()'s plain-dict shape
        (also passed through unchanged for a caller that already hands us
        dicts, e.g. a test driving check_compliance directly). """
        out = []
        for field in (cond or []):
            out.append(field.to_json() if hasattr(field, "to_json") else field)
        return out

    def _build_structural(self) -> Dict[str, Any]:
        """ AD6_PLAN.md §9: the payload -- ad6 config XML plus the Kripke edges
        XML cannot express, plus each source's and probe's own query node.

        Translation happens HERE, in FaVe's process, rather than in the bridge,
        because `translate.py` needs both vocabularies at once: ad6's GenUtils
        to emit, and FaVe's own `rule_model` classes to read. Only the finished
        XML crosses the subprocess boundary, so the bridge still needs nothing
        from FaVe. (The adapter's own no-ad6-imports discipline is not weakened:
        `translate` is imported inside this method, so merely constructing an
        adapter never touches ad6's package tree.) """
        import lxml.etree as et

        from ad6 import translate
        from src.xml.xmlutils import XMLUtils      # translate put ad6 on sys.path

        devices: Dict[str, Any] = {
            device: {'tables': tables,
                     'ports': [],
                     'wiring': self._wiring.get(device, [])}
            for device, tables in self._tables.items()
        }

        # The mutable set spans EVERY device's rules, and the generators' own
        # rewrites depend on it -- so it is computed before they are built
        # (§9.6: a field rewritten anywhere must be matched node-scoped
        # everywhere, or the same field resolves against a global alias in one
        # place and an SSA copy in another).
        every_rule = [rule for tables in self._tables.values()
                      for table_rules in tables.values() for rule in table_rules]
        mutable = translate.rewritten_fields(every_rule)
        # Generic fields that are MATCHED also reach a <fieldmatch> and also
        # need a declared width, even though nothing rewrites them.
        matched_generic = translate.matched_generic_fields(every_rule)

        for source in self._generators:
            devices[source] = translate.generator_device(
                source, self._gen_fields.get(source), mutable=mutable)
        for probe in self._probes:
            devices[probe] = translate.probe_device(probe)

        graph = translate.PortGraph(devices, self._raw_edges)
        config, edges = translate.model_to_config(devices, self._raw_edges)
        # Deannotated HERE rather than in the bridge, so what crosses the
        # boundary is plain XML the bridge can parse without knowing how it was
        # produced.
        XMLUtils.deannotate(config)

        # THE NAMESPACE MUST NOT SURVIVE THE ROUND TRIP, and getting this wrong
        # fails SILENTLY. `GenUtils.config()` declares xmlns="http://config" on
        # the root while every child it builds carries no namespace at all --
        # which is consistent in memory, where ad6's unprefixed xpaths
        # (XMLUtils.RULEPATH and friends) match. Serialize it, though, and the
        # declaration becomes the DEFAULT namespace for the whole document, so
        # on re-parse every descendant is suddenly in it and every one of those
        # xpaths matches NOTHING -- no error, just an empty model. Re-rooting
        # onto a plain <config> keeps the serialized form matching the in-memory
        # semantics. Pinned by test_ad6_translation_flag.py.
        plain = et.Element('config')
        for child in list(config):
            plain.append(child)

        return {
            "config": et.tostring(plain).decode('utf-8'),
            "edges": [list(edge) for edge in edges],
            "sources": {name: translate.generator_entry_key(name)
                        for name in self._generators},
            "probes": {name: translate.probe_entry_key(name)
                       for name in self._probes},
            # A <fieldmatch> is emitted whenever some rule rewrites the field,
            # so the widths are derived from what was actually emitted.
            "mutable_fields": translate.mutable_field_widths(
                mutable, port_width=graph.port_id_width(),
                matched=matched_generic),
        }

    def check_compliance(self, rules: Any) -> None:
        """ rules: {probe_name: [(source_name, negated, cond), ...]}. Builds
        the ad6 model and answers every pair in one bridge subprocess call. """
        queries = []
        for probe_name, src_rules in rules.items():
            dst_port = self._probes[probe_name]
            for source_name, negated, cond in src_rules:
                src_port = self._generators[source_name]
                queries.append({
                    "source": source_name, "probe": probe_name,
                    "src_port": src_port, "dst_port": dst_port,
                    "src_cidr": self._gen_src.get(source_name),
                    "negated": bool(negated), "cond": self._cond_to_json(cond),
                })
        payload = {"queries": queries,
                   "grounding": self.grounding,
                   "translation": self.translation,
                   "structural": self._build_structural()}
        with tempfile.TemporaryDirectory(prefix="ad6_bridge_") as tmp:
            in_path = os.path.join(tmp, "in.json")
            out_path = os.path.join(tmp, "out.json")
            with open(in_path, "w") as raw:
                json.dump(payload, raw)
            proc = subprocess.run(
                [sys.executable, BRIDGE, "--in", in_path, "--out", out_path],
                cwd=AD6_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    "ad6 bridge failed (rc=%d):\n%s" % (
                        proc.returncode, proc.stderr.decode("utf-8", "replace")[-4000:]
                    )
                )
            with open(out_path) as raw:
                results = json.load(raw)
        for r in results:
            must_reach = not r["negated"]
            if r["reachable"] != must_reach:
                self._results.append((r["source"], r["probe"], must_reach, r["cond"] or ""))

    def get_compliance_results(self) -> List[Tuple[str, str, bool, str]]:
        return list(self._results)

    def clear_results(self) -> None:
        self._results = []

    # --- not yet supported (not exercised by the forwarding+ACL milestone) --

    def check_anomalies(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Ad6Adapter: check_anomalies not supported")

    def add_slice(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Ad6Adapter: slices not supported")

    def del_slice(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Ad6Adapter: slices not supported")

    def dump_flows(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_flow_trees(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_pipes(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dump_plumbing_network(self, *args: Any, **kwargs: Any) -> None:
        pass

    def remove_link(self, sport: Any, dport: Any) -> None:
        if sport in self.links and dport in self.links[sport]:
            self.links[sport].remove(dport)

    def delete_generator(self, node: str) -> None:
        self._generators.pop(node, None)

    def delete_probe(self, node: str) -> None:
        self._probes.pop(node, None)

    def stop(self) -> None:
        pass
