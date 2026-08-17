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

""" In-process driver for the APKeep verifier (apkeep/ subtree) via JPype.

This embeds a *resident* JVM in the Python process (started once; JPype's JVM is
process-global and cannot be restarted) and drives APKeep's Java classes
directly -- no subprocess, no socket. It is the APKeep counterpart of
netplumber/lib_adapter.py's libnetplumber binding (see APKEEP_BACKEND.md, P2),
and the resident JVM is what the from-zero comparison needs (warm JVM, no
per-run boot).

Requires JDK 11 + the built APKeep fat jar (apkeep/target/apkeep-1.0.0.jar;
`mvn -C apkeep package`). `available()` reports whether both are present so
callers/tests can skip cleanly.

Scope (P2): resident JVM + in-memory rule add (run a Python list of rule
strings, not a file APKeep parses) + result retrieval. Network construction
currently uses APKeep's own snapshot loader (init_snapshot); building the
network from a FaVe model in-memory is P4. The reachability solver is P3.
"""

from __future__ import annotations

import os
import tempfile as _tempfile

from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_APKEEP_JAR = os.path.join(_REPO_ROOT, "apkeep", "target", "apkeep-1.0.0.jar")

try:
    import jpype
    import jpype.imports  # noqa: F401  (enables `from java... import ...`)
except ImportError:  # pragma: no cover - JPype not installed
    jpype = None  # type: ignore


def available() -> bool:
    """ True iff JPype is importable and the APKeep jar is built. """
    return jpype is not None and os.path.isfile(_APKEEP_JAR)


def _ensure_jvm() -> None:
    """ Start the resident JVM once (idempotent). """
    if jpype is None:
        raise RuntimeError("JPype is not installed (pip install JPype1)")
    if not os.path.isfile(_APKEEP_JAR):
        raise RuntimeError(
            "APKeep jar not built: %s (run `mvn -C apkeep package`)" % _APKEEP_JAR
        )
    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=[_APKEEP_JAR])


class LibAPKeep:
    """ Resident-JVM, in-process handle to a single APKeep network.

    APKeep keeps its network/evaluator in static fields, so one LibAPKeep
    instance maps to one network per process.
    """

    def __init__(self) -> None:
        _ensure_jvm()
        self._APKeep = jpype.JClass("apkeep.main.APKeep")
        self._Network = jpype.JClass("apkeep.core.Network")
        self._Evaluator = jpype.JClass("apkeep.utils.Evaluator")
        self._ArrayList = jpype.JClass("java.util.ArrayList")
        self._ReachabilityChecker = jpype.JClass("apkeep.checker.ReachabilityChecker")
        self._PositionTuple = jpype.JClass("common.PositionTuple")
        self._APKeeper = jpype.JClass("apkeep.core.APKeeper")
        self._net: Any = None
        self._eva: Any = None

    def init_snapshot(self, snapshot_dir: str) -> None:
        """ Build the network from an APKeep snapshot directory (topo/acls/vlan/
        parameters), via APKeep's own file loader. """
        self._APKeep.init(snapshot_dir)
        self._net = self._APKeep.net
        self._eva = self._APKeep.eva

    def init_in_memory(self, name: str, l1_links: List[str],
                       fwd_devices: Optional[List[str]] = None,
                       device_acls: Optional[Dict[str, List[str]]] = None,
                       device_nats: Optional[Dict[str, List[str]]] = None,
                       device_filters: Optional[List[str]] = None,
                       bdd_table_size: int = 1_000_000) -> None:
        """ Build the network from IN-MEMORY collections (no snapshot files):
        the path the APKeepAdapter uses to construct an APKeep network from a
        FaVe model (APKEEP_BACKEND.md, P4/P7b).

        l1_links    -- directed topology edges as "dev1 port1 dev2 port2" strings
        fwd_devices -- ForwardElement device names not already implied by a link
        device_acls -- {device: [acl_name, ...]} -> ACLElements "device_aclname"
                       (None when there are no ACLs)
        device_nats -- {device: [port, ...]} -> a NATElement "device_port" inserted
                       inline on device.port (rewrites, e.g. VLAN; see P7b). Its
                       "+ nat <device> <port> vlan <dstIP> <dstlen> <vlanN>" rules
                       go through run(). None when there are no rewrites.

        Bypasses APKeep's name-dependent file parsers (readACLs/readVlans), so
        the collections must already be in APKeep's internal shape.
        """
        links = self._ArrayList()
        for edge in l1_links:
            links.add(str(edge))
        devices = self._ArrayList()
        for dev in (fwd_devices or []):
            devices.add(str(dev))

        def _str_set_map(mapping: Optional[Dict[str, List[str]]]) -> Any:
            if not mapping:
                return None
            HashMap = jpype.JClass("java.util.HashMap")
            HashSet = jpype.JClass("java.util.HashSet")
            jmap = HashMap()
            for dev, names in mapping.items():
                names_set = HashSet()
                for n in names:
                    names_set.add(str(n))
                jmap.put(str(dev), names_set)
            return jmap

        acls_map = _str_set_map(device_acls)
        nats_map = _str_set_map(device_nats)

        # device_filters: packet-filter devices modelled by a FilterElement
        # (multi-field first-match forward_filter) instead of a dst-IP FIB.
        filters_set = None
        if device_filters:
            HashSet = jpype.JClass("java.util.HashSet")
            filters_set = HashSet()
            for dev in device_filters:
                filters_set.add(str(dev))

        # Size the BDD table for a FaVe-scale network (not APKeep's 100M
        # snapshot default), so several in-process networks can coexist under
        # the resident JVM without exhausting it.
        params = jpype.JClass("apkeep.utils.Parameters")
        params.BDD_TABLE_SIZE = int(bdd_table_size)
        # AP merging stays ON with NATs now that the multi-rule-NAT merge crash is
        # fixed (stale-AP guards in APKeeper.tryMergeAP / Element.updatePortPredicateMap);
        # merging is what keeps the atomic-predicate count (and memory) bounded at
        # scale, so faithful wl_stanford no longer OOMs (P7b).
        # With VLAN rewrites (NATs), ACLs must share the forwarding AP universe so
        # a VLAN admission composes with the rewrite -- ACL "division" would put
        # them in separate universes that disagree on the rewritten VLAN. Keep
        # division for the NAT-free src-IP ACL path (wl_ifi). (P7b)
        params.USE_DIVISION = nats_map is None

        self._net = self._Network(name)
        # initializeNetwork(l1_links, devices, device_acls, vlan_ports, device_nats,
        #                   device_filters)
        self._net.initializeNetwork(links, devices, acls_map, None, nats_map, filters_set)
        self._eva = self._Evaluator(name, _tempfile.mktemp())

    def run(self, rules: List[str]) -> None:
        """ Apply a batch of rule updates IN MEMORY (a Python list of APKeep
        rule strings, e.g. "+ fwd <device> ..."), not a file APKeep parses.

        Phase C: if APKEEP_BUILD_PROFILE is set to a path, a Java-side daemon
        sampler streams JSONL build metrics to it (interval APKEEP_BUILD_PROFILE_MS,
        default 20000). Opt-in: no profiler thread and no file when unset, so normal
        runs / the exactness gate are unaffected. Started here because run() is one
        synchronous JPype call Python cannot poll during. """
        if self._net is None:
            raise RuntimeError("init_snapshot() must be called first")
        java_rules = self._ArrayList()
        for rule in rules:
            java_rules.add(str(rule).strip())
        prof_path = os.environ.get("APKEEP_BUILD_PROFILE")
        profiler = None
        if prof_path:
            profiler = jpype.JClass("apkeep.utils.BuildProfiler")
            interval = int(os.environ.get("APKEEP_BUILD_PROFILE_MS", "20000"))
            profiler.totalRules = jpype.JLong(len(rules))
            profiler.start(self._net, prof_path, jpype.JLong(interval))
        try:
            self._net.run(self._eva, java_rules)
        finally:
            if profiler is not None:
                profiler.stop()

    def is_reachable(self, src_device: str, src_port: str,
                     dst_device: str, dst_port: str,
                     src_prefix: Optional[int] = None, src_len: int = 0,
                     target_vlan: Optional[int] = None) -> bool:
        """ Existential reachability over the current PPM: can traffic injected
        at (src_device, src_port) reach (dst_device, dst_port)? Implemented by
        apkeep.checker.ReachabilityChecker (P3); this is the query FaVe's
        source->probe compliance checks reduce to.

        When ACL elements are present they filter on the source IP, so a query
        must inject the source's actual src-IP prefix (src_prefix as a uint32 +
        src_len); otherwise the ACL packet space is the full space and a flow
        counts as reachable whenever *any* source is permitted. Pass src_prefix
        None (the default) for forwarding-only networks (no ACL division). """
        if self._net is None:
            raise RuntimeError("init_snapshot() must be called first")
        checker = self._ReachabilityChecker(self._net)
        src = self._PositionTuple(src_device, src_port)
        dst = self._PositionTuple(dst_device, dst_port)
        # target_vlan (P7b): require the packets reaching the probe to carry this
        # VLAN (wl_stanford probes only accept vlan=0). Uses the 5-arg checker
        # overload; the source seed defaults to the full space when unconstrained.
        if target_vlan is not None:
            vlan_bdd = self._APKeeper.bddengine.ConvertVLAN(jpype.JInt(target_vlan))
            prefix = 0 if src_prefix is None else src_prefix
            plen = 0 if src_prefix is None else src_len
            return bool(checker.isReachable(
                src, dst, jpype.JLong(prefix), jpype.JInt(plen), jpype.JInt(vlan_bdd)
            ))
        if src_prefix is not None:
            return bool(checker.isReachable(
                src, dst, jpype.JLong(src_prefix), jpype.JInt(src_len)
            ))
        return bool(checker.isReachable(src, dst))

    # --- Phase 7 instrumentation ------------------------------------------
    def ap_num(self) -> int:
        """ Global atomic-predicate count of the built network (fwd + acl
        universes). The AP-count axis of the Phase-A scaling curve. """
        if self._net is None:
            raise RuntimeError("network not built")
        return int(self._net.getAPNum())

    def element_metrics(self) -> Dict[str, int]:
        """ Structural metrics of the built element graph: total elements,
        total ports, and a per-type breakdown. `ACLElement`/`NATElement` == 0
        is the single-universe precondition the reachability fixpoint needs. """
        if self._net is None:
            raise RuntimeError("network not built")
        return {
            "elements": int(self._net.numElements()),
            "ports": int(self._net.numPorts()),
            "ForwardElement": int(self._net.numElementsOfType("ForwardElement")),
            "FilterElement": int(self._net.numElementsOfType("FilterElement")),
            "ACLElement": int(self._net.numElementsOfType("ACLElement")),
            "NATElement": int(self._net.numElementsOfType("NATElement")),
        }

    def element_names(self) -> List[str]:
        """ All element names of the built network (Phase C1: bucket by role to
        size Lever A's element-count reduction headroom). """
        if self._net is None:
            raise RuntimeError("network not built")
        return [str(s) for s in self._net.elementNames()]

    def last_query_counters(self) -> Dict[str, int]:
        """ Work done by the most recent is_reachable() DFS: nodesVisited (every
        (path-prefix, port) expanded) and branchesExplored (child descents). The
        counters are static and reset at each isReachable() entry, so they hold
        the last query's totals -- the per-pair path-enumeration cost. """
        return {
            "nodesVisited": int(self._ReachabilityChecker.nodesVisited),
            "branchesExplored": int(self._ReachabilityChecker.branchesExplored),
        }

    def get_loops(self) -> List[str]:
        """ Detected forwarding loops, one normalised "loop found for [...]: ||
        <path>" record per loop, sorted (order-independent). """
        from java.io import ByteArrayOutputStream, PrintStream
        buf = ByteArrayOutputStream()
        printer = PrintStream(buf)
        self._eva.printLoop(printer)
        printer.flush()
        lines = str(buf.toString()).splitlines()
        loops = []
        for i, line in enumerate(lines):
            if line.startswith("loop found for") and i + 1 < len(lines):
                loops.append(line + " || " + lines[i + 1].rstrip())
        return sorted(loops)
