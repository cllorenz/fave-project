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
check_compliance() serializes a neutral JSON IR and queries, and drives
`ad6/fave_bridge.py` as a subprocess to build the ad6 model and answer them.

SCOPE (first milestone, matches wl_ifi -- AD6_PLAN.md §4.4): IPv4 dst-IP
forwarding (routers + switches) + ingress/egress ACLs. VLAN is structural
only (which port's ACL group applies), never a match field -- wl_ifi's roles
are IP-distinct, so VLAN is redundant for reachability (same finding as
APKeepAdapter's P4 milestone). Mirrors APKeepAdapter's capture design
(add_tables/add_rules/add_link/add_generator/add_probe buffering, lazy build,
_splice_acls-style ingress/egress port tracing) but written independently
against this adapter's own IR, not by importing apkeep.adapter's internals.
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
from rule.rule_model import Forward, Rewrite

_DST = 'packet.ipv4.destination'
_SRC = 'packet.ipv4.source'
_DST6 = 'packet.ipv6.destination'
_SRC6 = 'packet.ipv6.source'
_DSTS = (_DST, _DST6)
_SRCS = (_SRC, _SRC6)
_VLAN = 'packet.ether.vlan'
# AD6_PLAN.md §5.5: the `_in_vlans` port key for an admission rule that names
# no ingress port -- one admitting its VLAN on every port of its device. MUST
# equal favemodel._ANY_PORT (this adapter deliberately imports nothing from
# the ad6 tree, see the module docstring, so the two are pinned equal by
# test_ad6_wl_i2_admission.py instead of shared).
# AD6_PLAN.md §9: the two model-construction paths. A local tuple, like
# GROUNDINGS below: this adapter imports nothing from ad6/ or from
# translate.py at module scope, and the spelling is pinned by a test
# (fave/test/test_ad6_translation_flag.py) so the two cannot drift.
TRANSLATION_SEMANTIC = 'semantic'
TRANSLATION_STRUCTURAL = 'structural'
TRANSLATIONS = (TRANSLATION_SEMANTIC, TRANSLATION_STRUCTURAL)

_ANY_PORT = '*'
_RELATED = 'related'    # AD6_PLAN.md §4.2: connection-state match, "0"=NEW,
                        # "1"=ESTABLISHED (mirrors apkeep/adapter.py:_RELATED;
                        # the FaVe policy compiler's state-shell, see
                        # fave/iptables/generator.py:_derive_general_state_shell/
                        # _calculate_blocks, only ever emits these two values --
                        # never a compound "ESTABLISHED,RELATED" -- so a 1:1
                        # related-value -> ad6-state mapping is exact here).
_OUT_PORT = 'out_port'

_MAX_PRIO = 65535


def _prefix_len(cidr: str) -> int:
    """ The prefix length of a "<addr>/<len>" CIDR string as captured from a
    dst match field (always this shape -- see favemodel.py's `_MATCH_ALL`,
    "0.0.0.0/0"/"::/0"). Falls back to a full-length host match (32/128) for
    the (currently unobserved, but not guaranteed-absent) case of a bare
    address with no explicit mask, rather than assuming the "/" is always
    present. """
    _addr, sep, mask = cidr.rpartition('/')
    if sep:
        return int(mask)
    return 128 if ':' in mask else 32  # no '/': rpartition puts all of `cidr` in `mask`


def _lpm_prio(dst: Optional[str]) -> int:
    """ ad6's own table evaluation is sequential first-match (ascending prio
    = evaluated first), not a priority-wins ForwardElement like APKeep's --
    so a genuine longest-prefix-match decision requires the MORE SPECIFIC
    (longer-prefix) dst-specific route to sort BEFORE a less specific one on
    the same device, not just "any dst-specific route before the no-dst
    default". A prior version of this function used a binary 0-vs-65535
    split ("specific before default"), which is only exact when a device
    never carries two overlapping-prefix routes -- true for wl_ifi/wl_up
    (confirmed by inspection at the time), but false in general (e.g.
    Stanford's real FIBs, AD6_PLAN.md §5.2 -- caught test-first by
    ad6/test/parser/favemodeltest.py::RoutingTableLPMTest, which fed the
    same two overlapping routes in both insertion orders and found the
    answer flipped). The no-dst default always sorts last. """
    if dst is None:
        return _MAX_PRIO
    return _MAX_PRIO - 1 - _prefix_len(dst)

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


def _split_port(fave_port: str) -> Tuple[str, str]:
    """ "device.port"[_ingress|_egress] -> (device, port). Mirrors
    apkeep.adapter._split_port; device may itself contain dots. """
    for suffix in ("_ingress", "_egress"):
        if fave_port.endswith(suffix):
            fave_port = fave_port[:-len(suffix)]
            break
    device, _, port = fave_port.rpartition('.')
    return device, port


class Ad6Adapter(AbstractVerificationEngine):
    """ Drive ad6 as a FaVe verification backend (forwarding + ACLs, matching
    wl_ifi's model). """

    def __init__(self, logger: TraceLogger, faithful_vlan: bool = False,
                 probe_untag: bool = False,
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

        # AD6_PLAN.md §9: which TRANSLATION built the model this adapter hands
        # to ad6. Measurement-affecting configuration, so it is an explicit
        # argument and a stamped field rather than a habit.
        #
        #   'structural' (default since §9.3 Phase 5) -- fave/ad6/translate.py.
        #       Translates FaVe's model as given: a table becomes a table, a
        #       rule becomes a rule at its own position, a port is resolved
        #       from declared wiring and links. Reads no device or table name.
        #   'semantic'   -- the original path, RETAINED ONLY FOR COMPARISON.
        #       RECONSTRUCTS meaning from FaVe's naming conventions (in./mid./
        #       out. stage prefixes, .acl_in/.routing table suffixes) into an
        #       IR of interpreted concepts, which ad6/src/parser/favemodel.py
        #       then builds from. Every measurement archived before Phase 5
        #       came from this path, which is why it is still selectable.
        #
        # The default flipped only after the differential agreed on every
        # benchmark in scope (§9.3 Phase 3: wl_ifi 54/54, wl_stanford 165 plain
        # and faithful, wl_i2 -- where structural is the one that is RIGHT on
        # the 11 disputed pairs, §9.16 -- and wl_up 3,661 = 3,661 against
        # NetPlumber, §9.22). Anything re-measured from here is measured
        # STRUCTURALLY; an archived number is comparable only to a run that
        # passes translation=TRANSLATION_SEMANTIC explicitly.
        #
        # ONE DELIBERATE LOSS OF SCOPE, owner decision at the Phase 5 gate:
        # wl_ifi's 54 stateful `related` checks are UNANSWERABLE structurally
        # and the bridge refuses them rather than answering the unconditioned
        # question. wl_ifi's ACLs come from Cisco text carrying no conntrack
        # qualifier, so FaVe's interweaving has nothing to strip and emits no
        # `related` field for the translator to carry. The semantic path
        # answered them by forcing ad6 <state> variables onto a state-blind
        # model (27 pass / 27 fail, §4.2's open question); the refusal is the
        # more honest answer, so the question is closed as MALFORMED rather
        # than inherited. See test_ad6_wl_ifi_stateful.py.
        # AD6_PLAN.md §9.16.1: `faithful_vlan` DOES NOT APPLY under the
        # structural translation, and saying so is a correctness requirement,
        # not a nicety. The semantic path's plain mode deliberately discards
        # VLAN ("structural only, never a match field", see this class's own
        # docstring); the structural path translates FaVe's rules as given, and
        # they carry VLAN whatever the flag says. Measured on wl_i2: plain
        # SEMANTIC reports all 72 pairs reachable, plain STRUCTURAL reports the
        # 11 unreachable pairs that ad6, NetPlumber and bench/
        # i2_structural_oracle.py independently agree on. A structural result
        # stamped `faithful_vlan: false` would therefore be mislabelled -- and
        # the generality-debt gate's whole rule is that the stamp must say what
        # produced the number.
        if translation not in TRANSLATIONS:
            raise ValueError(
                "unknown translation %r -- expected one of %s" % (
                    translation, ', '.join(repr(t) for t in TRANSLATIONS)))
        self.translation = translation

        # Raw model capture for the structural path. Buffered unconditionally:
        # it is a few references per rule, and making it conditional would mean
        # the two paths saw DIFFERENT captures, which is exactly what a
        # differential must not have. `_raw_edges` keeps the UNNORMALISED port
        # names -- `add_link` strips "_ingress"/"_egress" for the IR, and the
        # structural path needs the real ones to resolve an interface.
        self._tables: Dict[str, Dict[str, Any]] = {}
        self._wiring: Dict[str, List[Any]] = {}
        self._raw_edges: List[List[str]] = []
        self._gen_fields: Dict[str, Any] = {}
        # AD6_PLAN.md §5.4 Stage B (B2): opt-in (default False, every existing
        # caller/benchmark unaffected -- wl_ifi/wl_up/wl_tum/B0-B1's own
        # plain wl_stanford tests never pass this). Ported (not imported)
        # from apkeep/adapter.py's own `faithful_vlan` flag and its P7b
        # Stanford-faithful capture methods below, for direct semantic
        # comparability between the two backends' faithful-VLAN models
        # (§5.4 Stage B: "reuse APKeep's own faithful-VLAN subset protocol
        # ... for direct comparability").
        self._faithful_vlan = faithful_vlan
        # AD6_PLAN.md §5.5 C4 (part 2): enforce the probe's own declared
        # arrival VLAN (wl_i2's access-port untag, `vlan=0`) as a query-time
        # constraint. SEPARATE from `faithful_vlan` and DEFAULT OFF, by
        # deliberate choice rather than caution -- see §5.5's PROBE-UNTAG
        # PARITY FINDING. Neither comparison backend enforces this condition
        # on i2: `netplumber/adapter.py` computes the header space from
        # `model.test_fields` and then DISCARDS it (two `XXX: deactivate ...
        # memory explosion` guards), sending `test={"type": "true"}` with an
        # empty match vector, and `apkeep/adapter.py`'s `target_vlan` is
        # gated `self._stanford and self._faithful_vlan`, so i2 passes
        # `None`. Enforcing it here unconditionally would therefore make ad6
        # the STRICTEST of the three and reintroduce a workload-parity gap in
        # the opposite direction from the one C4 exists to close. On (with
        # `faithful_vlan`) this is the scientifically faithful model; off it
        # matches how the other two are actually run. The difference between
        # the two is a measurement, not a default to guess at.
        self._probe_untag = probe_untag
        self._devices: set = set()
        self._fwd_rules: List[Dict[str, Any]] = []   # [{device,dst,ports,prio}]
        self._fwd_seen: set = set()                    # (device,dst,tuple(ports)) dedup
        self._routing_rules: List[Dict[str, Any]] = []   # [{device,dst,port,prio}]
        self._edges: List[List[str]] = []             # [[sport,dport], ...]
        # AD6_PLAN.md §5.4 Stage B (B0): wl_stanford's in.X/out.X stages --
        # see _capture_in_admit/_capture_out_perm/_collapse_out_stage below.
        self._in_admit: Dict[str, Optional[set]] = {}   # device -> admitted ports, None=all
        self._out_perm: Dict[str, Dict[str, set]] = {}   # out.X device -> in_port -> {out_ports}
        # AD6_PLAN.md §5.4 Stage B (B2), faithful_vlan only -- ported from
        # apkeep/adapter.py's P7b `_mid_rw`/`_out_reset`/`_in_vlans`
        # (`_capture_mid_rewrite`/`_capture_out_reset`/`_capture_in_admission`
        # below have the full semantics; see also _fold_mid_rewrites).
        self._mid_rw: Dict[str, List[Tuple[Optional[str], str, str]]] = {}  # mid.X -> [(dst,egress_port,vlan_n)]
        # AD6_PLAN.md §5.5 C4, faithful_vlan only -- wl_i2's own egress-VLAN
        # rewrite, the out-stage counterpart of `_mid_rw` above (ported from
        # apkeep/adapter.py's `_out_rw`/`_capture_out_rewrite`, which solved
        # the identical problem on that backend's i2 path). SEPARATE from
        # `_mid_rw` because the two workloads put the rewrite on different
        # stages and `_build_ir` treats those stages oppositely: wl_stanford's
        # `out.*` is a port permutation it COLLAPSES, wl_i2's `out.*` is the
        # real dst FIB it must keep. See _capture_out_rewrite.
        self._out_rw: Dict[str, List[Tuple[Optional[str], str, str]]] = {}  # out.X -> [(dst,egress_port,vlan_m)]
        self._out_reset: Dict[str, set] = {}            # out.X -> {(in_port, vlan)}
        # AD6_PLAN.md §5.5, faithful_vlan only: the per-(port, VLAN) ingress
        # admission RELATION -- in.X device -> arrival port -> {admitted vlan
        # tags}. Was a per-device set until 2026-09-10; see
        # _capture_in_admission for what that cost.
        self._in_vlans: Dict[str, Dict[str, set]] = {}   # in.X -> port -> {vlans}
        self._generators: Dict[str, str] = {}          # name -> "device.port"
        self._probes: Dict[str, str] = {}              # name -> "device.port"
        # AD6_PLAN.md §5.5 C4 (part 2): probe name -> the VLAN its model
        # declares that an arriving flow must carry. Captured whenever the
        # probe declares one, independently of `_probe_untag` -- the IR
        # always reports what the model SAYS, and the flag decides only
        # whether it is enforced.
        self._probe_vlan: Dict[str, str] = {}          # name -> vlan tag
        self._gen_src: Dict[str, str] = {}              # name -> cidr
        self._gen_vlan: Dict[str, str] = {}              # name -> vlan
        # AD6_PLAN.md §5.4 Stage 0: keyed by device first, then VLAN -- wl_ifi
        # has exactly one admission-checked router, so a bare vlan-keyed dict
        # was never wrong there, but Stanford's 16 independent in.X/out.X
        # devices can reuse the same VLAN number for unrelated admission
        # groups on different routers; a flat dict would silently let a
        # second device's capture clobber the first's (or merge unrelated
        # ACL entries under one vlan key). `_acl_devices` replaces the old
        # scalar `_acl_device` for the same reason (only one device could
        # ever be recorded before).
        self._acl_devices: set = set()
        self._acl_in: Dict[str, Dict[Optional[str], List[List[Any]]]] = {}
        self._acl_out: Dict[str, Dict[Optional[str], List[List[Any]]]] = {}
        self._vlan_to_eport: Dict[str, Dict[str, str]] = {}   # device -> vlan -> "device.port"
        self._iport_vlan: Dict[str, str] = {}             # "device.port" -> vlan
        self._results: List[Tuple[str, str, bool, str]] = []
        # wl_up (AD6_PLAN.md §5.1): per-device ip6tables rulesets + own
        # addresses, loaded on demand via load_bench_metadata() from the
        # benchmark's topology.json -- see that method's docstring for why
        # this bypasses FaVe's own already-parsed Rule/Match objects for rule
        # CONTENT (not for topology/wiring, which stays FaVe-model-driven).
        self._ruleset_text: Dict[str, str] = {}           # device -> raw ip6tables text
        self._device_addr: Dict[str, str] = {}            # device -> own address
        self._switch_devices: set = set()                 # pure L2 relays, no ruleset
        # Surface the aggregator dispatch touches, like APKeepAdapter.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}

    @property
    def faithful_vlan_applies(self) -> bool:
        """ Whether this adapter's `faithful_vlan` setting affects its answers.

        False under the structural translation, where VLAN is carried
        unconditionally (§9.16.1). Anything stamping a result from this adapter
        must consult THIS rather than `faithful_vlan`, or it will mislabel a
        faithful answer as a plain one. """
        return self.translation == TRANSLATION_SEMANTIC

    def configuration_stamp(self) -> Dict[str, Any]:
        """ The honest configuration behind this adapter's answers, for a
        caller that records measurements. `faithful_vlan` is reported as None
        when it does not apply, rather than as the value that was passed and
        ignored. """
        return {
            "translation": self.translation,
            "grounding": self.grounding,
            "faithful_vlan": self._faithful_vlan if self.faithful_vlan_applies else None,
            "faithful_vlan_applies": self.faithful_vlan_applies,
            "probe_untag": self._probe_untag if self.faithful_vlan_applies else None,
        }

    def global_port(self, port: Any) -> Any:
        return port

    def load_bench_metadata(self, bench_root: str) -> None:
        """ wl_up (AD6_PLAN.md §5.1): unlike wl_ifi's Cisco ACL text (which
        ad6's own parser can't read), wl_up's per-device rulesets ARE literal
        `ip6tables` command text -- confirmed byte-identical to ad6's own
        bundled `ad6/bench/up/*-ruleset` files (AD6_PLAN.md §3.2/§4.1's
        provenance check). So rule CONTENT for these devices is sourced from
        ad6's own proven-at-scale native frontend (`IP6TablesParser`, already
        exact-matched on wl_tum's 3795 rules) instead of hand-translating
        FaVe's already-parsed Match/Action objects into GenUtils calls one
        field at a time -- this is the same "feed ad6 its native format
        directly" principle wl_tum already established, just per-device
        instead of one firewall. Topology/wiring (edges, generator/probe
        attachment, dst-LPM routing) still comes from FaVe's own model via
        the normal add_* dispatch, exactly as for wl_ifi -- only the filter
        CHAINS' content (input/output/forward, everything `-A INPUT ...`
        etc. can express) is sourced from the raw file. Must be called
        before check_compliance(); topology.json's device tuples are
        `[name, type, port_count, address, ruleset_path?]`, where
        `ruleset_path` (like `bench_root` itself) is relative to the process
        cwd (FaVe's `fave/` root -- e.g. "bench/wl_up/rulesets/x-ruleset"),
        exactly like every other benchmark path already used throughout
        this codebase (cwd=fave/ is a standing assumption, not new here). """
        with open(os.path.join(bench_root, 'topology.json')) as raw:
            topology = json.load(raw)
        for entry in topology['devices']:
            name = entry[0]
            dtype = entry[1]
            addr = entry[3] if len(entry) > 3 else None
            ruleset_path = entry[4] if len(entry) > 4 else None
            if dtype == 'switch':
                self._switch_devices.add(name)
            if addr:
                self._device_addr[name] = str(addr)
            if ruleset_path:
                with open(ruleset_path) as rs:
                    self._ruleset_text[name] = rs.read()

    # --- AbstractVerificationEngine: model construction (buffered) ----------

    def add_tables(self, model: Any) -> None:
        self._devices.add(model.node)

    def add_rules(self, model: Any) -> None:
        # AD6_PLAN.md §9: the raw capture the structural path translates. Taken
        # before any interpretation below, and kept even under 'semantic', so
        # the two paths can never be comparing different captures.
        device_tables = self._tables.setdefault(model.node, {})
        for table_name, table_rules in model.tables.items():
            device_tables[table_name] = list(table_rules)

        # AD6_PLAN.md §5.4 Stage B (B0): wl_stanford's device names are
        # "in.<router>"/"mid.<router>"/"out.<router>" -- this stage prefix
        # is the same dispatch key fave/apkeep/adapter.py's own Stanford
        # translator uses. wl_ifi/wl_up devices have no dot-prefixed stage
        # at all, so `stage` is just their own (irrelevant) node name there
        # -- this dispatch is purely additive, no existing behaviour changes.
        stage = model.node.split('.', 1)[0]
        if stage == 'out':
            self._capture_out_perm(model)
            if self._faithful_vlan:
                self._capture_out_reset(model)
        fwd_tables = (model.node + '.routing', model.node + '.1')
        acl_in_t = model.node + '.acl_in'
        acl_out_t = model.node + '.acl_out'
        pre_routing_t = model.node + '.pre_routing'
        for table, rules in model.tables.items():
            if table in fwd_tables:
                for rule in rules:
                    self._translate_fwd_rule(model.node, rule)
                    self._translate_routing_rule(model.node, rule)
                    self._capture_vlan_port(model.node, rule)
                    if stage == 'in':
                        self._capture_in_admit(model.node, rule)
                        if self._faithful_vlan:
                            self._capture_in_admission(model.node, rule)
                    if self._faithful_vlan and stage == 'mid':
                        self._capture_mid_rewrite(model.node, rule)
                    # AD6_PLAN.md §5.5 C4: wl_i2 carries the per-route
                    # egress-VLAN rewrite on its `out.*` dst FIB instead of
                    # a `mid.*` stage (it has none) -- see
                    # _capture_out_rewrite. Harmless on wl_stanford, whose
                    # own out-stage rewrites `_build_ir` scopes back out
                    # again along with the collapsed stage itself.
                    if self._faithful_vlan and stage == 'out':
                        self._capture_out_rewrite(model.node, rule)
            elif table == acl_in_t:
                self._acl_devices.add(model.node)
                self._capture_acl(self._acl_in.setdefault(model.node, {}), rules)
            elif table == acl_out_t:
                self._acl_devices.add(model.node)
                self._capture_acl(self._acl_out.setdefault(model.node, {}), rules)
            elif table == pre_routing_t:
                self._capture_iport_vlan(rules)

    @staticmethod
    def _out_ports(rule: Any) -> List[str]:
        """ The "device.port"(s) a forwarding rule sends matching traffic
        to, from either a router's out_port Rewrite (always single-port --
        no real router-routing benchmark here has ever needed more) or a
        switch's Forward (which CAN be multi-port: wl_stanford's mid.*
        dst-FIB genuinely has ECMP/multipath routes, e.g. `mid.bbra_rtr`
        forwarding one /23 to 15 distinct egress ports simultaneously --
        AD6_PLAN.md §5.4 Stage B). Mirrors `apkeep/adapter.py`'s own plural
        `_out_ports` (which solved the identical problem first). """
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _OUT_PORT:
                        phys = str(field.value)
                        if phys.endswith('_egress'):
                            phys = phys[:-len('_egress')]
                        return [phys]
        for action in rule.actions:
            if isinstance(action, Forward) and action.ports:
                return list(action.ports)
        return []

    def _out_port(self, rule: Any) -> Optional[str]:
        """ Single-port convenience wrapper over _out_ports, for call sites
        (_capture_vlan_port) that only ever need one port and have never
        seen a multi-port rule in practice. """
        ports = self._out_ports(rule)
        return ports[0] if ports else None

    def _translate_fwd_rule(self, device: str, rule: Any) -> None:
        ports = self._out_ports(rule)
        dst = None
        for field in (rule.match or []):
            if field.name in _DSTS:
                dst = str(field.value)
        if not ports:
            # A discard (no forward action). wl_ifi never exercises this
            # (harmless to keep silently dropping). wl_stanford's mid.*
            # stage genuinely does (e.g. a dst=224.0.0.0/3 multicast
            # blackhole, no `fd=` at all) -- and a real blackhole DOES need
            # modelling: leaving no rule at all would let a broader
            # less-specific route (e.g. the device's own /0 default) wrongly
            # claim that traffic instead, an over-approximation. Soundness
            # guard (mirrors apkeep/adapter.py's own): only model this as a
            # dst-only blackhole when the match is genuinely dst(+vlan)-only
            # -- a discard qualified by some other field (src/proto/port)
            # can't be expressed as a dst-only drop without over-dropping,
            # so leave those as a silent no-op, same as before.
            fnames = {f.name for f in (rule.match or [])}
            if dst is None or (fnames - {_DST, _DST6, _VLAN}):
                return
            ports = ["__drop__"]
        # Longest-prefix-match priority -- see _lpm_prio's docstring
        # (AD6_PLAN.md §5.2).
        prio = _lpm_prio(dst)
        self._add_fwd_route(device, dst, ports, prio)

    def _add_fwd_route(self, device: str, dst: Optional[str], ports: List[str], prio: int) -> None:
        """ AD6_PLAN.md §5.4 Stage B: a multi-port route is recorded as ONE
        entry carrying the whole port list -- NOT one entry per port.
        ad6's own table evaluation is sequential first-match
        (KripkeUtils._HandleRule's fallthrough discipline): several
        separate rules sharing the identical dst condition would let only
        the FIRST one ever fire, silently dropping the other ports'
        reachability (see favemodel.py's `wire_fanout`, which gives the
        real OR/multipath semantics at the Kripke-transition level
        instead). Deduped on (device, dst, ports) -- harmless for existing
        benchmarks (never produces duplicates) but real for wl_stanford's
        `in.*` stage, whose per-VLAN admission rules all share one
        identical unconditional default route to the same fixed internal
        port; without this, one entry would be added per admitted VLAN. """
        key = (device, dst, tuple(ports))
        if key in self._fwd_seen:
            return
        self._fwd_seen.add(key)
        self._fwd_rules.append({"device": device, "dst": dst, "ports": ports, "prio": prio})

    def _translate_routing_rule(self, device: str, rule: Any) -> None:
        """ wl_up (AD6_PLAN.md §5.1): a `PacketFilterModel`'s `.routing` table
        picks egress via an `out_port` MATCH field (not a Rewrite action like
        a wl_ifi router's `.routing`/`.1` table -- see `_translate_fwd_rule`,
        which is a silent no-op here since these rules carry no Rewrite).
        Mirrors `apkeep/adapter.py:_translate_fib_rule`'s reading of the same
        shape: a match-with-out_port-but-no-Forward-action entry is an
        internal placeholder (a "route unknown" discard, or a connected-route
        marker), not a real route -- only a rule that actually forwards
        counts. """
        dst = None
        port = None
        for field in (rule.match or []):
            if field.name in _DSTS:
                dst = str(field.value)
            elif field.name == _OUT_PORT:
                port = str(field.value)
        if port is None:
            return
        has_fwd = any(isinstance(a, Forward) for a in (rule.actions or []))
        if not has_fwd:
            return
        if port.endswith('_egress'):
            port = port[:-len('_egress')]
        # Longest-prefix-match priority -- see _lpm_prio's docstring
        # (AD6_PLAN.md §5.2).
        prio = _lpm_prio(dst)
        self._routing_rules.append({"device": device, "dst": dst, "port": port, "prio": prio})

    def _capture_vlan_port(self, device: str, rule: Any) -> None:
        """ A routing rule that rewrites the egress VLAN records VLAN->egress
        port (per device, AD6_PLAN.md §5.4 Stage 0 -- see __init__'s
        `_vlan_to_eport` docstring), so acl_out groups (keyed by device then
        VLAN) can be traced to a port. """
        vlan = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan = str(field.value)
        if vlan is None:
            return
        port = self._out_port(rule)
        if port:
            self._vlan_to_eport.setdefault(device, {})[vlan] = port

    def _capture_in_admit(self, device: str, rule: Any) -> None:
        """ AD6_PLAN.md §5.4 Stage B (B0): record which physical ingress
        ports an `in.*` device admits -- direct port of
        `apkeep/adapter.py:_capture_in_admit`. wl_stanford's in-stage rules
        are in-port-qualified (each lists the ingress ports it permits for
        a VLAN, ignored here -- B0 has no VLAN modelling at all, only
        WHICH ports have any admission rule); the union over all rules is
        the set of ports the router accepts traffic on. A rule with no
        in-port qualifies every port, marking the device admit-all
        (`None` -- never gated). """
        cur = self._in_admit.get(device, set())
        if cur is None:
            return
        if not rule.in_ports:
            self._in_admit[device] = None
            return
        for port in rule.in_ports:
            cur.add(_split_port(port)[1])
        self._in_admit[device] = cur

    def _capture_out_perm(self, model: Any) -> None:
        """ AD6_PLAN.md §5.4 Stage B (B0): wl_stanford's `out.*` stage maps
        an input port (fed by a `mid.*` egress interface) to a physical
        output port, possibly under a VLAN match/rewrite (irrelevant to
        B0's plain port permutation) -- direct port of
        `apkeep/adapter.py:_capture_out_perm`. """
        perm = self._out_perm.setdefault(model.node, {})
        for _table, rules in model.tables.items():
            for rule in rules:
                out_ports = self._out_ports(rule)
                if not out_ports or not rule.in_ports:
                    continue  # a drop (empty action) or a rule with no in port
                in_port = _split_port(rule.in_ports[0])[1]
                perm.setdefault(in_port, set()).update(
                    _split_port(p)[1] for p in out_ports
                )

    def _collapse_out_stage(self, edges: List[List[str]]) -> List[List[str]]:
        """ AD6_PLAN.md §5.4 Stage B (B0): remove wl_stanford's `out.*`
        stage, splicing its port permutation into the topology directly --
        ported (not imported) from `apkeep/adapter.py:_collapse_out_stage`,
        whose algorithm operates purely on the edge list so it transfers
        directly onto Ad6Adapter's own `[sport, dport]` edge shape. The
        physical path is `mid.X.<port> -> out.X.<in_port>` (internal link)
        -> `out.X.<out_port>` (permutation rule, `_capture_out_perm`) ->
        `in.Y.<port>` / probe (external link). ad6's dst-based forwarding
        table cannot honour an in-port permutation (there is no dst
        condition to key it on at all), so this resolves the chain
        statically and wires the `mid.*` egress interface straight to the
        external neighbour(s), dropping `out.*` entirely. """
        mid_to_out: Dict[Tuple[str, str], Tuple[str, str]] = {}
        out_ext: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
        kept: List[List[str]] = []
        for sport, dport in edges:
            s_dev, s_port = _split_port(sport)
            d_dev, d_port = _split_port(dport)
            if d_dev.split('.', 1)[0] == 'out':          # mid.X -> out.X (internal)
                mid_to_out[(d_dev, d_port)] = (s_dev, s_port)
            elif s_dev.split('.', 1)[0] == 'out':          # out.X -> in.Y/probe (external)
                out_ext.setdefault((s_dev, s_port), []).append((d_dev, d_port))
            else:
                kept.append([sport, dport])
        for out_dev, perm in self._out_perm.items():
            for in_port, out_ports in perm.items():
                mid = mid_to_out.get((out_dev, in_port))
                if mid is None:
                    continue
                m_dev, m_port = mid
                for out_port in out_ports:
                    for d_dev, d_port in out_ext.get((out_dev, out_port), []):
                        kept.append(["%s.%s" % (m_dev, m_port), "%s.%s" % (d_dev, d_port)])
        return kept

    def _capture_iport_vlan(self, rules: Any) -> None:
        """ pre_routing assigns an ingress VLAN per physical ingress port
        (e.g. the Internet/transit port). """
        for rule in rules:
            if not rule.in_ports:
                continue
            port = "%s.%s" % _split_port(rule.in_ports[0])
            for action in rule.actions:
                if isinstance(action, Rewrite):
                    for field in action.rewrite:
                        if field.name == _VLAN:
                            self._iport_vlan[port] = str(field.value)

    def _capture_mid_rewrite(self, node: str, rule: Any) -> None:
        """ AD6_PLAN.md §5.4 Stage B (B2), faithful_vlan only: a mid-stage
        rule forwards a dst-IP prefix to an egress port and rewrites the
        egress VLAN (rw=vlan:N). Record (dst_cidr, egress_port, N) so
        favemodel.py can emit it as a real ad6 rewrite action
        (GenUtils.action(..., rewrite_field='vlan', rewrite_value=N),
        AD6_PLAN.md §5.4 Stage A). Direct port of
        apkeep/adapter.py:_capture_mid_rewrite -- including its own
        simplification of recording only the FIRST egress port for a
        multi-port (ECMP) route (a Rewrite applies to the packet
        regardless of which egress branch it takes, so this only affects
        which out.X in_port _fold_mid_rewrites folds the reset against;
        kept identical to APKeep's own capture for direct comparability,
        not "fixed" here, since real Stanford data has not been observed
        to combine ECMP with a VLAN rewrite on the same route). """
        vlan_n = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan_n = str(field.value)
        if vlan_n is None:
            return
        ports = self._out_ports(rule)
        if not ports:
            return
        dst = None
        for field in (rule.match or []):
            if field.name in _DSTS:
                dst = str(field.value)
        self._mid_rw.setdefault(node, []).append((dst, ports[0], vlan_n))

    def _capture_out_rewrite(self, node: str, rule: Any) -> None:
        """ AD6_PLAN.md §5.5 C4, faithful_vlan only: an out-stage rule
        matches a dst-IP prefix, forwards to an egress port, AND rewrites
        the egress VLAN (rw=vlan:M). Record (dst_cidr, egress_port, M) so
        favemodel.py can emit it as a real ad6 rewrite action
        (GenUtils.action(..., rewrite_field='vlan', rewrite_value=M),
        AD6_PLAN.md §5.4 Stage A) on that route's own jump.

        This is wl_i2's shape and the gap §5.5's WORKLOAD-PARITY FINDING
        identified: all 77,451 of i2's real `out.X` rules match `ipv4_dst`
        and carry exactly two actions, `rw=vlan:M` plus one `fd=`, and
        before this method existed every one of those rewrites was dropped
        in BOTH modes -- so `faithful_vlan=True` produced in-stage
        admission gating on a VLAN that nothing ever assigned (an
        incoherent model, not a faithful one) rather than the joint
        (dst x VLAN) coupling NetPlumber and the faithful NDD run both
        answer.

        Deliberately a separate method and a separate IR field from
        `_capture_mid_rewrite`/`_mid_rw`, not a widened stage filter on
        those: wl_stanford puts the rewrite on `mid.X` and its `out.X` is a
        pure port permutation that `_build_ir` COLLAPSES (folding the
        out-stage's `rw=vlan:0` resets into the mid rewrite via
        `_fold_mid_rewrites`), whereas wl_i2 has no `mid` stage at all and
        its `out.X` survives as the dst FIB. Merging the two would make one
        field mean different things depending on which benchmark built it.

        Direct port of `apkeep/adapter.py:_capture_out_rewrite`, keeping the
        same accepted narrowing its own docstring records (only the FIRST
        egress port of a multi-port route -- a Rewrite applies to the packet
        whichever ECMP branch fires, and real i2 data never combines the
        two: all 77,451 out rules carry exactly one `fd=`), for the direct
        cross-backend comparability §5.4 Stage B asks for. """
        vlan_m = None
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _VLAN:
                        vlan_m = str(field.value)
        if vlan_m is None:
            return
        ports = self._out_ports(rule)
        if not ports:
            return
        dst = None
        for field in (rule.match or []):
            if field.name in _DSTS:
                dst = str(field.value)
        self._out_rw.setdefault(node, []).append((dst, ports[0], vlan_m))

    def _capture_out_reset(self, model: Any) -> None:
        """ AD6_PLAN.md §5.4 Stage B (B2), faithful_vlan only: the out-stage
        mostly passes the mid-assigned VLAN through, but a few rules reset
        it to 0 (rw=vlan:0) -- probes require vlan=0. Record the (in_port,
        vlan) pairs that reset, so _fold_mid_rewrites can fold the reset
        into the effective egress VLAN for the mid.X routes that feed
        them. Direct port of apkeep/adapter.py:_capture_out_reset. """
        reset = self._out_reset.setdefault(model.node, set())
        for _table, rules in model.tables.items():
            for rule in rules:
                resets = any(
                    isinstance(a, Rewrite)
                    and any(f.name == _VLAN and str(f.value) == '0' for f in a.rewrite)
                    for a in rule.actions
                )
                if not resets or not rule.in_ports:
                    continue
                in_port = _split_port(rule.in_ports[0])[1]
                for field in (rule.match or []):
                    if field.name == _VLAN:
                        reset.add((in_port, str(field.value)))

    def _capture_in_admission(self, node: str, rule: Any) -> None:
        """ AD6_PLAN.md §5.5, faithful_vlan only: an in-stage rule admits
        (permits, forwards on) traffic arriving on a given ingress VLAN, on
        the specific physical PORT(S) its `in_ports` names. Records the
        per-(port, VLAN) relation those rules actually express.

        This used to record only the per-DEVICE union of admitted VLANs,
        checked once at that device's own already-collapsed dst=None
        forwarding entry -- mirroring apkeep/adapter.py's own
        single-check-at-the-collapsed-junction simplification, deliberately,
        for direct comparability with APKeep's faithful-VLAN result
        (AD6_PLAN.md §5.4 Stage B). That projection is not sound: dropping
        the port makes the gate strictly weaker, and it is weaker on EVERY
        real port of both workloads -- 223/223 on wl_i2 and 252/252 on
        wl_stanford have a per-port set strictly narrower than their
        device's union. On wl_i2 it admitted 2,555 of the 2,564 crossings a
        per-port configuration rejects (99.6%), which is what made ad6
        report `source.chic` reaching salt/seat where NetPlumber has the
        flow correctly die at `in.kans`/`in.hous` (AD6_PLAN.md §5.5, "STEP
        (c) DONE"). NOTE that apkeep/adapter.py's own `_in_vlans` still has
        the unfixed projection -- see TODO.md.

        A rule naming no `in_ports` at all admits its VLAN on every port of
        the device; it is recorded under `_ANY_PORT` rather than dropped,
        and favemodel._port_scoped_admission falls the whole device back to
        the device-wide gate when it sees one (under-approximating a
        port-agnostic rule would turn an over-approximation into a false
        UNSAT, which is worse). Neither shipped benchmark has one: all
        2,265 wl_stanford and all 390 wl_i2 in-stage rules name their
        ports. Diverges from apkeep/adapter.py:_capture_in_admission,
        which is still a direct-port of the projected version. """
        if not any(isinstance(a, Forward) and a.ports for a in rule.actions):
            return  # a drop (no forward) -- not an admission
        vlans = {
            str(field.value) for field in (rule.match or [])
            if field.name == _VLAN
        }
        if not vlans:
            return
        ports = [_split_port(p)[1] for p in (rule.in_ports or [])] or [_ANY_PORT]
        per_port = self._in_vlans.setdefault(node, {})
        for port in ports:
            per_port.setdefault(port, set()).update(vlans)

    def _fold_mid_rewrites(self) -> Dict[str, List[List[Any]]]:
        """ AD6_PLAN.md §5.4 Stage B (B2): port of
        apkeep/adapter.py:_build_stanford_faithful's VLAN-rewrite folding --
        the EFFECTIVE egress VLAN of a mid.X route is 0 iff the (already-
        collapsed-away, AD6_PLAN.md §5.4 Stage B0) out.X stage resets it
        for that specific (in_port, vlan) pair (probes require vlan=0),
        else the mid-assigned VLAN N propagates on unchanged as the
        transit tag. Needs the SAME mid.X-egress-port -> out.X-in-port
        mapping `_collapse_out_stage` derives from the RAW (pre-collapse)
        edges -- by the time favemodel.py sees the IR's own "edges" list,
        the out.* stage is already gone, so this must be computed here,
        from `self._edges`, before that collapse discards the information.
        Returns {mid_device: [[dst, egress_port, effective_vlan], ...]}
        (JSON-serialisable: lists, not tuples/sets, since this feeds
        straight into `_build_ir`'s payload). """
        mid_port_to_outin: Dict[Tuple[str, str], str] = {}
        for sport, dport in self._edges:
            s_dev, s_port = _split_port(sport)
            d_dev, d_port = _split_port(dport)
            if d_dev.split('.', 1)[0] == 'out':
                mid_port_to_outin[(s_dev, s_port)] = d_port
        folded: Dict[str, List[List[Any]]] = {}
        for mid_dev, rewrites in self._mid_rw.items():
            router = mid_dev.split('.', 1)[1]
            reset = self._out_reset.get('out.' + router, set())
            for dst, egress_port, vlan_n in rewrites:
                # `egress_port` here is the FULL "device.port" string
                # ad6's own `_out_ports`/`_capture_mid_rewrite` convention
                # uses (unlike apkeep/adapter.py's `_out_ports`, which
                # pre-splits to a bare port number) -- `mid_port_to_outin`
                # above is keyed the same way `self._edges` already is
                # (device, bare-port), via `_split_port`, so the lookup
                # key must be split the same way, or every lookup misses
                # silently (found test-first: a hand-built fixture with a
                # real matching reset pair still returned the un-folded
                # vlan, `test_ad6_wl_stanford_faithful.py::
                # TestAd6StanfordFoldMidRewrites::
                # test_reset_pair_folds_effective_vlan_to_zero`).
                out_inport = mid_port_to_outin.get((mid_dev, _split_port(egress_port)[1]))
                effective = '0' if (
                    out_inport is not None and (out_inport, vlan_n) in reset
                ) else vlan_n
                folded.setdefault(mid_dev, []).append([dst, egress_port, effective])
        return folded

    @staticmethod
    def _capture_acl(store: Dict[Optional[str], List[List[Any]]], rules: Any) -> None:
        """ Group FaVe ACL rules by their VLAN match into
        [idx, permit, src, dst, related] entries. permit == forwards
        somewhere; related is the connection-state match ("0"/"1"/None), see
        _RELATED -- carried through so favemodel.py can emit the matching
        ad6 <state> condition (AD6_PLAN.md §4.2). """
        for rule in rules:
            vlan = src = dst = related = None
            for field in (rule.match or []):
                if field.name == _VLAN:
                    vlan = str(field.value)
                elif field.name == _SRC:
                    src = field.value
                elif field.name == _DST:
                    dst = field.value
                elif field.name == _RELATED:
                    related = str(field.value)
            permit = any(isinstance(a, Forward) and a.ports for a in rule.actions)
            store.setdefault(vlan, []).append([rule.idx, permit, src, dst, related])

    def add_wiring(self, model: Any) -> None:
        """ FaVe DECLARES each device's internal pipeline as unidirectional
        port-to-port links (AbstractDevice.wiring). The semantic path ignores
        it and rebuilds an approximation by recognising table-name suffixes;
        the structural path uses the declaration. Captured unconditionally so
        both paths see one capture (AD6_PLAN.md §9.8.2). """
        pairs = getattr(model, 'wiring', None) or []
        if pairs:
            self._wiring.setdefault(model.node, []).extend(
                [list(pair) for pair in pairs])

    def add_link(self, sport: str, dport: str) -> None:
        # UNNORMALISED, for the structural path: the normalisation below strips
        # the "_ingress"/"_egress" suffix that names which interface a port is.
        self._raw_edges.append([sport, dport])
        # Normalise router "_ingress"/"_egress"-suffixed endpoints (see
        # _split_port) so every consumer of self._edges (and the IR it feeds
        # to the ad6 bridge) sees plain "device.port" throughout.
        self._edges.append(["%s.%s" % _split_port(sport), "%s.%s" % _split_port(dport)])

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
                elif fname == _VLAN:
                    self._gen_vlan[model.node] = str(rfields[0].value)

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        for model in models:
            self.add_generator(model)

    def add_probe(self, model: Any) -> None:
        """ AD6_PLAN.md §5.5 C4 (part 2): additionally record the arrival
        VLAN the probe's model declares, which this used to drop entirely.

        Read from `test_fields`, NOT `filter_fields`. The two are different
        FaVe mechanisms -- `filter_fields` narrows which flows the probe
        considers at all, `test_fields` is the condition it TESTS on the
        flows that arrive -- and it is the latter that states "a flow only
        counts as delivered here if its VLAN is 0". Confirmed against the
        real model rather than inferred: instrumenting an
        `InProcessFaVe.replay` of `bench/wl_i2/i2-json` shows every probe
        arriving with `test_fields={'packet.ether.vlan': ['0']}` and BOTH
        `filter_fields` and `match` empty, so reading either of those would
        have silently captured nothing. wl_stanford's probes declare the
        same condition the same way; every other benchmark's declare no
        VLAN and record nothing here. """
        self._probes[model.node] = model.node + '.1'
        for field in (getattr(model, 'test_fields', None) or {}).get(_VLAN, []):
            self._probe_vlan[model.node] = str(field.value)

    # --- ingress port tracing (mirrors APKeepAdapter._splice_acls) ----------

    def _ingress_port(self, source: str) -> Optional[str]:
        """ source -> (switch or router) -> router port, as "device.port"
        (suffix-stripped -- router-facing edge endpoints carry an
        "_ingress"/"_egress" suffix at dispatch time, see _split_port). """
        nxt = None
        for sport, dport in self._edges:
            if sport.rsplit('.', 1)[0] == source:
                nxt = dport
                break
        if nxt is None:
            return None
        ndev, nport = _split_port(nxt)
        if ndev in self._acl_devices:
            return "%s.%s" % (ndev, nport)
        for sport, dport in self._edges:
            if (sport.rsplit('.', 1)[0] == ndev
                    and _split_port(dport)[0] in self._acl_devices):
                return "%s.%s" % _split_port(dport)
        return None

    def _build_ir(self) -> Dict[str, Any]:
        # AD6_PLAN.md §5.4 Stage B (B0): wl_stanford (and only it) has a
        # `mid.*` stage; its `out.*` stage is a port permutation to
        # collapse, exactly like `apkeep/adapter.py:_build`'s own detection
        # (`any(d.split('.',1)[0]=='mid' ...)` -- there is no other flag
        # distinguishing this benchmark from wl_ifi/wl_up).
        devices = set(self._devices)
        edges = list(self._edges)
        if any(d.split('.', 1)[0] == 'mid' for d in devices):
            devices = {d for d in devices if d.split('.', 1)[0] != 'out'}
            edges = self._collapse_out_stage(edges)

        in_port_vlan: Dict[str, str] = {}
        for port, vlan in self._iport_vlan.items():
            device = port.rsplit('.', 1)[0]
            if vlan in self._acl_in.get(device, {}):
                in_port_vlan[port] = vlan
        for source, vlan in self._gen_vlan.items():
            port = self._ingress_port(source)
            if port is None:
                continue
            device = port.rsplit('.', 1)[0]
            if vlan in self._acl_in.get(device, {}):
                in_port_vlan[port] = vlan
        out_port_vlan: Dict[str, str] = {
            port: vlan
            for device, vlan_map in self._vlan_to_eport.items()
            for vlan, port in vlan_map.items()
            if vlan in self._acl_out.get(device, {})
        }
        ir = {
            "devices": sorted(devices),
            "fwd_rules": self._fwd_rules,
            "routing_rules": self._routing_rules,
            "edges": edges,
            "generators": self._generators,
            "probes": self._probes,
            "acl_devices": sorted(self._acl_devices),
            "acl_in": self._acl_in,
            "acl_out": self._acl_out,
            "in_port_vlan": in_port_vlan,
            "out_port_vlan": out_port_vlan,
            "in_admit": {
                device: (sorted(ports) if ports is not None else None)
                for device, ports in self._in_admit.items()
            },
            "ruleset_devices": self._ruleset_text,
            "device_addr": self._device_addr,
        }
        # AD6_PLAN.md §5.4 Stage B (B2): only emitted in faithful_vlan mode --
        # every existing (plain) benchmark's IR payload is byte-for-byte
        # unaffected, since favemodel.py gates all faithful-VLAN wiring on
        # ir["faithful_vlan"] being truthy.
        if self._faithful_vlan:
            ir["faithful_vlan"] = True
            ir["mid_rw"] = self._fold_mid_rewrites()
            # AD6_PLAN.md §5.5 C4: wl_i2's out-stage rewrites, scoped to the
            # devices that SURVIVE the collapse above. On wl_stanford every
            # `out.*` device is collapsed away and its resets are already
            # folded into `mid_rw`, so this is {} there -- publishing those
            # same rewrites again would be double-counting a rewrite no
            # surviving device carries. Unfolded, unlike `mid_rw`: i2's out
            # stage IS the surviving FIB, so there is no downstream stage
            # whose reset would need folding in (and `_capture_out_reset`
            # records nothing on i2 anyway -- its out rules carry no VLAN
            # match to key a reset on).
            ir["out_rw"] = {
                device: [list(entry) for entry in entries]
                for device, entries in self._out_rw.items()
                if device in devices
            }
            # AD6_PLAN.md §5.5 C4 (part 2): what the probes DECLARE is always
            # reported; whether it is ENFORCED is the separate opt-in below,
            # so a reader of an IR (or of a result stamped with it) can tell
            # the two apart instead of inferring enforcement from presence.
            ir["probe_vlan"] = dict(self._probe_vlan)
            if self._probe_untag:
                ir["probe_untag"] = True
            # AD6_PLAN.md §5.5: the per-(port, VLAN) relation, NOT a
            # per-device union -- {device: {port: [vlans]}}. favemodel.py
            # (_in_vlans_for) also still reads the old flat {device: [vlans]}
            # shape, so an ARCHIVED IR keeps building the encoding it was
            # measured against; nothing emits that shape any more.
            ir["in_vlans"] = {
                device: {
                    port: sorted(vlans, key=int)
                    for port, vlans in sorted(per_port.items())
                }
                for device, per_port in self._in_vlans.items()
            }
            ir["gen_vlan"] = dict(self._gen_vlan)
        return ir

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
        """ AD6_PLAN.md §9: the structural payload -- ad6 config XML plus the
        Kripke edges XML cannot express, plus each source's and probe's own
        query node.

        Translation happens HERE, in FaVe's process, rather than in the bridge,
        because `translate.py` needs both vocabularies at once: ad6's GenUtils
        to emit, and FaVe's own `rule_model` classes to read. Only the finished
        XML crosses the subprocess boundary, so the bridge still needs nothing
        from FaVe. (The adapter's own no-ad6-imports discipline is not weakened:
        `translate` is imported inside this method, so a 'semantic' run never
        touches ad6's package tree at all.) """
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
            # Derived from what was emitted, not from faithful_vlan: the
            # structural path emits a <fieldmatch> whenever some rule rewrites
            # the field, which on wl_ifi is true in plain mode too.
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
        payload = {"ir": self._build_ir(), "queries": queries,
                   "grounding": self.grounding,
                   "translation": self.translation}
        if self.translation == TRANSLATION_STRUCTURAL:
            payload["structural"] = self._build_structural()
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
