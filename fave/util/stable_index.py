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

""" Stable rule indices across model updates -- INCREMENTAL_PLAN.md §8.1.

A modelling engine numbers a table's rules by position: the packet filter
renumbers every chain densely, so one inserted rule shifts every later index
and a rule-level diff sees the whole table as changed. A ruleset alone cannot
say which rule "was" where before an edit, so stability needs the previous
emission (results_m2_spike_20261011/FINDINGS.md). `StableIndexer` keeps it,
per (node, table), and re-numbers every new emission against it:

* the new rule list is aligned with the last emitted one by CONTENT (`key`):
  matched rules keep their index;
* a run of new rules takes evenly spaced free indices between its neighbours;
* a run that does not fit its gap relabels the smallest window around it to
  half the nominal spacing (the spike's R4c), counted in `stats`.

Order is preserved by construction, and asserted. A table is spaced within
`budget(table)` -- the aggregator's numbering, common to every engine -- unless
it holds more rules than that, or already reaches past it; then within
`limit(table)`, the engine's own (`max_rule_index`). The first emission spaces
a table at cap / (2(n+1)), leaving half the range for growth.
"""

from __future__ import annotations

import copy
import difflib

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

#: (table, in-ports, match, actions): what an engine sees of a rule. Index and
#: the raw-line metadata are not part of it -- `raw_line_no` shifts with every
#: line inserted above a rule, and no engine reads it.
Key = Tuple[Any, ...]


def key(rule: Any) -> Key:
    """ A rule's content, independent of its index. """
    return (rule.tid, tuple(rule.in_ports), str(rule.match),
            ",".join(str(a) for a in rule.actions))


class IndexBudgetExceeded(ValueError):
    """ A table holds more rules than its index budget has slots. """


class StableIndexer:
    """ Per (node, table): the last emission, and the re-numbering of the next
    one against it. `budget(table)` is the largest index the engine takes in
    that table. """

    def __init__(self, budget: Callable[[str], int],
                 limit: Optional[Callable[[str], int]] = None) -> None:
        self.budget = budget
        self.limit = limit
        self._last: Dict[Tuple[str, str], List[Tuple[int, Key]]] = {}
        #: relabelled windows, and the old rules they moved to a new index
        self.stats = {'windows': 0, 'moved': 0}

    def forget(self, node: str) -> None:
        """ A device left the model: its tables start afresh. """
        for nt in [nt for nt in self._last if nt[0] == node]:
            del self._last[nt]

    def seed(self, node: str, table: str, rules: List[Any]) -> None:
        """ Take `rules`, as the engine holds them, as the last emission of a
        table the indexer has not emitted -- a switch table filled by
        control-plane commands, with the indices their sender chose. """
        self._last[(node, table)] = [(r.idx, key(r)) for r in sorted(rules, key=lambda r: r.idx)]

    def drop(self, node: str, table: str, idxs: Iterable[int]) -> None:
        """ Rules a control-plane command deleted from a table: the last
        emission no longer holds them. """
        prev = self._last.get((node, table))
        if prev is not None:
            gone = set(idxs)
            self._last[(node, table)] = [e for e in prev if e[0] not in gone]

    def restore(self, node: str, table: str,
                last: Optional[List[Tuple[int, Key]]]) -> None:
        """ Put back an earlier `last(node, table)` (None: never emitted) --
        a re-send the engine refused is undone. """
        if last is None:
            self._last.pop((node, table), None)
        else:
            self._last[(node, table)] = list(last)

    def last(self, node: str, table: str) -> Optional[List[Tuple[int, Key]]]:
        """ The last emission of (node, table): [(idx, key)] in order. """
        return self._last.get((node, table))

    def emit(self, node: str, table: str, rules: List[Any]) -> List[Any]:
        """ `rules` in their table order (first-match order: as the modelling
        engine indexed them) -> copies carrying stable indices. """
        keys = [key(r) for r in rules]
        prev = self._last.get((node, table))
        cap = self._cap(table, len(keys), prev)
        if prev is None:
            idxs = self._spaced(len(keys), cap)
        else:
            idxs = self._aligned(prev, keys, cap)
        assert all(a < b for a, b in zip(idxs, idxs[1:])), "order not preserved"
        # (no bound on the indices kept: a seeded table carries the indices its
        # control plane chose -- index 0 included -- and the engine holds them)
        self._last[(node, table)] = list(zip(idxs, keys))
        out = []
        for idx, rule in zip(idxs, rules):
            new = copy.copy(rule)
            new.idx = idx
            out.append(new)
        return out

    def _cap(self, table: str, n: int, prev: Optional[List[Tuple[int, Key]]]) -> int:
        """ The common numbering's room for `table`, or -- for a table that
        does not fit it, or was already numbered past it -- the engine's. """
        cap = self.budget(table)
        if self.limit is None:
            return cap
        limit = self.limit(table)
        if limit <= cap:
            return limit
        if n > cap or (prev and prev[-1][0] > cap):
            return limit
        return cap

    @staticmethod
    def _step(n: int, cap: int) -> int:
        return max(1, cap // (2 * (n + 1)))

    def _spaced(self, n: int, cap: int) -> List[int]:
        if n > cap:
            raise IndexBudgetExceeded(
                "%d rules do not fit an index budget of %d" % (n, cap))
        step = self._step(n, cap)
        return [step * (i + 1) for i in range(n)]

    def _aligned(self, prev: List[Tuple[int, Key]], keys: List[Key], cap: int) -> List[int]:
        n = len(keys)
        if n > cap:
            raise IndexBudgetExceeded(
                "%d rules do not fit an index budget of %d" % (n, cap))
        ops = difflib.SequenceMatcher(None, [k for _i, k in prev], keys,
                                      autojunk=False).get_opcodes()
        slots: List[Optional[int]] = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                slots.extend(prev[i][0] for i in range(i1, i2))
            else:
                slots.extend([None] * (j2 - j1))
        # the spacing a relabel restores: half the nominal one (the spike's
        # R4c) -- the nominal spacing itself is only found at the table's free
        # end, so a window would always reach it
        target = max(1, self._step(n, cap) // 2)
        j = 0
        while j < n:
            if slots[j] is not None:
                j += 1
                continue
            a = j
            while j < n and slots[j] is None:
                j += 1
            b = j                                   # [a, b) has no index yet
            lo = slots[a - 1] if a > 0 else 0
            hi = slots[b] if b < n else cap + 1
            assert lo is not None and hi is not None
            if hi - lo - 1 >= b - a:                # it fits its gap
                self._fill(slots, a, b, lo, hi)
                continue
            left, right = a, b                      # widen a window [left, right)
            while True:
                while right < n and slots[right] is None:
                    right += 1                      # absorb a later run
                lo = slots[left - 1] if left > 0 else 0
                hi = slots[right] if right < n else cap + 1
                assert lo is not None and hi is not None
                if (hi - lo) // (right - left + 1) >= target:
                    break
                if left == 0 and right == n:
                    break                           # the whole table: lo=0, hi=cap+1
                if left > 0 and (right == n or (a - left) <= (right - b)):
                    left -= 1
                else:
                    right += 1
            moved = sum(1 for x in range(left, right) if slots[x] is not None)
            if moved:
                self.stats['windows'] += 1
                self.stats['moved'] += moved
            self._fill(slots, left, right, lo, hi)
            j = right
        return [s for s in slots if s is not None] if None not in slots else \
            self._unreachable()

    @staticmethod
    def _fill(slots: List[Optional[int]], a: int, b: int, lo: int, hi: int) -> None:
        """ Spread slots [a, b) evenly strictly between lo and hi. """
        step = (hi - lo) / (b - a + 1)
        for x in range(a, b):
            slots[x] = int(lo + step * (x - a + 1))

    @staticmethod
    def _unreachable() -> List[int]:
        raise AssertionError("a rule was left without an index")


def diff(prev: Optional[List[Tuple[int, Key]]], emitted: List[Any]
         ) -> Tuple[List[int], List[Any]]:
    """ INCREMENTAL_PLAN.md §8.1 (4): the rules an engine must delete (by
    index) and insert to go from the emission `prev` to `emitted` -- an index
    that left, or whose content changed, is deleted; one that is new, or whose
    content changed, is inserted. """
    old = dict(prev or [])
    new = {r.idx: (key(r), r) for r in emitted}
    deletes = sorted(i for i, k in old.items() if i not in new or new[i][0] != k)
    inserts = [r for i, (k, r) in sorted(new.items()) if old.get(i) != k]
    return deletes, inserts
