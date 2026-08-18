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

""" In-process driver for the NDD reachability engine (the ndd/ subtree) via
JPype -- FaVe's second backend ENGINE behind the shared APKeep adapter (the BDD
engine is apkeep/lib_apkeep.py; see APKEEP_NDD_PLAN.md, §2.5e).

The APKeepAdapter emits a backend-neutral IR (APKeep "+ filter ..." rule strings
+ "dev port dev port" topology edges). The BDD path hands them to APKeep
(lib_apkeep); the NDD path hands the SAME strings to
org.ants.jndd.fave.NddReachabilityEngine, which builds a per-field NDD residual
forwarding model and answers source->probe reachability -- proven at exact
parity with the frozen BDD baseline on wl_up (§2.5c/d), and far faster (no
per-field atomic-predicate cross-product).

Scope: single-universe forwarding (no ACL/NAT). The adapter guards this before
dispatching here.

Requires JDK 11 + the built NDD fat jar (ndd/target/ndd-1.0.1-jar-with-
dependencies.jar; `mvn -f ndd/pom.xml -DskipTests package`). `available()`
reports whether both are present so callers/tests can skip cleanly.
"""

from __future__ import annotations

import os

from typing import List, Optional, Set

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_NDD_JAR = os.path.join(
    _REPO_ROOT, "ndd", "target", "ndd-1.0.1-jar-with-dependencies.jar"
)
_APKEEP_JAR = os.path.join(_REPO_ROOT, "apkeep", "target", "apkeep-1.0.0.jar")

try:
    import jpype
    import jpype.imports  # noqa: F401
except ImportError:  # pragma: no cover - JPype not installed
    jpype = None  # type: ignore


def available() -> bool:
    """ True iff JPype is importable and the NDD fat jar is built. """
    return jpype is not None and os.path.isfile(_NDD_JAR)


def _union_classpath() -> List[str]:
    """ The resident JVM is process-global (JPype cannot restart it), and the
    APKeepAdapter may drive EITHER engine in one process, so both jars go on the
    classpath when present -- whichever engine boots the JVM first, both are
    reachable. Kept identical here and in lib_apkeep so boot order is irrelevant. """
    return [j for j in (_APKEEP_JAR, _NDD_JAR) if os.path.isfile(j)]


def _ensure_jvm() -> None:
    """ Start the resident JVM once (idempotent), with the union classpath. """
    if jpype is None:
        raise RuntimeError("JPype is not installed (pip install JPype1)")
    if not os.path.isfile(_NDD_JAR):
        raise RuntimeError(
            "NDD jar not built: %s (run `mvn -f ndd/pom.xml -DskipTests package`)"
            % _NDD_JAR
        )
    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=_union_classpath())


class LibNDD:
    """ Resident-JVM, in-process handle to a single NddReachabilityEngine.

    NDD keeps its decision-diagram node tables in process-global statics, so one
    LibNDD instance maps to one network per process (as LibAPKeep does for
    APKeep). Build once from the adapter's rule+edge IR, then query reachability.
    """

    def __init__(self) -> None:
        _ensure_jvm()
        self._Engine = jpype.JClass("org.ants.jndd.fave.NddReachabilityEngine")
        self._ArrayList = jpype.JClass("java.util.ArrayList")
        self._eng = self._Engine()
        self._built = False

    def build(self, rules: List[str], edges: List[str]) -> None:
        """ Build the residual forwarding model from the adapter's neutral IR:
        `rules` are APKeep rule strings (only "+ filter ..." are consumed),
        `edges` are "dev port dev port" topology strings. """
        jrules = self._ArrayList()
        for r in rules:
            jrules.add(str(r).strip())
        jedges = self._ArrayList()
        for e in edges:
            jedges.add(str(e).strip())
        self._eng.build(jrules, jedges)
        self._built = True

    def is_reachable(self, src_device: str, src_port: str,
                     dst_device: str, dst_port: str,
                     src_cidr: Optional[str] = None) -> bool:
        """ Existential reachability source->probe over the built model. The
        source emits its own src space (`src_cidr`, None => unconstrained); a
        probe counts as reached iff its DEVICE received a non-empty header set on
        any port. The per-source flood is cached engine-side. """
        if not self._built:
            raise RuntimeError("build() must be called first")
        return bool(self._eng.isReachable(
            str(src_device), str(src_port),
            None if src_cidr is None else str(src_cidr),
            str(dst_device), str(dst_port)
        ))

    def reached_devices(self, src_device: str, src_port: str,
                        src_cidr: Optional[str] = None) -> Set[str]:
        """ The set of device names reachable from one source (diagnostic). """
        if not self._built:
            raise RuntimeError("build() must be called first")
        js = self._eng.reachedDevices(
            str(src_device), str(src_port),
            None if src_cidr is None else str(src_cidr)
        )
        return {str(x) for x in js}
