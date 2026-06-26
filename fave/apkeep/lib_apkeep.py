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

from typing import Any, List, Optional

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
        self._ArrayList = jpype.JClass("java.util.ArrayList")
        self._net: Any = None
        self._eva: Any = None

    def init_snapshot(self, snapshot_dir: str) -> None:
        """ Build the network from an APKeep snapshot directory (topo/acls/vlan/
        parameters). P4 will replace this with in-memory construction from a
        FaVe model. """
        self._APKeep.init(snapshot_dir)
        self._net = self._APKeep.net
        self._eva = self._APKeep.eva

    def run(self, rules: List[str]) -> None:
        """ Apply a batch of rule updates IN MEMORY (a Python list of APKeep
        rule strings, e.g. "+ fwd <device> ..."), not a file APKeep parses. """
        if self._net is None:
            raise RuntimeError("init_snapshot() must be called first")
        java_rules = self._ArrayList()
        for rule in rules:
            java_rules.add(str(rule).strip())
        self._net.run(self._eva, java_rules)

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
