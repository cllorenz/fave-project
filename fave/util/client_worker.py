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

""" FaVe's client side -- topology.py/switch.py: parse, generate, serialise --
in a process of its own, for `InProcessFaVe` (TODO item 60).

Real FaVe runs every client command as a process of its own. The in-process
harness ran them in the process it measures, where the iptables parser
(pybison 0.6.4) leaks every parse tree whole: its `py_callback` never
releases the argument lists of a grammar action, nor the generated actions
their stack values. A re-sent wl_tum packet filter left ~210 MB behind.

The worker is a fresh interpreter (`python -m util.client_worker`), not a
fork: a fork of a process holding a JVM inherits locks the JVM's threads held
and deadlocked on them (the integration tier, 2026-10-17). It serves calls
until its resident set passes `recycle_mb`, then the parent replaces it;
so what it leaks is bounded, and its memory counts to the cell's, as a real
client's would to the machine's.

Protocol, on the worker's stdin and a duplicate of its stdout (its own
stdout and stderr both go to the parent's stderr): length-prefixed JSON
frames. A request is {"call": "module:function", "args": [...], "kwargs":
{...}}; the worker answers with one {"msg": <a message the client sent>} per
message, then {"done": true} or {"error": <traceback>}.
"""

import importlib
import json
import os
import struct
import subprocess
import sys
import traceback
from typing import Any, BinaryIO, Dict, List, Optional

_HEAD = struct.Struct('!Q')


def _write(out: BinaryIO, obj: Any) -> None:
    raw = json.dumps(obj).encode()
    out.write(_HEAD.pack(len(raw)) + raw)
    out.flush()


def _read(inp: BinaryIO) -> Optional[Any]:
    head = inp.read(_HEAD.size)
    if len(head) < _HEAD.size:
        return None
    raw = inp.read(_HEAD.unpack(head)[0])
    return json.loads(raw)


def device(*entry: Any, **kwargs: Any) -> None:
    """ Send one `topology.json` device entry, as `replay` sends it. """
    from util.bench_utils import _DEVICES
    _DEVICES[entry[1]](*entry, **kwargs)


def serve(inp: BinaryIO, out: BinaryIO) -> None:
    """ The worker's loop: one request after the other, until stdin closes. """
    import topology.topology as topo_mod
    import devices.switch as switch_mod
    sent: List[str] = []

    class _Conn:
        def close(self) -> None:
            pass

    for mod in (topo_mod, switch_mod):
        mod.connect_to_fave = lambda *_a, **_k: _Conn()
        mod.fave_sendmsg = lambda _conn, data: sent.append(data)
    while True:
        request = _read(inp)
        if request is None:
            return
        del sent[:]
        try:
            module, name = request['call'].split(':')
            getattr(importlib.import_module(module), name)(
                *request.get('args', []), **request.get('kwargs', {}))
        except BaseException:
            _write(out, {'error': traceback.format_exc()})
            continue
        for data in sent:
            _write(out, {'msg': data})
        _write(out, {'done': True})


class ClientWorker:
    """ The parent's end: `call` runs a client in the worker and returns the
    messages it sent; a client that raises raises RuntimeError here with the
    worker's traceback, and none of its messages are returned. """

    def __init__(self, recycle_mb: int = 512) -> None:
        self.recycle_mb = recycle_mb
        self.recycled = 0
        self._proc: Optional[subprocess.Popen] = None

    def _start(self) -> subprocess.Popen:
        env = dict(os.environ)
        # the parent's import path is the worker's: it runs the same checkout
        env['PYTHONPATH'] = os.pathsep.join(p for p in sys.path if p)
        return subprocess.Popen(
            [sys.executable, '-m', 'util.client_worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)

    def call(self, target: str, *args: Any, **kwargs: Any) -> List[str]:
        if self._proc is None:
            self._proc = self._start()
        proc = self._proc
        assert proc.stdin is not None and proc.stdout is not None
        _write(proc.stdin, {'call': target, 'args': list(args), 'kwargs': kwargs})
        messages: List[str] = []
        while True:
            reply: Optional[Dict[str, Any]] = _read(proc.stdout)
            if reply is None:
                self._proc = None
                raise RuntimeError("the client worker died (exit %s)" % proc.wait())
            if 'msg' in reply:
                messages.append(reply['msg'])
            elif 'error' in reply:
                self._maybe_recycle()
                raise RuntimeError("client failed:\n" + reply['error'])
            else:
                break
        self._maybe_recycle()
        return messages

    def rss_mb(self) -> Optional[float]:
        if self._proc is None:
            return None
        try:
            with open('/proc/%d/status' % self._proc.pid) as raw:
                for line in raw:
                    if line.startswith('VmRSS:'):
                        return int(line.split()[1]) / 1024
        except OSError:
            pass
        return None

    def _maybe_recycle(self) -> None:
        rss = self.rss_mb()
        if rss is not None and rss > self.recycle_mb:
            self.close()
            self.recycled += 1
            # the next one starts now, importing while the caller goes on
            self._proc = self._start()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        assert proc.stdin is not None
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()


def main() -> int:
    # The protocol on a private duplicate of stdout; what the client prints
    # goes to stderr, so it cannot corrupt a frame.
    out = os.fdopen(os.dup(1), 'wb')
    os.dup2(2, 1)
    serve(sys.stdin.buffer, out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
