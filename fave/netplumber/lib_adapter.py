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

""" An AbstractVerificationEngine backed by the in-process libnetplumber binding.

NetPlumberLibAdapter reuses ALL of NetPlumberAdapter's model translation (port
numbering, vector building, negation expansion, generator/rule/probe prep) and
only swaps the transport: instead of JSON-RPC over a socket, it drives the
NetPlumber C++ core in-process via libnetplumber (see APKEEP_BACKEND.md, P1).

Compliance results are read in-process via get_compliance_results() (option b),
rather than through NetPlumber's log4cxx output + the Reporter's log tail.
"""

from __future__ import annotations

import os
import sys

from typing import Any, List, Optional, Tuple

from aggregator.aggregator_abstract import TraceLogger
from netplumber.adapter import NetPlumberAdapter
from netplumber.lib_transport import LibTransport

# The libnetplumber extension module is built next to the NetPlumber sources
# (net_plumber/python/build_libnetplumber.sh). Make it importable without an
# install step. Import is deferred-friendly: a missing build only fails when a
# NetPlumberLibAdapter is actually constructed, not on module import.
_LIBNP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "net_plumber", "python")
)
if _LIBNP_DIR not in sys.path:
    sys.path.insert(0, _LIBNP_DIR)

try:
    import libnetplumber  # type: ignore
except ImportError:  # pragma: no cover - only when the .so is not built
    libnetplumber = None  # type: ignore


class NetPlumberLibAdapter(NetPlumberAdapter):
    """ NetPlumberAdapter driving the C++ core in-process via libnetplumber. """

    def __init__(self, logger: TraceLogger, mapping: Optional[Any] = None) -> None:
        if libnetplumber is None:
            raise RuntimeError(
                "libnetplumber is not built; run net_plumber/python/build_libnetplumber.sh"
            )

        # Set up all the adapter state (mapping, tables, ports, ...). No sockets.
        super().__init__([], logger, asyncore_socks=None, mapping=mapping)

        # Start the in-process engine at 1 byte (mirrors `net_plumber --hdr-len 1`)
        # and grow it to the current mapping length, just as _expand() would.
        self._lib = libnetplumber.LibNetPlumber(1)
        self._rpc = LibTransport(self._lib)
        if self.mapping.length:
            self._lib.expand(self.mapping.length)

    def get_compliance_results(self) -> List[Tuple[int, int, bool, str]]:
        """ Compliance violations collected since the last clear, as
        (src_node_id, dst_node_id, valid, cond) tuples -- the same records the
        Reporter would have parsed from NetPlumber's log, delivered in-process. """
        return [tuple(r) for r in self._lib.get_compliance_results()]

    def clear_results(self) -> None:
        self._lib.clear_results()
