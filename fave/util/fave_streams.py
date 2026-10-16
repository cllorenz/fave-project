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

""" S1-S3 driven through FaVe (INCREMENTAL_PLAN.md D14, owner: every
measurement is driven through FaVe, as an end user would change the network).

A workload's rules, as its user holds them, are of two kinds:

* **configuration rule lines** -- an iptables `-A` line of a packet filter or
  host, a router's `access-list` entry. A user changes one by editing the
  file and re-sending the device; the aggregator diffs it with stable indices
  (§8.1, as S4 does);
* **routes** -- the entries of `routes.json`, which every benchmark sends as
  control-plane `switch` commands. A user deletes or adds them with
  `switch.py -d -r` / `-a -r`.

**Links** are the links of `topology.json`, `policies.json` and
`sources.json`, taken down and up with `topology.py -d -l` / `-a -l`.

The streams are those of §7 over these units: S1 deletes every rule in
reverse build order (the configuration lines, as the devices are created,
then the routes) and inserts them again in build order; S2 deletes a seeded
fraction and re-adds it; S3 takes each link down and up. A batch is sent as
the fewest messages that keep its order: consecutive updates of one kind,
direction and device (a re-send, a command) form one message.

Every message is all or nothing in the aggregator (a refusal changes
nothing), so the state kept here is exactly what FaVe holds, and
`zero_prefix` writes it as a workload for the from-zero oracle.
"""

import copy
import json
import os
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from util.incremental import _S4_RULE_LINE, _config_index

#: one unit: ('line', device, line) | ('route', k) | ('link', role, k)
Unit = Tuple[Any, ...]
#: one update: (op, unit), op in delete, insert, link_down, link_up
Update = Tuple[str, Unit]

_ROLES = ('topology', 'routes', 'policies', 'sources')
_DEFAULT_NAMES = {'topology': 'topology.json', 'routes': 'routes.json',
                  'policies': 'policies.json', 'sources': 'sources.json'}


class FaveWorkload:
    """ A workload as its user changes it, with a working copy of every
    configuration file and the current state of every unit. """

    def __init__(self, prefix: str, workdir: str,
                 files: Optional[Dict[str, str]] = None) -> None:
        self.prefix, self.workdir = prefix, workdir
        self.absent: set = set()     # rule units deleted
        self.down: set = set()       # link units down
        self.names = dict(_DEFAULT_NAMES, **(files or {}))
        self.data: Dict[str, Any] = {}
        for role in _ROLES:
            with open(os.path.join(prefix, self.names[role])) as raw:
                self.data[role] = json.load(raw)
        self.devices = copy.deepcopy(self.data['topology']['devices'])
        #: device index -> its configuration's lines, as read
        self.lines: Dict[int, List[str]] = {}
        for n, device in enumerate(self.devices):
            if device[1] not in _S4_RULE_LINE:
                continue
            i = _config_index(device)
            with open(device[i]) as raw:
                self.lines[n] = raw.read().split('\n')
            device[i] = os.path.join(workdir, 'config_%d' % n)
            self._write(n)
        self.routes: List[List[Any]] = self.data['routes']
        #: the links per role, as the role's file lists them
        self.link_list: List[Tuple[str, int]] = [
            (role, k) for role in ('topology', 'policies', 'sources')
            for k in range(len(self.data[role].get('links', [])))]

    # -- units ---------------------------------------------------------------

    def rules(self) -> List[Unit]:
        """ Every rule unit in build order: each configuration's rule lines
        in topology then file order, then the routes in routes.json order. """
        out: List[Unit] = [('line', n, i) for n in sorted(self.lines)
                           for i, line in enumerate(self.lines[n])
                           if _S4_RULE_LINE[self.devices[n][1]](line)]
        return out + [('route', k) for k in range(len(self.routes))]

    def links(self) -> List[Unit]:
        return [('link', role, k) for role, k in self.link_list]

    def describe(self, unit: Unit) -> List[Any]:
        """ A unit as a stream record names it. """
        if unit[0] == 'line':
            return ['line', self.devices[unit[1]][0], unit[2], self.lines[unit[1]][unit[2]]]
        if unit[0] == 'route':
            route = self.routes[unit[1]]
            return ['route', route[0], route[2]]
        link = self.data[unit[1]]['links'][unit[2]]
        return ['link', link[0], link[1]]

    def _key(self, update: Update) -> Tuple[Any, ...]:
        """ Updates with the same key, consecutive in a batch, are one message. """
        op, unit = update
        if unit[0] == 'line':
            return (op, 'line', unit[1])
        if unit[0] == 'route':
            return (op, 'route', self.routes[unit[1]][0])
        return (op, 'link')

    def messages(self, batch: Sequence[Update]) -> List[Tuple[str, List[Unit]]]:
        """ `batch` as the fewest messages that keep its order. """
        out: List[Tuple[Tuple[Any, ...], str, List[Unit]]] = []
        for update in batch:
            key = self._key(update)
            if out and out[-1][0] == key:
                out[-1][2].append(update[1])
            else:
                out.append((key, update[0], [update[1]]))
        return [(op, units) for _key, op, units in out]

    # -- sending ---------------------------------------------------------------

    def _write(self, n: int) -> None:
        with open(self.devices[n][_config_index(self.devices[n])], 'w') as out:
            out.write('\n'.join(self._current(n)))

    def _current(self, n: int) -> List[str]:
        return [line for i, line in enumerate(self.lines[n])
                if ('line', n, i) not in self.absent]

    def send(self, fave: Any, op: str, units: List[Unit]) -> Dict[str, Any]:
        """ Send one message through `fave` (an InProcessFaVe) and keep the
        state in step. Returns what the message was: its kind and, for a
        re-send, the aggregator's `update_stats`. A refusal (BarrierError)
        propagates with the state unchanged. """
        kind = units[0][0]
        if kind == 'line':
            n = units[0][1]
            change = set(units)
            before = set(self.absent)
            if op == 'delete':
                self.absent |= change
            else:
                self.absent -= change
            self._write(n)
            try:
                fave.resend_device(self.devices[n])
            except Exception:
                self.absent = before
                self._write(n)
                raise
            return {'kind': 'resend', 'device': self.devices[n][0],
                    'stats': dict(fave._agg.update_stats or {})}
        if kind == 'route':
            routes = [self.routes[u[1]] for u in units]
            if op == 'delete':
                arg = '#'.join('$'.join((r[0], str(r[1]), str(r[2]))) for r in routes)
                fave.switch(['-d', '-r', arg])
                self.absent |= set(units)
            else:
                arg = '#'.join('$'.join((r[0], str(r[1]), str(r[2]), ','.join(r[5]),
                                         ';'.join(r[3]), ','.join(r[4]))) for r in routes)
                fave.switch(['-a', '-r', arg])
                self.absent -= set(units)
            return {'kind': 'command', 'node': routes[0][0]}
        links = [self.data[u[1]]['links'][u[2]] for u in units]
        arg = ','.join('%s:%s:%s' % (s, d, bool(b)) for s, d, b in links)
        if op == 'link_down':
            fave.topology(['-d', '-l', arg])
            self.down |= set(units)
        else:
            fave.topology(['-a', '-l', arg])
            self.down -= set(units)
        return {'kind': 'links'}

    # -- the oracle's workload ---------------------------------------------------

    def zero_prefix(self) -> str:
        """ A workload directory of the CURRENT state -- configurations as
        edited, routes present, links up -- for a from-zero build, under the
        workload's own file names (`files`); other files are linked. """
        zero = os.path.join(self.workdir, 'zero')
        os.makedirs(zero, exist_ok=True)
        own = {self.names[role] for role in _ROLES}
        for name in os.listdir(self.prefix):
            if name not in own and not os.path.exists(os.path.join(zero, name)):
                os.symlink(os.path.abspath(os.path.join(self.prefix, name)),
                           os.path.join(zero, name))
        for role in _ROLES:
            if role == 'routes':
                data: Any = [r for k, r in enumerate(self.routes)
                             if ('route', k) not in self.absent]
            else:
                data = copy.deepcopy(self.data[role])
                data['links'] = [l for k, l in enumerate(data.get('links', []))
                                 if ('link', role, k) not in self.down]
                if role == 'topology':
                    data['devices'] = self.devices
            with open(os.path.join(zero, self.names[role]), 'w') as out:
                json.dump(data, out)
        return zero


def stream_s1(rules: List[Unit]) -> List[Update]:
    """ S1: every rule deleted in reverse build order, then inserted in it. """
    return ([('delete', u) for u in reversed(rules)]
            + [('insert', u) for u in rules])


def stream_s2(rules: List[Unit], fraction: float, seed: int) -> List[Update]:
    """ S2: a seeded `fraction` of the rules deleted, then re-added, both in
    the drawn order. """
    drawn = random.Random(seed).sample(rules, max(1, int(round(fraction * len(rules)))))
    return [('delete', u) for u in drawn] + [('insert', u) for u in drawn]


def stream_s3(links: List[Unit]) -> List[Update]:
    """ S3: each link taken down, then up again, one at a time. """
    out: List[Update] = []
    for link in links:
        out += [('link_down', link), ('link_up', link)]
    return out


def build_stream(kind: str, workload: FaveWorkload, fraction: float,
                 seed: int) -> List[Update]:
    if kind == 's1':
        return stream_s1(workload.rules())
    if kind == 's2':
        return stream_s2(workload.rules(), fraction, seed)
    if kind == 's3':
        return stream_s3(workload.links())
    raise ValueError("unknown stream %r" % kind)
