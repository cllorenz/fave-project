#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module provides a basic node model to be stored in NetPlumber.

TABLE SEMANTICS (TABLE_SEMANTICS_PLAN.md S1). Every table in FaVe resolves its
rules FIRST-MATCH-WINS, and for most of this project's life nothing said so: a
table whose real semantics differed -- a FIB resolved by longest prefix -- had
to be preprocessed INTO first-match order before it entered the model, and every
backend adapter had to re-derive what it originally was. Two of three backends
share the implicit default (NetPlumber resolves priority by rule index, ad6 is
first-match in document order), which is why it stayed invisible until APKeep
arrived with a destination-prefix trie, for which it is wrong.

The default is now explicit and TOTAL: `semantics_of(table)` answers for every
table, and `table_semantics` stores only the OVERRIDES, so a benchmark declares
its exceptions and nothing else. It is a statement of what a table IS; it is
deliberately NOT enforced here -- an adapter implements the declared semantics
in its own primitive, or refuses it. Reordering a declared-LPM table in the
model would bake a positional convention in for backends that do not need one,
and would make the model stop being a faithful record of the source config.
"""

from __future__ import annotations

import json

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from util.collections_util import list_sub, dict_sub
from util.typing_util import JSONDict

if TYPE_CHECKING:
    from rule.rule_model import Rule


# The table-semantics vocabulary. Deliberately small: a term with no consumer is
# a declaration nothing honours, which is the failure mode this mechanism exists
# to end. `admission` and `permutation` are implied by wl_stanford's other two
# stages and are NOT here, because nothing can carry them yet.
FIRST_MATCH = 'first_match'
LPM = 'lpm'
TABLE_SEMANTICS = frozenset({FIRST_MATCH, LPM})


class TableSemanticsError(Exception):
    """ Raised on an unknown semantics, or on one a model cannot carry. """


def restore_table_semantics(model: Any, j: JSONDict) -> Any:
    """ Read declared table semantics back off a serialised model.

    Kept OUT of the per-model `from_json` methods on purpose. All eight of them
    are independent -- not one chains to `AbstractDeviceModel.from_json` -- so a
    field added to the base is restored by none of them, and eight edits would
    have to be repeated by every future model. `_model_from_json` in
    `aggregator/aggregator_service.py` is the ONE place every model type is
    reconstructed (the live aggregator and `InProcessFaVe` both route through
    it), so the restore goes there instead.

    Tolerant by design: reading refuses nothing. An override could only have been
    WRITTEN by a model whose `to_json` carries it (`set_table_semantics` checks),
    so there is nothing left to catch here, and refusing on read would turn a
    stale snapshot into a crash.
    """
    if not isinstance(j, dict):
        return model

    semantics = j.get("table_semantics")
    if semantics and hasattr(model, "table_semantics"):
        model.table_semantics = dict(semantics)

    # A device arrives WRAPPED: `_model_from_json` is handed the whole command,
    # whose own type is `topology_command`, so the device and its declarations
    # sit one level down under "model". Recurse rather than special-casing the
    # command class here -- this stays right for any future wrapper, and getting
    # it wrong is silent (the declaration simply never arrives, which is exactly
    # what the first version of this did).
    inner = j.get("model")
    wrapped = getattr(model, "model", None)
    if isinstance(inner, dict) and wrapped is not None:
        restore_table_semantics(wrapped, inner)

    return model


class AbstractDeviceModel(object):
    """ This class stores a basic model for a node.
    """

    def __init__(
            self,
            node: str,
            mtype: str = "model",
            tables: Optional[Dict[str, List["Rule"]]] = None,
            ports: Optional[Dict[str, Any]] = None,
            wiring: Optional[List[Tuple[str, str]]] = None
    ) -> None:
        """ Constructs a basic NetPlumber model.

        Keyword arguments:
        node -- the node's name
        type -- the model's type (default: "model")
        tables -- a list of tables storing rules
        ports -- a mapping of port lists to the model's tables
        wiring -- a list of unidirectional links between the model's ports
        """

        self.node = node
        self.type = mtype
        self.tables: Dict[str, List["Rule"]] = tables if tables is not None else {}
        self.ports: Dict[str, Any] = ports if ports is not None else {}
        self.wiring: List[Tuple[str, str]] = wiring if wiring is not None else []
        # keyed by table name on reset but by rule.tid (int or str) on insert
        self._adds: Dict[Any, List["Rule"]] = {t : [] for t in self.tables}
        self._deletes: List[int] = []
        # OVERRIDES ONLY -- see `semantics_of`. Not materialised per table,
        # because tables are created lazily (RouterModel.persist calls
        # `self.tables.setdefault(...)` in four places), so a dict filled in here
        # would silently miss them; and because emitting an entry per table would
        # move every generated model JSON the test suite reads.
        self.table_semantics: Dict[str, str] = {}


    def __str__(self) -> str:
        return "node: %s\ntype: %s\ntables:\n\t%s\nports:\n\t%s\nwiring:\n\t%s" % (
            self.node,
            self.type,
            self.tables,
            self.ports,
            self.wiring
        )


    def reset(self) -> None:
        """ Resets add and delete buffers.
        """
        self._adds = {t : [] for t in self.tables}
        self._deletes = []


    def add_rule(self, rule: "Rule") -> None:
        """ Add rule to add buffer.

        Positional arguments:
        rule -- the rule to be added
        """
        self.add_rules([rule])


    def add_rules(self, rules: Iterable["Rule"]) -> None:
        """ Add rules to rule buffer.

        Positional arguments:
        rules -- list of ports to be added
        """
        for rule in rules:
            self._adds.setdefault(rule.tid, [])
            self._adds[rule.tid].append(rule)


    def remove_rule(self, idx: int) -> None:
        """ Add rule to delete buffer.
        """
        self._deletes.append(idx)


    def ingress_port(self, port: str) -> str:
        """ Returns the model's corresponding ingress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port


    def egress_port(self, port: str) -> str:
        """ Returns the model's corresponding egress port.

        Keyword arguments:
        port -- the outer model's port identifier
        """
        return port


    def table_index(self, table: str) -> int:
        """ Returns an unambigious index of an internal table.

        Keyword arguments:
        table -- The table's name
        """
        return sorted(self.tables.keys()).index(table)


    def port_index(self, port: str) -> int:
        """ Returns an unambigious index of a port of the model.

        Keyword arguments:
        port -- The port's name
        """
        return sorted(self.ports.keys()).index(port)


    def semantics_of(self, table: str) -> str:
        """ How `table` resolves its rules. TOTAL: every table has an answer.

        Defaulted on READ rather than materialised, so a table created after
        construction (RouterModel.persist creates several) still has semantics
        without anyone having to remember to register it.
        """
        return self.table_semantics.get(table, FIRST_MATCH)


    def set_table_semantics(self, table: str, semantics: str) -> None:
        """ Declare that `table` is not first-match.

        Refuses two ways, because a declaration that goes missing is worse than
        no declaration at all:

        * an unknown term -- the vocabulary is closed (`TABLE_SEMANTICS`);
        * a model class whose `to_json` would DROP it -- checked against the
          actual serialisation rather than a list of safe classes, which would
          rot the moment a model is added.

        **This second check fires on nothing today, and that was measured, not
        assumed.** All five `AbstractDeviceModel` subclasses carry the field:
        `SwitchModel` and `RouterModel` chain to this `to_json`, and
        `PacketFilterModel`, `ApplicationLayerGatewayModel` and
        `SnapshotPacketFilterModel` inherit it outright. (`GeneratorModel` and
        `ProbeModel` look like counterexamples and are not -- neither subclasses
        `AbstractDeviceModel`, so neither can reach this method. An earlier draft
        of this docstring claimed four models would drop the field; that was a
        `def to_json` grep that never checked class membership.) It is kept as a
        guard for the next model, not as live protection.
        """
        if semantics not in TABLE_SEMANTICS:
            raise TableSemanticsError(
                "unknown table semantics %r for %s.%s (known: %s)" % (
                    semantics, self.node, table, ', '.join(sorted(TABLE_SEMANTICS))
                )
            )
        if semantics == FIRST_MATCH:
            self.table_semantics.pop(table, None)   # the default is not an override
            return

        self.table_semantics[table] = semantics
        carried = self.to_json().get("table_semantics", {})
        if carried.get(table) != semantics:
            del self.table_semantics[table]
            raise TableSemanticsError(
                "%s.to_json() does not carry table_semantics, so declaring %s on "
                "%s.%s would be silently lost. Chain that to_json to "
                "AbstractDeviceModel.to_json before declaring semantics on this "
                "model." % (type(self).__name__, semantics, self.node, table)
            )


    def to_json(self) -> JSONDict:
        """ Converts the model to a JSON object.
        """

        j: JSONDict = {
            "node" : self.node,
            "type" : self.type,
            "tables" : {
                tk:[
                    r.to_json() for r in t
                ]  for tk, t in list(self.tables.items())
            },
            "ports" : self.ports,
            "wiring" : self.wiring
        }
        # Overrides only, and omitted entirely when there are none -- so every
        # model that declares nothing serialises exactly as it did before this
        # field existed. Same convention as SwitchModel.table_ids.
        if self.table_semantics:
            j["table_semantics"] = dict(self.table_semantics)
        return j


    def to_json_str(self) -> str:
        """ Converts the model to a JSON string.
        """
        return json.dumps(self.to_json())


    @staticmethod
    def from_string(jsons: str) -> "AbstractDeviceModel":
        """ Creates a model from a JSON string.

        Keyword arguments:
        jsons -- a JSON string
        """

        assert isinstance(jsons, str)

        j = json.loads(jsons)
        return AbstractDeviceModel.from_json(j)


    @staticmethod
    def from_json(j: JSONDict) -> "AbstractDeviceModel":
        """ Creates a model from a JSON object.

        Keyword arguments:
        j -- a JSON object
        """

        model = AbstractDeviceModel(
            j["node"],
            j["type"],
            tables=j["tables"],
            ports=j["ports"],
            wiring=[(p1, p2) for p1, p2 in j["wiring"]]
        )

        return model

    def __sub__(self, other: "AbstractDeviceModel") -> "AbstractDeviceModel":
        assert self.node == other.node
        assert self.type == other.type

        tables: Dict[str, List["Rule"]] = {}
        for tab in self.tables:
            if tab in other.tables:
                table = list_sub(self.tables[tab], other.tables[tab])
                if table:
                    tables[tab] = table

        ports = dict_sub(self.ports, other.ports)
        wiring = list_sub(self.wiring, other.wiring)

        # NB declared table semantics are NOT carried here. There are four
        # `__sub__` implementations (this one, AbstractFirewallModel,
        # RouterModel, SwitchModel) and exactly one caller
        # (`aggregator_service._sync_diff`), so the declarations are carried at
        # that call site instead -- one place that stays right when a fifth
        # `__sub__` is added, rather than four that must each remember.
        return AbstractDeviceModel(
            self.node,
            mtype=self.type,
            tables=tables,
            ports=ports,
            wiring=wiring
        )


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AbstractDeviceModel):
            return NotImplemented

        return all([
            self.node == other.node,
            self.type == other.type,
            self.tables == other.tables,
            self.ports == other.ports,
            self.wiring == other.wiring,
        ])

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result
