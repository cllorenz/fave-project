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

""" A campaign directory's MACHINE.txt and ARTIFACTS.txt (INCREMENTAL_PLAN.md
D17.7), with the sections V5 wrote by hand (`bench/campaigns/MACHINE.txt`,
`ARTIFACTS.txt`): written when the protocol is declared, checked again when
the queue ends -- an artifact whose hash changed is a finding.

    python3 bench/campaign_stamps.py write <campaign dir>
    python3 bench/campaign_stamps.py check <campaign dir>   # exit 1 on a change

Run from fave/. The gate results (the integration tier on the measured code)
are the protocol's to record; this records what can be read off the machine.
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from util import provenance  # noqa: E402

#: the engines' source trees, whose last commit S5.0's staleness rule keys on
TREES = ('apkeep', 'ndd', 'net_plumber', 'veriflow_fr', 'ad6',
         'fave/veriflow', 'fave/apkeep', 'fave/netplumber', 'fave/aggregator')


def _run(argv: List[str], cwd: Optional[str] = None) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, check=False)
    except OSError:
        return '(unavailable)'
    return (proc.stdout + proc.stderr).strip()


def _first(text: str) -> str:
    return text.splitlines()[0] if text else '(unavailable)'


def machine_text() -> str:
    root = os.path.dirname(os.getcwd())
    cpu = '(unknown)'
    try:
        with open('/proc/cpuinfo') as raw:
            for line in raw:
                if line.startswith('model name'):
                    cpu = line.split(':', 1)[1].strip()
                    break
    except OSError:
        pass
    os_name = '(unknown)'
    try:
        with open('/etc/os-release') as raw:
            for line in raw:
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
    except OSError:
        pass
    swaps = _run(['cat', '/proc/swaps']).splitlines()[1:]
    lines = [
        '# Machine record, recorded before anything ran (INCREMENTAL_PLAN.md D17.7)',
        '# Date: %s' % time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), '',
        'git_head          %s' % _run(['git', 'rev-parse', 'HEAD'], root),
        'git_branch        %s' % _run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], root),
        'git_describe      %s' % _run(['git', 'log', '-1', '--format=%h %s'], root),
        'git_dirty         %s' % ('yes' if _run(['git', 'status', '--porcelain',
                                                 '--untracked-files=no'], root) else 'no'),
        'kernel            %s' % platform.release(),
        'os                %s' % os_name,
        'nproc             %d' % (os.cpu_count() or 0),
        'cpu_model         %s' % cpu, '',
        '## memory',
        *['  ' + l for l in _run(['free', '-m']).splitlines()],
        '  swap: %d device(s)%s' % (len(swaps), '  <-- ZERO SWAP: an overshoot is the '
                                     'OOM killer, not a slowdown' if not swaps else ''), '',
        '## disk',
        *['  ' + l for l in _run(['df', '-h', '/dev/shm', root]).splitlines()],
    ]
    return '\n'.join(lines) + '\n'


def artifact_hashes() -> Dict[str, Optional[str]]:
    return provenance.artifacts()


def artifacts_text() -> str:
    root = os.path.dirname(os.getcwd())
    lines = ['# Build artifacts (INCREMENTAL_PLAN.md D17.7)',
             '# Date: %s' % time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), '',
             '## artifact hashes (identity within this campaign)']
    for path, digest in sorted(artifact_hashes().items()):
        lines.append('  %s  %s' % (digest or '(missing)', path))
    lines += ['', '## engine source commits']
    for tree in TREES:
        if os.path.exists(os.path.join(root, tree)):
            lines.append('  %-24s %s' % (tree, _run(
                ['git', 'log', '-1', '--format=%h  %ad', '--date=short', '--', tree], root)))
    java11 = '/usr/lib/jvm/java-11-openjdk-amd64/bin/java'
    lines += ['', '## toolchain',
              '  build JDK   %s' % (_first(_run([java11, '-version']))
                                    if os.path.exists(java11) else '(no JDK 11)'),
              '  default JVM %s' % _first(_run(['java', '-version'])),
              '  maven       %s' % _first(_run(['mvn', '-B', '-v'])),
              '  gcc         %s' % _first(_run(['gcc', '--version'])),
              '  python      %s (%s)' % (platform.python_version(), sys.executable)]
    return '\n'.join(lines) + '\n'


_HASH_LINE = re.compile(r'^  ([0-9a-f]{64}|\(missing\))  (\S+)$')


def recorded_hashes(path: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    with open(path) as raw:
        for line in raw:
            match = _HASH_LINE.match(line.rstrip('\n'))
            if match:
                out[match.group(2)] = None if match.group(1) == '(missing)' else match.group(1)
    return out


def check(directory: str) -> List[str]:
    """ What changed since ARTIFACTS.txt was written: one line per artifact. """
    recorded = recorded_hashes(os.path.join(directory, 'ARTIFACTS.txt'))
    now = artifact_hashes()
    return ['%s: %s -> %s' % (path, recorded.get(path), now.get(path))
            for path in sorted(set(recorded) | set(now))
            if recorded.get(path) != now.get(path)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=('write', 'check'))
    parser.add_argument('directory')
    args = parser.parse_args(argv)
    if args.action == 'write':
        os.makedirs(args.directory, exist_ok=True)
        for name, text in (('MACHINE.txt', machine_text()), ('ARTIFACTS.txt', artifacts_text())):
            target = os.path.join(args.directory, name)
            if os.path.exists(target):
                parser.error("%s exists: a record is not overwritten" % target)
            with open(target, 'w') as out:
                out.write(text)
        return 0
    changed = check(args.directory)
    for line in changed:
        print("CHANGED " + line)
    if not changed:
        print("artifacts unchanged since ARTIFACTS.txt")
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())
