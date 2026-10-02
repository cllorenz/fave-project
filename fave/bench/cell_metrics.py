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

""" What a measured cell is made of: memory sampling, GC, verdicts, limits.

EXTRACTED 2026-10-02 from `bench/deltanet/eval/engine_run.py`, unchanged, so
that `bench/cell_run.py` measures with the SAME code rather than a second copy
of it. A fork here would be the worst place for one: two runners that sample
RSS slightly differently produce two columns a table cannot put side by side,
and the difference would be invisible in the results. `engine_run.py` imports
these back under their old names, so every figure it has already produced stays
re-derivable from it.

What is NEW here, and is TODO item 31's unchecked box:

* `machine()` -- the machine description stamped on every cell. Item 31 fixes
  the reportable memory limit "with the machine's description" before anything
  is measured, and no cell carried one.
* `limit_stamps()` -- `limit_wall`, `limit_rss`, `limit_class`, `machine`,
  `limit_tripped`, the five item 31 names. Verified absent from the tree on
  2026-10-02: no result file, anywhere, said under which limit it was produced.
* `outcome()` -- the distinction the stopping-rule discipline rests on. A run
  the DECLARED limit killed is a result; a run the environment killed is not,
  and calling the second one a did-not-finish manufactures a finding
  (`AD6_PLAN.md` §9.34.3 is the case where that nearly happened).
"""

import hashlib
import os
import platform
import re


#: `status` -> what ended the run.
#:
#: `completed`/`error` come from the child's exit code; `deadline`/`memory`
#: from the two declared stopping rules; `interrupted` from a signal this
#: process received, which is the unstable-machine case and is NOT a result.
STATUSES = ('completed', 'error', 'deadline', 'memory', 'interrupted')

#: `outcome` -> what the cell says about the ENGINE, which is a different
#: question from what ended the run. A cell killed by the environment says
#: nothing about the engine at all.
OUTCOMES = ('correct', 'wrong_verdict', 'did_not_finish', 'interrupted',
            'error', 'measured')


def sha256(path):
    """ The hash of a file, or None if it is not there. A jar that was not
    built is a fact about the run worth recording, not an exception. """
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def available_mb():
    with open('/proc/meminfo') as handle:
        for line in handle:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) // 1024
    raise RuntimeError('no MemAvailable in /proc/meminfo')


def swap_used_mb():
    """ System-wide swap in use -- SwapTotal minus SwapFree. """
    fields = {}
    with open('/proc/meminfo') as handle:
        for line in handle:
            name, _, rest = line.partition(':')
            fields[name] = int(rest.split()[0])
    return (fields['SwapTotal'] - fields['SwapFree']) // 1024


def swap_traffic():
    """ Pages swapped in and out since boot (`/proc/vmstat`); a run's
    difference says whether it actually swapped, which occupancy alone
    cannot -- pages can sit in swap from before the run. """
    counts = {}
    with open('/proc/vmstat') as handle:
        for line in handle:
            name, value = line.split()
            if name in ('pswpin', 'pswpout'):
                counts[name] = int(value)
    return counts


def label(pid):
    """ Which part of the run a process is: the `-c` bootstrap is the
    benchmark, the aggregator carries APKeep in-process (JPype), and
    `net_plumber` is NetPlumber's C++ server. """
    with open('/proc/%s/cmdline' % pid, 'rb') as handle:
        argv = handle.read().split(b'\0')
    text = b' '.join(argv).decode(errors='replace')
    for name in ('aggregator', 'net_plumber'):
        if name in text:
            return name
    if b'-c' in argv[1:2]:
        return 'benchmark'
    return os.path.basename(argv[0].decode(errors='replace')) or 'other'


def session_pids(session):
    """ Every live pid in `session`. Used both to sample a run and, after a
    kill, to find what outlived it: an external SIGTERM bypasses `run()`'s
    `finally`, so `_teardown` never runs and the aggregator is orphaned --
    and the next cell then measures a machine that is not idle. """
    found = []
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/%s/stat' % pid) as handle:
                fields = handle.read().rsplit(')', 1)[1].split()
            if int(fields[3]) == session:       # field 6: session id
                found.append(int(pid))
        except (OSError, IndexError, ValueError):
            continue                            # exited while sampled
    return found


def process_state(pid):
    """ The single-letter state from `/proc/<pid>/stat`, or None if it is gone.

    Needed to tell a LIVE straggler from a ZOMBIE. A zombie is already dead --
    it holds no memory and can pollute nothing -- it is simply waiting to be
    reaped, and after a clean benchmark there is reliably one, reparented to
    init. Counting it as an orphan would mark every clean cell in the campaign
    as having leaked, and the one time a real orphan appeared, nobody would
    look twice.
    """
    try:
        with open('/proc/%s/stat' % pid) as handle:
            return handle.read().rsplit(')', 1)[1].split()[0]
    except (OSError, IndexError):
        return None


def live_session_pids(session):
    """ `session_pids` without the zombies -- what a cleanup sweep must act on. """
    return [pid for pid in session_pids(session)
            if process_state(pid) not in (None, 'Z')]


def session_rss_mb(session, field='VmRSS:'):
    """ `{label: summed RSS}` over every process in `session` -- the
    benchmark, the aggregator and whatever engine it started
    (`start_new_session`). `field='VmSwap:'` sums swapped-out memory
    instead. """
    totals = {}
    for pid in session_pids(session):
        try:
            name = label(pid)
            with open('/proc/%s/status' % pid) as handle:
                for line in handle:
                    if line.startswith(field):
                        totals[name] = (totals.get(name, 0)
                                        + int(line.split()[1]) // 1024)
        except (OSError, IndexError, ValueError):
            continue                            # exited while sampled
    return totals


_GC_PAUSE = re.compile(r'GC\(\d+\) (Pause [A-Za-z ]+?) (?:\(.*\) )*'
                       r'.*?(\d+)M->(\d+)M\((\d+)M\) ([0-9.]+)ms')


def gc_summary(path):
    """ Collections, total pause and the largest heap after a collection,
    from a JDK `-Xlog:gc` file. Pauses only: concurrent phases do not stop
    the engine. """
    pauses, total_ms, full, heap_after, heap_committed = 0, 0.0, 0, 0, 0
    with open(path) as handle:
        for line in handle:
            match = _GC_PAUSE.search(line)
            if match is None:
                continue
            pauses += 1
            total_ms += float(match.group(5))
            full += match.group(1).startswith('Pause Full')
            heap_after = max(heap_after, int(match.group(3)))
            heap_committed = max(heap_committed, int(match.group(4)))
    return {'pauses': pauses, 'full_pauses': full,
            'pause_s': round(total_ms / 1000, 3),
            'max_heap_after_gc_mb': heap_after,
            'max_heap_committed_mb': heap_committed}


def violations(report_text):
    """ The violation lines of the Compliance Check section, counted. """
    section = report_text.split('## Compliance Check', 1)[-1]
    section = section.split('\n## ', 1)[0]
    return [line for line in section.splitlines() if line.startswith('- `')]


# ---- what item 31 asked for, and what was missing ---------------------------

def machine():
    """ The machine a cell was measured on, stamped so a table cannot put two
    of them in one column by accident.

    Item 31 fixes the reportable memory limit "with the machine's description"
    before V5 measures anything, and `CLOUD_BENCH_PLAN.md` §2.15 had to write
    its machine into prose because no result carried one. SWAP is in here for
    a reason that cost a campaign: the 19 GB box had swap and the 32 GB box had
    none, so on the second an overshoot was the OOM killer rather than a
    slowdown, and the same `--memory-floor` means different things on the two.
    """
    meminfo = {}
    with open('/proc/meminfo') as handle:
        for line in handle:
            name, _, rest = line.partition(':')
            meminfo[name] = int(rest.split()[0])
    return {
        'ram_mb': meminfo['MemTotal'] // 1024,
        'swap_mb': meminfo['SwapTotal'] // 1024,
        'cores': os.cpu_count(),
        'kernel': platform.release(),
        'node': platform.node(),
    }


def limit_stamps(limit_class, wall_s, rss_mb, tripped):
    """ Item 31's five stamps, exactly as it names them.

    `tripped` is the ONLY one that is not a declaration, and it is three-valued
    on purpose: `wall` and `rss` are the two declared stopping rules, and
    `none` covers both a run that finished and a run the environment killed.
    Which of those two it was is `outcome()`'s job, not this one's -- keeping
    them apart is what stops "the container died" being recorded as "the engine
    did not finish".
    """
    assert tripped in ('wall', 'rss', 'none'), tripped
    return {
        'limit_class': limit_class,
        'limit_wall_s': wall_s,
        'limit_rss_mb': rss_mb,
        'limit_tripped': tripped,
        'machine': machine(),
    }


def outcome(status, verdict_valid, expected_violations=None,
            got_violations=None):
    """ What the cell says about the ENGINE.

    The four cases item 31's result-cell schema asks to be told apart, plus
    two the campaign needs:

    * `interrupted` -- the environment killed it. **Not a result**, and not a
      did-not-finish: it is re-run. This is the distinction the whole
      stopping-rule discipline rests on, and the reason the campaign's runner
      has a signal handler at all.
    * `did_not_finish` -- a DECLARED limit killed it. A result, and reportable,
      provided a progress lower bound came with it.
    * `error` -- the run failed on its own, or finished without a readable
      verdict. A missing `report.md` lands here rather than in `correct`,
      which is the trap `AD6_PLAN.md` §9.34.3 records: `grep -c` on an absent
      file returns 0, indistinguishable from "no violations".
    * `correct` / `wrong_verdict` -- only when an expectation was DECLARED.
      Without one the honest answer is `measured`: this harness will not invent
      an oracle, and `reachable.json` is not one (TODO item 1s).
    """
    if status == 'interrupted':
        return 'interrupted'
    if status in ('deadline', 'memory'):
        return 'did_not_finish'
    if status != 'completed' or not verdict_valid:
        return 'error'
    if expected_violations is None:
        return 'measured'
    return 'correct' if got_violations == expected_violations else 'wrong_verdict'
