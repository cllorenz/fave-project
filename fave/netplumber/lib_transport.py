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

""" In-process transport for NetPlumberAdapter, backed by the libnetplumber
pybind11 binding instead of JSON-RPC over a socket.

Each method mirrors the signature of the corresponding ``netplumber.jsonrpc``
function (including the leading ``socks`` argument, which is ignored here) and
its return contract, so NetPlumberAdapter can use it as a drop-in ``self._rpc``.
The header-space / condition arguments are re-serialised to the exact JSON the
RPC client would have sent (the binding parses them with copies of the RPC
handler's helpers), so the engine sees identical inputs.
"""

from __future__ import annotations

import json

from typing import Any, Dict, Iterable, List, Optional


def _vec(v: Any) -> str:
    """ A match/mask/rewrite vector: a vector string, or "" for None/absent
    (which the binding maps to nullptr, exactly like jsonrpc.val_to_array). """
    return v if isinstance(v, str) else ""


def _hs_json(hs_list: Any, hs_diff: Any) -> str:
    """ Build the `hs` JSON exactly as jsonrpc.add_source does: a bare vector
    string when there is a single emitted vector and no diff, else {list,diff}. """
    if not hs_diff and len(hs_list) == 1:
        return json.dumps(hs_list[0])
    return json.dumps({"list": list(hs_list), "diff": list(hs_diff)})


class LibTransport:
    """ jsonrpc-compatible facade over a libnetplumber.LibNetPlumber instance. """

    def __init__(self, lib: Any) -> None:
        self._lib = lib

    # --- lifecycle / dumps ---------------------------------------------------

    def stop(self, _socks: Any) -> None:
        # No separate process to stop; the engine is freed when the binding
        # object is garbage-collected.
        pass

    def expand(self, _socks: Any, new_length: int) -> int:
        return int(self._lib.expand(new_length))

    def dump_flows(self, _socks: Any, odir: str) -> None:
        self._lib.dump_flows(odir)

    def dump_plumbing_network(self, _socks: Any, odir: str) -> None:
        self._lib.dump_plumbing_network(odir)

    def dump_pipes(self, _socks: Any, odir: str) -> None:
        self._lib.dump_pipes(odir)

    def dump_flow_trees(self, _socks: Any, odir: str, keep_simple: bool = False) -> None:
        self._lib.dump_flow_trees(odir, keep_simple)

    # --- topology ------------------------------------------------------------

    def add_link(self, _socks: Any, from_port: int, to_port: int) -> None:
        self._lib.add_link(from_port, to_port)

    def remove_link(self, _socks: Any, from_port: int, to_port: int) -> None:
        self._lib.remove_link(from_port, to_port)

    def add_links_bulk(self, _socks: Any, links: Iterable[Any], use_dynamic: bool = False) -> None:
        for _idx, src, dst in links:
            self._lib.add_link(src, dst)

    # --- tables / rules ------------------------------------------------------

    def add_table(self, _socks: Any, t_idx: int, ports: Any) -> None:
        self._lib.add_table(t_idx, list(ports))

    def remove_table(self, _socks: Any, t_idx: int) -> None:
        self._lib.remove_table(t_idx)

    def add_rule(self, _socks: Any, t_idx: int, r_idx: int, in_ports: Any,
                 out_ports: Any, match: Any, mask: Any, rewrite: Any) -> int:
        return int(self._lib.add_rule(
            t_idx, r_idx, list(in_ports), list(out_ports),
            _vec(match), _vec(mask), _vec(rewrite)
        ))

    def add_rules_batch(self, _socks: Any, rules: Iterable[Any]) -> List[int]:
        out = []
        for _np_rid, t_idx, r_idx, in_ports, out_ports, match, mask, rewrite in rules:
            out.append(int(self._lib.add_rule(
                t_idx, r_idx, list(in_ports), list(out_ports),
                _vec(match), _vec(mask), _vec(rewrite)
            )))
        return out

    def remove_rule(self, _socks: Any, r_idx: int) -> None:
        self._lib.remove_rule(r_idx)

    # --- sources / probes ----------------------------------------------------

    def add_source(self, _socks: Any, idx: int, hs_list: Any, hs_diff: Any,
                   ports: Any, use_dynamic: bool = False) -> int:
        return int(self._lib.add_source(_hs_json(hs_list, hs_diff), list(ports), idx))

    def add_sources_bulk(self, _socks: Any, sources: Iterable[Any],
                         use_dynamic: bool = False) -> Dict[int, int]:
        sids = {}
        for idx, hs_list, hs_diff, ports in sources:
            sids[idx] = int(self._lib.add_source(_hs_json(hs_list, hs_diff), list(ports), idx))
        return sids

    def remove_source(self, _socks: Any, s_idx: int) -> None:
        self._lib.remove_source(s_idx)

    def add_source_probe(self, _socks: Any, ports: Any, mode: str, match: Any,
                         filterexp: Any, test: Any, idx: int) -> int:
        filter_json = json.dumps(filterexp) if filterexp is not None else ""
        test_json = json.dumps(test) if test is not None else ""
        return int(self._lib.add_source_probe(
            list(ports), mode, _vec(match), filter_json, test_json, idx
        ))

    def remove_source_probe(self, _socks: Any, sp_idx: int) -> None:
        self._lib.remove_source_probe(sp_idx)

    # --- checks --------------------------------------------------------------

    def check_compliance(self, _socks: Any, rules: Dict[int, List[Any]]) -> None:
        mapped = {
            dst: [(src, valid, cond if cond is not None else "") for src, valid, cond in lst]
            for dst, lst in rules.items()
        }
        self._lib.check_compliance(mapped)

    def check_anomalies(self, _socks: Any, table: int = 0, use_shadow: bool = False,
                        use_reach: bool = False, use_general: bool = False) -> None:
        # libnetplumber does not yet expose anomaly checking; the benchmarks
        # under comparison exercise compliance, not anomalies. See APKEEP_BACKEND.md.
        raise NotImplementedError("libnetplumber: check_anomalies not yet supported")

    # --- slices (unsupported: libnetplumber/the comparison workloads use none) -

    def add_slice(self, _socks: Any, nid: int, ns_list: Any, ns_diff: Any) -> None:
        raise NotImplementedError("libnetplumber: slices not supported")

    def remove_slice(self, _socks: Any, nid: int) -> None:
        raise NotImplementedError("libnetplumber: slices not supported")
