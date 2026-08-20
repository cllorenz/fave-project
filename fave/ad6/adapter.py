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
_VLAN = 'packet.ether.vlan'
_OUT_PORT = 'out_port'

_HERE = os.path.dirname(os.path.abspath(__file__))         # .../fave/ad6
_FAVE = os.path.dirname(_HERE)                              # .../fave
AD6_ROOT = os.path.normpath(os.path.join(_FAVE, '..', 'ad6'))
BRIDGE = os.path.join(AD6_ROOT, 'fave_bridge.py')


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

    def __init__(self, logger: TraceLogger) -> None:
        self.logger = logger
        self._devices: set = set()
        self._fwd_rules: List[Dict[str, Any]] = []   # [{device,dst,port,prio}]
        self._edges: List[List[str]] = []             # [[sport,dport], ...]
        self._generators: Dict[str, str] = {}          # name -> "device.port"
        self._probes: Dict[str, str] = {}              # name -> "device.port"
        self._gen_src: Dict[str, str] = {}              # name -> cidr
        self._gen_vlan: Dict[str, str] = {}              # name -> vlan
        self._acl_device: Optional[str] = None
        self._acl_in: Dict[Optional[str], List[List[Any]]] = {}   # vlan -> [[idx,permit,src,dst]]
        self._acl_out: Dict[Optional[str], List[List[Any]]] = {}
        self._vlan_to_eport: Dict[str, str] = {}          # vlan -> "device.port"
        self._iport_vlan: Dict[str, str] = {}             # "device.port" -> vlan
        self._results: List[Tuple[str, str, bool, str]] = []
        # Surface the aggregator dispatch touches, like APKeepAdapter.
        self.links: Dict[Any, List[Any]] = {}
        self.asyncore_socks: Dict[Any, Any] = {}

    def global_port(self, port: Any) -> Any:
        return port

    # --- AbstractVerificationEngine: model construction (buffered) ----------

    def add_tables(self, model: Any) -> None:
        self._devices.add(model.node)

    def add_rules(self, model: Any) -> None:
        fwd_tables = (model.node + '.routing', model.node + '.1')
        acl_in_t = model.node + '.acl_in'
        acl_out_t = model.node + '.acl_out'
        pre_routing_t = model.node + '.pre_routing'
        for table, rules in model.tables.items():
            if table in fwd_tables:
                for rule in rules:
                    self._translate_fwd_rule(model.node, rule)
                    self._capture_vlan_port(rule)
            elif table == acl_in_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_in, rules)
            elif table == acl_out_t:
                self._acl_device = model.node
                self._capture_acl(self._acl_out, rules)
            elif table == pre_routing_t:
                self._capture_iport_vlan(rules)

    @staticmethod
    def _out_port(rule: Any) -> Optional[str]:
        """ The single "device.port" a forwarding rule sends matching traffic
        to, from either a router's out_port Rewrite or a switch's Forward. """
        for action in rule.actions:
            if isinstance(action, Rewrite):
                for field in action.rewrite:
                    if field.name == _OUT_PORT:
                        phys = str(field.value)
                        if phys.endswith('_egress'):
                            phys = phys[:-len('_egress')]
                        return phys
        for action in rule.actions:
            if isinstance(action, Forward) and action.ports:
                return action.ports[0]
        return None

    def _translate_fwd_rule(self, device: str, rule: Any) -> None:
        port = self._out_port(rule)
        if port is None:
            return  # a discard (no forward action) -- out of scope for wl_ifi
        dst = None
        for field in (rule.match or []):
            if field.name == _DST:
                dst = str(field.value)
        # ad6's table is sequential first-match (ascending prio = evaluated
        # first), unlike APKeep's priority-wins ForwardElement -- so a
        # dst-specific route must sort BEFORE the no-dst default, not by
        # prefix length. wl_ifi has no two routes on the same device with
        # different-length overlapping prefixes, so "specific before
        # default" is exact (not an approximation of true LPM).
        prio = 65535 if dst is None else 0
        self._fwd_rules.append({"device": device, "dst": dst, "port": port, "prio": prio})

    def _capture_vlan_port(self, rule: Any) -> None:
        """ A routing rule that rewrites the egress VLAN records VLAN->egress
        port, so acl_out groups (keyed by VLAN) can be traced to a port. """
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
            self._vlan_to_eport[vlan] = port

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

    @staticmethod
    def _capture_acl(store: Dict[Optional[str], List[List[Any]]], rules: Any) -> None:
        """ Group FaVe ACL rules by their VLAN match into
        [idx, permit, src, dst] entries. permit == forwards somewhere. """
        for rule in rules:
            vlan = src = dst = None
            for field in (rule.match or []):
                if field.name == _VLAN:
                    vlan = str(field.value)
                elif field.name == _SRC:
                    src = field.value
                elif field.name == _DST:
                    dst = field.value
            permit = any(isinstance(a, Forward) and a.ports for a in rule.actions)
            store.setdefault(vlan, []).append([rule.idx, permit, src, dst])

    def add_wiring(self, model: Any) -> None:
        pass  # internal device pipeline plumbing; not needed for a flat dst-IP model

    def add_link(self, sport: str, dport: str) -> None:
        # Normalise router "_ingress"/"_egress"-suffixed endpoints (see
        # _split_port) so every consumer of self._edges (and the IR it feeds
        # to the ad6 bridge) sees plain "device.port" throughout.
        self._edges.append(["%s.%s" % _split_port(sport), "%s.%s" % _split_port(dport)])

    def add_links_bulk(self, links: Any, use_dynamic: bool = False) -> None:
        for sport, dport in links:
            self.add_link(sport, dport)

    def add_generator(self, model: Any) -> None:
        self._generators[model.node] = model.node + '.1'
        fields = getattr(model, 'fields', None)
        if fields:
            for fname, rfields in fields.items():
                if not rfields:
                    continue
                if fname == _SRC:
                    self._gen_src[model.node] = str(rfields[0].value)
                elif fname == _VLAN:
                    self._gen_vlan[model.node] = str(rfields[0].value)

    def add_generators_bulk(self, models: Any, use_dynamic: bool = False) -> None:
        for model in models:
            self.add_generator(model)

    def add_probe(self, model: Any) -> None:
        self._probes[model.node] = model.node + '.1'

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
        if ndev == self._acl_device:
            return "%s.%s" % (ndev, nport)
        for sport, dport in self._edges:
            if (sport.rsplit('.', 1)[0] == ndev
                    and _split_port(dport)[0] == self._acl_device):
                return "%s.%s" % _split_port(dport)
        return None

    def _build_ir(self) -> Dict[str, Any]:
        in_port_vlan: Dict[str, str] = {
            port: vlan for port, vlan in self._iport_vlan.items()
            if vlan in self._acl_in
        }
        for source, vlan in self._gen_vlan.items():
            if vlan in self._acl_in:
                port = self._ingress_port(source)
                if port is not None:
                    in_port_vlan[port] = vlan
        out_port_vlan: Dict[str, str] = {
            port: vlan for vlan, port in self._vlan_to_eport.items()
            if vlan in self._acl_out
        }
        return {
            "devices": sorted(self._devices),
            "fwd_rules": self._fwd_rules,
            "edges": self._edges,
            "generators": self._generators,
            "probes": self._probes,
            "acl_device": self._acl_device,
            "acl_in": self._acl_in,
            "acl_out": self._acl_out,
            "in_port_vlan": in_port_vlan,
            "out_port_vlan": out_port_vlan,
        }

    # --- build + query --------------------------------------------------

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
                    "negated": bool(negated), "cond": cond,
                })
        payload = {"ir": self._build_ir(), "queries": queries}
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
